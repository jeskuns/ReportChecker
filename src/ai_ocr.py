"""
AI 两段式识别引擎（桌面版）

第一段：视觉模型 OCR —— 页面图像 → 文字（保留表格行列）
第二段：大模型抽取 —— 文字 + 模板字段定义 → 结构化字段

仅在用户于「模型」下拉框手动选择「AI 视觉模型」时使用，不参与自动级联。
"""

import base64
import json
import re
from typing import Any, Dict, List, Optional

from ai_config import is_configured, load_ai_config

AI_ENGINE_NAME = 'AI 视觉模型'

OCR_PROMPT = (
    '你是 OCR 引擎。识别这页图片中的全部文字，按从上到下、从左到右的顺序输出。'
    '表格按行输出，同一行的单元格之间用 " | " 分隔。'
    '只输出识别到的原文，不要解释、不要使用 Markdown 代码块。'
)

MAX_IMAGE_WIDTH = 2000


# ────────────────── 图像编码 ──────────────────

def _encode_image(image) -> bytes:
    import cv2

    img = image
    h, w = img.shape[:2]
    if w > MAX_IMAGE_WIDTH:
        scale = MAX_IMAGE_WIDTH / float(w)
        img = cv2.resize(img, (MAX_IMAGE_WIDTH, int(h * scale)),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode('.png', img)
    if not ok:
        raise RuntimeError('图像编码失败')
    return buf.tobytes()


def _strip_fence(text: str) -> str:
    text = (text or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```[a-zA-Z]*\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    return text.strip()


def _chat(cfg: dict, model: str, messages: list) -> str:
    import requests

    resp = requests.post(
        cfg['base_url'].rstrip('/') + '/chat/completions',
        headers={'Authorization': f"Bearer {cfg['api_key']}",
                 'Content-Type': 'application/json'},
        json={'model': model, 'temperature': 0, 'messages': messages},
        timeout=cfg.get('timeout', 120),
    )
    if resp.status_code != 200:
        detail = (resp.text or '').strip().replace('\n', ' ')[:200]
        if resp.status_code == 401:
            raise RuntimeError(f'鉴权失败（401），请检查 API Key：{detail}')
        if resp.status_code == 402:
            raise RuntimeError(f'账户余额不足（402），请先充值：{detail}')
        raise RuntimeError(f'接口返回 {resp.status_code}：{detail}')
    body = resp.json()
    try:
        content = body['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f'返回格式异常：{str(body)[:200]}')
    if isinstance(content, list):
        content = ''.join(p.get('text', '') for p in content if isinstance(p, dict))
    return str(content)


# ────────────────── 第一段：OCR ──────────────────

def ocr_image(image, cfg: dict = None) -> str:
    cfg = cfg or load_ai_config()
    if not is_configured(cfg):
        raise RuntimeError('未配置 AI 模型，请到「设置 → AI 模型设置」填写地址、模型和 API Key')
    data = base64.b64encode(_encode_image(image)).decode('ascii')
    text = _chat(cfg, cfg['ocr_model'], [{
        'role': 'user',
        'content': [
            {'type': 'text', 'text': OCR_PROMPT},
            {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{data}'}},
        ],
    }])
    return _strip_fence(text)


# ────────────────── 第二段：字段抽取 ──────────────────

def collect_fields(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    fields = []
    for tdef in template.get('tables', []):
        title = tdef.get('title', '')
        headers = [h.get('label', '') for h in tdef.get('headers', [])]
        for f in tdef.get('fields', []):
            if not f.get('name'):
                continue
            fields.append({
                'name': f['name'],
                'type': f.get('type', 'text'),
                'description': f.get('description', ''),
                'unit': f.get('unit', ''),
                'array_size': f.get('array_size'),
                'computed': bool(f.get('computed')),
                'table': title,
                'headers': headers,
            })
    for f in template.get('fields', []):
        name = f.get('field_name') or f.get('name')
        if not name:
            continue
        fields.append({
            'name': name, 'type': f.get('type', 'text'),
            'description': f.get('description', ''), 'unit': f.get('unit', ''),
            'array_size': None, 'computed': False, 'table': '', 'headers': [],
        })
    return fields


def build_prompt(template: Dict[str, Any], fields: List[Dict[str, Any]]) -> str:
    lines = [
        f"标准：{template.get('standard', '')}",
        f"测试项目：{template.get('title', '')}（{template.get('description', '')}）",
    ]
    cur = None
    for f in fields:
        if f['table'] != cur:
            cur = f['table']
            if cur:
                header_str = '、'.join(f['headers']) if f['headers'] else '键值对'
                lines.append(f"\n◆ 表格「{cur}」（列：{header_str}）")
        desc = f['description'] or f['name']
        unit = f"（单位 {f['unit']}）" if f['unit'] else ''
        if f['type'] == 'number_array':
            shape = f"数字数组，长度 {f['array_size'] or '按表格列数'}"
        elif f['type'] == 'number':
            shape = '单个数字'
        else:
            shape = '文本'
        note = '；该字段为计算值，若报告中印有记录值则提取，否则填 null' if f['computed'] else ''
        lines.append(f'  - "{f["name"]}": {desc}{unit}，{shape}{note}')

    return (
        '你是电动工具检测报告的数据提取助手。请阅读提供的报告识别文本，'
        '提取下列字段并以严格 JSON 输出。\n\n'
        + '\n'.join(lines) + '\n\n'
        '输出要求：\n'
        '1. 只输出一个 JSON 对象，键为字段英文名，不要输出解释或 markdown 代码围栏。\n'
        '2. 数字字段输出数值（不带单位、不带千分位逗号）；找不到的填 null。\n'
        '3. 数字数组按表格从左到右顺序输出，缺失单元格用 null 占位，保持数组长度。\n'
        '4. 文本字段输出原文。\n'
        '5. 报告中未出现的字段一律填 null，不要猜测。'
    )


def parse_number(text: Any) -> Optional[float]:
    if text is None or isinstance(text, (int, float)):
        return float(text) if text is not None else None
    if not isinstance(text, str):
        return None
    t = text.strip()
    if not t or t.upper() in ('N/A', 'NA', '无', '—', '-', '合格', 'PASS', 'OK'):
        return None
    m = re.search(r'[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', t)
    if m:
        try:
            return float(m.group(0).replace(',', ''))
        except ValueError:
            pass
    for pat in (r'≤\s*([-+]?\d[\d.,]*)', r'≥\s*([-+]?\d[\d.,]*)',
                r'<\s*([-+]?\d[\d.,]*)', r'>\s*([-+]?\d[\d.,]*)',
                r'([-+]?\d[\d.,]*)'):
        m = re.search(pat, t)
        if m:
            try:
                return float(m.group(1).replace(',', ''))
            except ValueError:
                continue
    return None


def _coerce(raw: Any, fdef: Dict[str, Any]) -> Any:
    if raw is None:
        return None
    if fdef['type'] == 'number':
        return parse_number(raw)
    if fdef['type'] == 'number_array':
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, str):
            items = [s for s in re.split(r'[，,、;；\s]+', raw.strip()) if s]
        else:
            items = [raw]
        values = [parse_number(v) for v in items]
        size = fdef.get('array_size')
        if size:
            values = values[:size] + [None] * max(0, size - len(values))
        return values
    if isinstance(raw, str):
        return raw.strip() or None
    return str(raw)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    s = (text or '').strip()
    m = re.search(r'```(?:json)?\s*(.*?)```', s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    start, end = s.find('{'), s.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(s[start:end + 1])
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        try:
            obj = json.loads(re.sub(r',\s*([}\]])', r'\1', s[start:end + 1]))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None


def extract_fields_from_text(text: str, template: Dict[str, Any],
                             cfg: dict = None) -> Dict[str, Any]:
    """第二段：从 OCR 文本中抽取模板字段"""
    cfg = cfg or load_ai_config()
    if not is_configured(cfg):
        raise RuntimeError('未配置 AI 模型')
    fields = collect_fields(template)
    if not fields:
        return {}
    prompt = build_prompt(template, fields)
    raw = _chat(cfg, cfg['extract_model'], [
        {'role': 'system', 'content': '你是严谨的数据提取助手，只输出 JSON。'},
        {'role': 'user', 'content': f'{prompt}\n\n报告识别文本：\n{text[:40000]}'},
    ])
    obj = _extract_json(raw)
    if obj is None:
        raise RuntimeError('模型输出无法解析为 JSON')
    return {f['name']: _coerce(obj.get(f['name']), f) for f in fields}


# ────────────────── 引擎适配 ──────────────────

class AIVisionEngine:
    """对齐 BaseOCREngine 接口，供 MultiOCREngine 调度"""

    def __init__(self):
        self._name = AI_ENGINE_NAME
        self._error = ''
        self._cfg = load_ai_config()

    def get_engine_name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        self._cfg = load_ai_config()
        if not is_configured(self._cfg):
            self._error = '未配置 AI 模型（地址 / 模型 / API Key）'
            return False
        return True

    def get_error_message(self) -> str:
        return self._error

    def recognize_region(self, image) -> Optional[str]:
        self._cfg = load_ai_config()
        if not is_configured(self._cfg):
            self._error = '未配置 AI 模型（地址 / 模型 / API Key）'
            return None
        try:
            text = ocr_image(image, self._cfg)
            self._error = ''
            return text or None
        except Exception as e:
            self._error = str(e)
            return None

    def recognize_full_page(self, image) -> Optional[str]:
        return self.recognize_region(image)


def test_connection(cfg: dict = None) -> tuple:
    """测试配置：用抽取模型发一次最小请求"""
    cfg = cfg or load_ai_config()
    if not is_configured(cfg):
        return False, '请先填写 Base URL、识别模型、抽取模型和 API Key'
    try:
        _chat(cfg, cfg['extract_model'],
              [{'role': 'user', 'content': '回复 OK'}])
        return True, f"连接成功（识别 {cfg['ocr_model']} / 抽取 {cfg['extract_model']}）"
    except Exception as e:
        return False, str(e)
