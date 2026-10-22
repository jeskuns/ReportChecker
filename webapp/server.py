"""
ReportChecker Web 版 — FastAPI 服务
PC / 手机浏览器通用，AI（通义千问）解析 + 本地规则引擎校验
"""

import os
import threading
import time
import traceback
import uuid
from typing import Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import web_config
from ai_parser import AIParseError, extract_fields
from doc_loader import LoadedDocument
from docmind_ocr import DocMindError, check_credentials, parse_document
from rule_engine import check_rules, list_templates, load_template
from rule_extract import extract_fields_local

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title='ReportChecker Web', docs_url=None, redoc_url=None)

# ────────────────── 文档与任务管理 ──────────────────

_docs: Dict[str, dict] = {}          # doc_id -> {'doc': LoadedDocument, 'name': str, 'ts': float}
_tasks: Dict[str, dict] = {}         # task_id -> {'status','progress','result','error','ts'}
_lock = threading.Lock()

ALLOWED_EXTS = ('.pdf', '.docx', '.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp')


def _cleanup_expired():
    now = time.time()
    with _lock:
        for store in (_docs, _tasks):
            expired = [k for k, v in store.items() if now - v['ts'] > web_config.DOC_TTL]
            for k in expired:
                item = store.pop(k)
                if 'doc' in item:
                    try:
                        item['doc'].close()
                    except Exception:
                        pass


def _get_doc(doc_id: str) -> LoadedDocument:
    entry = _docs.get(doc_id)
    if not entry:
        raise HTTPException(404, '文档不存在或已过期，请重新上传')
    entry['ts'] = time.time()
    return entry['doc']


# ────────────────── 请求模型 ──────────────────

class CheckRequest(BaseModel):
    doc_id: str
    templates: List[str]


class ConfigRequest(BaseModel):
    engine: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    access_key_id: Optional[str] = None
    access_key_secret: Optional[str] = None


def _config_view(cfg: dict) -> dict:
    """对外暴露的配置视图（不返回明文密钥）"""
    return {
        'engine': cfg['engine'],
        'engines': web_config.list_engines(),
        'provider': cfg['provider'],
        'providers': web_config.list_providers(),
        'base_url': cfg['base_url'],
        'model': cfg['model'],
        'has_key': bool(cfg['api_key']),
        'key_masked': web_config.mask_key(cfg['api_key']),
        'has_access_key': bool(cfg['access_key_id']),
        'access_key_id_masked': web_config.mask_key(cfg['access_key_id']),
        'access_key_secret_masked': web_config.mask_key(cfg['access_key_secret']),
    }


# ────────────────── 页面与静态资源 ──────────────────

@app.get('/')
def index():
    return FileResponse(os.path.join(BASE_DIR, 'static', 'index.html'))


app.mount('/static', StaticFiles(directory=os.path.join(BASE_DIR, 'static')), name='static')


# ────────────────── API ──────────────────

@app.get('/api/templates')
def api_templates():
    return {'templates': list_templates()}


@app.post('/api/upload')
async def api_upload(file: UploadFile = File(...)):
    _cleanup_expired()
    filename = file.filename or 'upload'
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f'不支持的文件格式 {ext}，支持 PDF / Word / 图片')

    doc_id = uuid.uuid4().hex[:12]
    save_dir = os.path.join(web_config.UPLOADS_DIR, doc_id)
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, f'source{ext}')
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(400, '文件超过 100MB 限制')
    with open(save_path, 'wb') as f:
        f.write(content)

    doc = LoadedDocument(doc_id, save_path)
    try:
        doc.open()
    except Exception as e:
        raise HTTPException(400, f'文件打开失败: {e}')

    with _lock:
        _docs[doc_id] = {'doc': doc, 'name': filename, 'ts': time.time()}
    return {
        'doc_id': doc_id,
        'name': filename,
        'doc_type': doc.doc_type,
        'is_text_based': doc.is_text_based,
        'page_count': doc.page_count,
    }


@app.get('/api/doc/{doc_id}/page/{page_num}.png')
def api_page(doc_id: str, page_num: int):
    doc = _get_doc(doc_id)
    png = doc.page_png(page_num, dpi=web_config.PREVIEW_DPI)
    if png is None:
        raise HTTPException(404, '页面不存在')
    tmp = os.path.join(web_config.UPLOADS_DIR, doc_id, f'preview_{page_num}.png')
    with open(tmp, 'wb') as f:
        f.write(png)
    return FileResponse(tmp, media_type='image/png')


