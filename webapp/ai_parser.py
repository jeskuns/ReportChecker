"""
AI 文档解析模块（Web 版）
调用通义千问视觉模型（阿里百炼，OpenAI 兼容接口），
按模板字段定义从报告页面中提取结构化数据。
"""

import json
import re
from typing import Any, Callable, Dict, List, Optional

import requests

import web_config
from doc_loader import LoadedDocument


def parse_number(text: Any) -> Optional[float]:
    """从文本中解析数值（移植自桌面版 utils.parse_number，去除 numpy 依赖）"""
    if text is None or isinstance(text, (int, float)):
        return float(text) if text is not None else None
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text or text.upper() in ("N/A", "NA", "无", "—", "-", "合格", "PASS", "OK"):
        return None
    m = re.search(r'[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', text)
    if m:
        try:
            return float(m.group(0).replace(',', ''))
        except ValueError:
            pass
    for pattern in (r'≤\s*([-+]?\d[\d.,]*)', r'≥\s*([-+]?\d[\d.,]*)',
                    r'<\s*([-+]?\d[\d.,]*)', r'>\s*([-+]?\d[\d.,]*)',
                    r'([-+]?\d[\d.,]*)'):
        m = re.search(pattern, text)
        if m:
            try:
                return float(m.group(1).replace(',', ''))
            except ValueError:
                continue
    return None


# ────────────────── 模板 → 提取 Schema ──────────────────

