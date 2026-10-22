"""
阿里云文档智能 DocMind 解析（Web 版）

用阿里云 AccessKey（AK/SK）调用 DocMind，把扫描版 PDF / Word / 图片解析为
Markdown 文本与表格行，再由本地规则抽取字段（不依赖大模型 API Key）。

调用方式参考 private/xiaomuzhe/scripts/aliyun_docmind.py：
提交解析任务 -> 轮询状态 -> 分页取结果。
"""

import io
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import web_config


class DocMindError(Exception):
    pass


# ────────────────── SDK 客户端 ──────────────────

def _get_client(cfg: Dict[str, Any]):
    try:
        from alibabacloud_docmind_api20220711.client import Client
        from alibabacloud_tea_openapi import models as open_api_models
    except ImportError as e:
        raise DocMindError(
            '未安装 DocMind SDK，请执行：'
            'pip install alibabacloud-docmind-api20220711 alibabacloud-tea-openapi alibabacloud-tea-util'
        ) from e

    ak = os.environ.get('ALIYUN_AK', '').strip() or cfg.get('access_key_id', '')
    sk = os.environ.get('ALIYUN_SK', '').strip() or cfg.get('access_key_secret', '')
    if not ak or not sk:
        raise DocMindError('未配置阿里云 AccessKey，请在「AI 接口设置」中填写 AccessKey ID / Secret')

    conf = open_api_models.Config(access_key_id=ak, access_key_secret=sk)
    conf.endpoint = web_config.DOCMIND_ENDPOINT
    return Client(conf)