@app.post('/api/check')
def api_check(req: CheckRequest):
    doc = _get_doc(req.doc_id)
    if not req.templates:
        raise HTTPException(400, '请至少选择一个校验模板')
    cfg = web_config.load_api_config()

    task_id = uuid.uuid4().hex[:12]
    with _lock:
        _tasks[task_id] = {'status': 'running', 'progress': '排队中...', 'result': None,
                           'error': None, 'ts': time.time()}

    def _run():
        def set_progress(msg: str):
            with _lock:
                if task_id in _tasks:
                    _tasks[task_id]['progress'] = msg

        try:
            engine = cfg.get('engine') or web_config.DEFAULT_ENGINE
            check_results = []
            docmind_data = getattr(doc, '_docmind_data', None)

            def ensure_docmind():
                nonlocal docmind_data
                if docmind_data is None:
                    docmind_data = parse_document(
                        doc, cfg, progress=lambda m: set_progress(f'[DocMind] {m}'))
                    doc._docmind_data = docmind_data
                return docmind_data

            for ti, tname in enumerate(req.templates):
                template = load_template(tname)
                if template is None:
                    check_results.append({'template': tname, 'error': '模板文件不存在'})
                    continue
                display = template.get('title') or tname
                try:
                    if engine == 'ai_vision':
                        set_progress(f'[{ti + 1}/{len(req.templates)}] AI 提取「{display}」字段...')
                        extracted = extract_fields(
                            doc, template, cfg['api_key'], cfg['base_url'], cfg['model'],
                            progress=lambda m: set_progress(f'[{ti + 1}/{len(req.templates)}] {m}'))
                    else:
                        set_progress(f'[{ti + 1}/{len(req.templates)}] DocMind 识别报告...')
                        parsed = ensure_docmind()
                        set_progress(f'[{ti + 1}/{len(req.templates)}] 本地规则抽取「{display}」字段...')
                        extracted = extract_fields_local(
                            parsed, template,
                            progress=lambda m: set_progress(f'[{ti + 1}/{len(req.templates)}] {m}'))
                    set_progress(f'[{ti + 1}/{len(req.templates)}] 校验「{display}」规则...')
                    outcome = check_rules(template, extracted)
                    check_results.append({
                        'template': tname,
                        'display': display,
                        'standard': template.get('standard', ''),
                        'engine': engine,
                        'extracted': extracted,
                        **outcome,
                    })
                except (AIParseError, DocMindError) as e:
                    check_results.append({'template': tname, 'display': display, 'error': str(e)})
                except Exception as e:
                    check_results.append({'template': tname, 'display': display,
                                          'error': f'处理异常: {e}'})
            with _lock:
                _tasks[task_id].update({
                    'status': 'done',
                    'progress': '完成',
                    'result': {'checks': check_results},
                })
        except Exception as e:
            traceback.print_exc()
            with _lock:
                _tasks[task_id].update({'status': 'error', 'error': str(e)})

    threading.Thread(target=_run, daemon=True).start()
    return {'task_id': task_id}


@app.get('/api/task/{task_id}')
def api_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(404, '任务不存在或已过期')
    return {k: task[k] for k in ('status', 'progress', 'result', 'error')}


@app.get('/api/config')
def api_get_config():
    return _config_view(web_config.load_api_config())


@app.post('/api/config')
def api_set_config(req: ConfigRequest):
    cfg = web_config.save_api_config(
        provider=req.provider,
        api_key=req.api_key,
        base_url=req.base_url,
        model=req.model,
        access_key_id=req.access_key_id,
        access_key_secret=req.access_key_secret,
        engine=req.engine,
    )
    return _config_view(cfg)


@app.post('/api/config/test')
def api_test_config():
    """按当前识别引擎验证配置：DocMind 校验 AK/SK，视觉模型校验 API Key"""
    cfg = web_config.load_api_config()
    if (cfg.get('engine') or web_config.DEFAULT_ENGINE) == 'docmind':
        ok, message = check_credentials(cfg)
        return {'ok': ok, 'message': message}

    if not cfg['api_key']:
        return {
            'ok': False,
            'message': '未配置 API Key。阿里云 AccessKey（LTAI 开头）不能直接调用百炼大模型，'
                       '请到百炼控制台创建以 sk- 开头的 API Key 后填入。',
        }
    if not cfg['base_url']:
        return {'ok': False, 'message': '未填写 Base URL'}
    if not cfg['model']:
        return {'ok': False, 'message': '未填写模型名称'}

    import requests
    try:
        resp = requests.post(
            cfg['base_url'].rstrip('/') + '/chat/completions',
            headers={'Authorization': f"Bearer {cfg['api_key']}",
                     'Content-Type': 'application/json'},
            json={
                'model': cfg['model'],
                'messages': [{'role': 'user', 'content': '回复 OK'}],
                'max_tokens': 8,
            },
            timeout=30,
        )
    except Exception as e:
        return {'ok': False, 'message': f'连接失败：{e}'}

    if resp.status_code == 200:
        try:
            text = resp.json()['choices'][0]['message']['content']
        except Exception:
            text = ''
        return {'ok': True, 'message': f'连接成功，模型回复：{str(text).strip()[:40] or "（空）"}'}

    detail = resp.text.strip().replace('\n', ' ')[:200]
    if resp.status_code == 401:
        return {'ok': False, 'message': f'鉴权失败（401）：API Key 无效。{detail}'}
    if resp.status_code == 402:
        return {'ok': False, 'message': f'账户余额不足（402），请先充值。{detail}'}
    return {'ok': False, 'message': f'接口返回 {resp.status_code}：{detail}'}


@app.exception_handler(Exception)
async def global_exc_handler(request, exc):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})
    traceback.print_exc()
    return JSONResponse(status_code=500, content={'detail': f'服务器内部错误: {exc}'})


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