def collect_template_fields(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    """汇总模板 tables 中的全部字段定义（含所属表格标题与表头）"""
    result = []
    for tdef in template.get('tables', []):
        table_title = tdef.get('title', '')
        headers = [h.get('label', '') for h in tdef.get('headers', [])]
        for f in tdef.get('fields', []):
            result.append({
                'name': f.get('name', ''),
                'type': f.get('type', 'text'),
                'description': f.get('description', ''),
                'unit': f.get('unit', ''),
                'array_size': f.get('array_size'),
                'computed': bool(f.get('computed')),
                'table': table_title,
                'headers': headers,
            })
    # 兼容旧版 fields 顶层格式
    for f in template.get('fields', []):
        result.append({
            'name': f.get('field_name', ''),
            'type': f.get('type', 'text'),
            'description': f.get('description', ''),
            'unit': f.get('unit', ''),
            'array_size': None,
            'computed': False,
            'table': '',
            'headers': [],
        })
    return [f for f in result if f['name']]


def build_prompt(template: Dict[str, Any], fields: List[Dict[str, Any]]) -> str:
    """根据模板字段定义构造提取指令"""
    meta_lines = [
        f"标准：{template.get('standard', '')}",
        f"测试项目：{template.get('title', '')}（{template.get('description', '')}）",
    ]

    field_lines = []
    cur_table = None
    for f in fields:
        if f['table'] != cur_table:
            cur_table = f['table']
            if cur_table:
                header_str = '、'.join(f['headers']) if f['headers'] else '键值对'
                field_lines.append(f"\n◆ 表格「{cur_table}」（列：{header_str}）")
        desc = f['description'] or f['name']
        unit = f"（单位 {f['unit']}）" if f['unit'] else ''
        if f['type'] == 'number_array':
            shape = f"数字数组，长度 {f['array_size'] or '按表格列数'}"
        elif f['type'] == 'number':
            shape = "单个数字"
        else:
            shape = "文本"
        note = "；该字段为计算值，若报告中印有记录值则提取，否则填 null" if f['computed'] else ''
        field_lines.append(f"  - \"{f['name']}\": {desc}{unit}，{shape}{note}")

    return (
        "你是电动工具检测报告的数据提取助手。请阅读提供的报告页面（图像或文本），"
        "提取下列字段并以严格 JSON 输出。\n\n"
        + "\n".join(meta_lines) + "\n"
        + "\n".join(field_lines) + "\n\n"
        "输出要求：\n"
        "1. 只输出一个 JSON 对象，键为字段英文名，不要输出任何解释、注释或 markdown 代码围栏。\n"
        "2. 数字字段输出数值（不带单位、不带千分位逗号）；确实找不到的填 null。\n"
        "3. 数字数组按表格从左到右的顺序输出，缺失的单元格用 null 占位，保持数组长度。\n"
        "4. 文本字段输出原文（如\"合格\"、\"电阻法\"等）。\n"
        "5. 表格中合并单元格或空白的列，同样以 null 占位。"
    )


# ────────────────── API 调用 ──────────────────

class AIParseError(Exception):
    pass


def _chat_completions_url(base_url: str) -> str:
    return base_url.rstrip('/') + '/chat/completions'


def _call_qwen(messages: list, api_key: str, base_url: str, model: str) -> str:
    resp = requests.post(
        _chat_completions_url(base_url),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        json={
            'model': model,
            'messages': messages,
            'temperature': 0,
        },
        timeout=web_config.REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise AIParseError(f'AI 接口错误 {resp.status_code}: {resp.text[:300]}')
    data = resp.json()
    try:
        return data['choices'][0]['message']['content']
    except (KeyError, IndexError) as e:
        raise AIParseError(f'AI 返回格式异常: {str(data)[:300]}') from e


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出中提取 JSON 对象"""
    text = text.strip()
    # 去除 markdown 代码围栏
    m = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    start = text.find('{')
    end = text.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        # 常见修复：尾逗号
        cleaned = re.sub(r',\s*([}\]])', r'\1', text[start:end + 1])
        try:
            obj = json.loads(cleaned)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None


def _coerce_value(raw: Any, fdef: Dict[str, Any]) -> Any:
    """按字段定义把 AI 输出转为目标类型"""
    if raw is None:
        return None
    ftype = fdef['type']
    if ftype == 'number':
        return parse_number(raw)
    if ftype == 'number_array':
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, str):
            # 兼容 AI 返回 "10, 50, 60" 这类逗号分隔字符串
            items = [s for s in re.split(r'[，,、;；\s]+', raw.strip()) if s]
        else:
            items = [raw]
        values = [parse_number(v) for v in items]
        size = fdef.get('array_size')
        if size:
            values = values[:size] + [None] * max(0, size - len(values))
        return values
    # text
    if isinstance(raw, str):
        return raw.strip() or None
    return str(raw)


def _merge_extracted(base: Dict[str, Any], extra: Dict[str, Any]):
    """分批解析结果合并：非空优先，数组逐元素补齐"""
    for key, val in extra.items():
        if val is None:
            continue
        old = base.get(key)
        if old is None:
            base[key] = val
        elif isinstance(old, list) and isinstance(val, list):
            merged = []
            for i in range(max(len(old), len(val))):
                a = old[i] if i < len(old) else None
                b = val[i] if i < len(val) else None
                merged.append(a if a is not None else b)
            base[key] = merged


# ────────────────── 主入口 ──────────────────

def extract_fields(doc: LoadedDocument,
                   template: Dict[str, Any],
                   api_key: str,
                   base_url: str,
                   model: str,
                   progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    用 AI 按模板提取字段值。

    Returns:
        {field_name: 数值/数组/文本/None}
    """
    if not api_key:
        raise AIParseError('未配置 API Key，请在右上角「AI 接口设置」中填写所选服务商的 API Key')

    fields = collect_template_fields(template)
    if not fields:
        raise AIParseError('模板中未定义任何字段')

    prompt = build_prompt(template, fields)
    system_msg = {'role': 'system', 'content': '你是严谨的数据提取助手，只输出 JSON。'}

    extracted: Dict[str, Any] = {}

    if doc.doc_type == 'word':
        # Word：纯文本提交
        text = doc.all_text()
        if not text.strip():
            raise AIParseError('Word 文档中未提取到文本内容')
        if progress:
            progress('正在提交 Word 文本给 AI 解析...')
        messages = [system_msg, {'role': 'user', 'content': prompt + '\n\n报告全文：\n' + text[:30000]}]
        raw = _call_qwen(messages, api_key, base_url, model)
        obj = _extract_json(raw)
        if obj is None:
            raise AIParseError('AI 输出无法解析为 JSON')
        _merge_extracted(extracted, obj)
    else:
        # PDF / 图片：按页分批携带图像（文字型 PDF 同时附文本）
        page_nums = list(range(min(doc.page_count, web_config.MAX_PAGES_TOTAL)))
        batches = [page_nums[i:i + web_config.MAX_PAGES_PER_CALL]
                   for i in range(0, len(page_nums), web_config.MAX_PAGES_PER_CALL)]
        for bi, batch in enumerate(batches):
            if progress:
                progress(f'AI 正在解析第 {batch[0] + 1}~{batch[-1] + 1} 页'
                         f'（第 {bi + 1}/{len(batches)} 批）...')
            content: List[Dict[str, Any]] = [{'type': 'text', 'text': prompt}]
            for p in batch:
                b64 = doc.page_base64(p, dpi=web_config.RENDER_DPI)
                if b64:
                    content.append({
                        'type': 'image_url',
                        'image_url': {'url': f'data:image/png;base64,{b64}'},
                    })
                page_text = doc.page_text(p).strip()
                if page_text:
                    content.append({'type': 'text', 'text': f'（第 {p + 1} 页文本层）\n{page_text[:8000]}'})
            if len(content) == 1:
                continue
            messages = [system_msg, {'role': 'user', 'content': content}]
            raw = _call_qwen(messages, api_key, base_url, model)
            obj = _extract_json(raw)
            if obj is not None:
                _merge_extracted(extracted, obj)

    # 类型规整
    result: Dict[str, Any] = {}
    fdef_map = {f['name']: f for f in fields}
    for name, fdef in fdef_map.items():
        result[name] = _coerce_value(extracted.get(name), fdef)
    return result