def check_credentials(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    """轻量校验 AK/SK：查询一个不存在的任务，鉴权通过时返回业务错误而非签名错误"""
    try:
        from alibabacloud_docmind_api20220711 import models as dm_models
    except ImportError as e:
        return False, f'未安装 DocMind SDK：{e}'
    try:
        client = _get_client(cfg)
        client.query_doc_parser_status(
            dm_models.QueryDocParserStatusRequest(id='000000000000000000'))
        return True, 'AccessKey 校验通过'
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if 'signature' in low or 'invalidaccesskey' in low or 'forbidden' in low or '401' in low:
            return False, f'AccessKey 校验失败：{msg[:200]}'
        # 参数/任务不存在等业务错误说明签名已通过
        return True, 'AccessKey 校验通过（任务 ID 不存在属预期）'


# ────────────────── 输入准备 ──────────────────

def _prepare_upload(file_path: str) -> Tuple[bytes, str, str]:
    """DocMind 支持 PDF/Word/图片；图片先转为单页 PDF，统一按 pdf 提交"""
    ext = os.path.splitext(file_path)[1].lower()
    base = os.path.splitext(os.path.basename(file_path))[0]
    with open(file_path, 'rb') as f:
        content = f.read()

    if ext in ('.bmp', '.tif', '.tiff', '.webp'):
        try:
            import fitz
            pix = fitz.Pixmap(content)
            if pix.alpha or pix.colorspace.n > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            content = pix.tobytes('png')
        except Exception:
            pass
        ext = '.png'

    if ext in ('.png', '.jpg', '.jpeg'):
        try:
            import fitz
            img = fitz.open(file_path)
            content = img.convert_to_pdf()
            img.close()
            return content, f'{base}.pdf', 'pdf'
        except Exception as e:
            raise DocMindError(f'图片转 PDF 失败：{e}') from e

    return content, os.path.basename(file_path), ext.lstrip('.')


# ────────────────── HTML 表格 → 行 ──────────────────

def _html_table_rows(html: str) -> List[List[str]]:
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows: List[List[str]] = []
            self._row: Optional[List[str]] = None
            self._cell: Optional[List[str]] = None

        def handle_starttag(self, tag, attrs):
            if tag == 'tr':
                self._row = []
            elif tag in ('td', 'th') and self._row is not None:
                self._cell = []

        def handle_endtag(self, tag):
            if tag in ('td', 'th') and self._row is not None and self._cell is not None:
                self._row.append(' '.join(''.join(self._cell).split()))
                self._cell = None
            elif tag == 'tr' and self._row is not None:
                if any(c for c in self._row):
                    self.rows.append(self._row)
                self._row = None

        def handle_data(self, data):
            if self._cell is not None:
                self._cell.append(data)

    parser = _P()
    try:
        parser.feed(html)
    except Exception:
        return []
    return parser.rows


# ────────────────── 主解析入口 ──────────────────

def parse_document(doc, cfg: Dict[str, Any],
                   progress=None) -> Dict[str, Any]:
    """
    解析文档为文本与表格。

    Returns:
        {'text': str, 'tables': [[[cell, ...], ...], ...], 'layouts': int}
    """
    try:
        from alibabacloud_docmind_api20220711 import models as dm_models
        from alibabacloud_tea_util import models as util_models
    except ImportError as e:
        raise DocMindError(f'未安装 DocMind SDK：{e}') from e

    client = _get_client(cfg)
    data, file_name, ext = _prepare_upload(doc.file_path)

    if progress:
        progress(f'提交 DocMind 解析任务（{os.path.basename(doc.file_path)}）...')
    req = dm_models.SubmitDocParserJobAdvanceRequest(
        file_url_object=io.BytesIO(data),
        file_name=file_name,
        file_name_extension=ext,
    )
    try:
        body = client.submit_doc_parser_job_advance(req, util_models.RuntimeOptions()).body.to_map()
        job_id = (body.get('Data') or {}).get('Id')
    except Exception as e:
        raise DocMindError(f'提交 DocMind 任务失败：{e}') from e
    if not job_id:
        raise DocMindError(f'DocMind 未返回任务 ID：{str(body)[:200]}')

    if progress:
        progress('DocMind 正在识别页面（扫描件通常需要数十秒）...')
    deadline = time.time() + web_config.DOCMIND_TIMEOUT
    status = ''
    while time.time() < deadline:
        try:
            st = client.query_doc_parser_status(
                dm_models.QueryDocParserStatusRequest(id=job_id)
            ).body.to_map().get('Data', {}).get('Status', '')
            status = str(st or '').lower()
        except Exception as e:
            raise DocMindError(f'查询 DocMind 状态失败：{e}') from e
        if status in ('success', 'succeeded'):
            break
        if status in ('failed', 'fail'):
            raise DocMindError('DocMind 解析失败，请确认文件未加密且页数在限制内')
        time.sleep(web_config.DOCMIND_POLL_INTERVAL)
    else:
        raise DocMindError(f'DocMind 解析超时（>{web_config.DOCMIND_TIMEOUT}s）')

    if progress:
        progress('拉取 DocMind 识别结果...')
    layouts: List[Dict[str, Any]] = []
    num = 0
    step = 200
    while True:
        try:
            r = client.get_doc_parser_result(
                dm_models.GetDocParserResultRequest(
                    id=job_id, layout_num=num, layout_step_size=step)
            )
        except Exception as e:
            raise DocMindError(f'获取 DocMind 结果失败：{e}') from e
        d = r.body.to_map().get('Data') or {}
        part = d.get('layouts') or []
        if not part:
            break
        layouts.extend(part)
        if len(part) < step:
            break
        num += step

    tables: List[Dict[str, Any]] = []
    lines: List[str] = []
    last_title = ''
    for layout in layouts:
        ltype = str(layout.get('type') or '').lower()
        if ltype == 'table':
            html = layout.get('tableHtml') or layout.get('table_html') or ''
            rows = _html_table_rows(html)
            if rows:
                tables.append({'title': last_title, 'rows': rows})
                for row in rows:
                    lines.append(' | '.join(row))
                continue
        text = (layout.get('markdownContent') or layout.get('markdown_content')
                or layout.get('text') or '')
        text = str(text).strip()
        if text:
            lines.append(text)
            # 记录表格前的最近一段文字，作为该表标题（用于区分同表头表格）
            if ltype in ('title', 'heading', 'header', 'text', ''):
                last_title = text.split('\n')[0][:60]

    return {'text': '\n'.join(lines), 'tables': tables, 'layouts': len(layouts)}
