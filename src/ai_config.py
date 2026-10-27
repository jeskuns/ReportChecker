"""
AI 视觉模型识别配置（桌面版）

模型名称不写死，全部从 ai_config.json 读取，可在「设置 → AI 模型设置」中修改。
"""

import json
import os

from config import PROJECT_ROOT

AI_CONFIG_FILE = os.path.join(PROJECT_ROOT, 'ai_config.json')

# 常用视觉模型服务商预设（均为 OpenAI 兼容 /chat/completions 接口）
PROVIDER_PRESETS = {
    'qwen': {
        'label': '通义千问（阿里百炼）',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'models': ['qwen-vl-max', 'qwen-vl-plus', 'qwen2.5-vl-72b-instruct'],
        'note': 'API Key 以 sk- 开头，在百炼控制台创建',
    },
    'doubao': {
        'label': '豆包（火山方舟）',
        'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
        'models': ['doubao-1-5-vision-pro-32k-250115', 'doubao-1-5-vision-lite-250315'],
        'note': '模型名也可填方舟接入点 ID（ep- 开头）',
    },
    'zhipu': {
        'label': '智谱 GLM-4V',
        'base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'models': ['glm-4v-plus', 'glm-4v-flash'],
        'note': 'glm-4v-flash 免费但精度较低',
    },
    'moonshot': {
        'label': '月之暗面 Kimi',
        'base_url': 'https://api.moonshot.cn/v1',
        'models': ['kimi-latest', 'moonshot-v1-8k-vision-preview'],
        'note': '需选择支持图片输入的模型',
    },
    'openai': {
        'label': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
        'models': ['gpt-4o-mini', 'gpt-4o'],
        'note': '国内网络需自备代理',
    },
    'deepseek': {
        'label': 'DeepSeek V4 Flash（辅助）',
        'base_url': 'https://api.deepseek.com/v1',
        'models': ['deepseek-flash', 'deepseek-v4-pro'],
        'note': 'deepseek-flash 支持图片输入；需账户有余额',
    },
    'siliconflow': {
        'label': '硅基流动 SiliconFlow',
        'base_url': 'https://api.siliconflow.cn/v1',
        'models': ['Qwen/Qwen2.5-VL-72B-Instruct'],
        'note': '兼容通义千问视觉模型',
    },
    'custom': {
        'label': '自定义（OpenAI 兼容）',
        'base_url': '',
        'models': [],
        'note': '填写任意 OpenAI 兼容接口地址',
    },
}

# 默认值：地址与模型默认硅基流动，全部可在设置里修改
DEFAULT_AI_CONFIG = {
    'base_url': PROVIDER_PRESETS['siliconflow']['base_url'],
    'ocr_model': PROVIDER_PRESETS['siliconflow']['models'][0],
    'extract_model': PROVIDER_PRESETS['siliconflow']['models'][0],
    'api_key': '',
    'timeout': 120,
}


def load_ai_config() -> dict:
    cfg = dict(DEFAULT_AI_CONFIG)
    if os.path.exists(AI_CONFIG_FILE):
        try:
            with open(AI_CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            for k in DEFAULT_AI_CONFIG:
                if saved.get(k) not in (None, ''):
                    cfg[k] = saved[k]
        except Exception:
            pass
    # 环境变量优先，便于批量部署时统一指定模型
    if os.environ.get('AI_VISION_BASE_URL'):
        cfg['base_url'] = os.environ['AI_VISION_BASE_URL'].strip()
    if os.environ.get('AI_OCR_MODEL'):
        cfg['ocr_model'] = os.environ['AI_OCR_MODEL'].strip()
    if os.environ.get('AI_EXTRACT_MODEL'):
        cfg['extract_model'] = os.environ['AI_EXTRACT_MODEL'].strip()
    if os.environ.get('AI_VISION_API_KEY'):
        cfg['api_key'] = os.environ['AI_VISION_API_KEY'].strip()
    return cfg


def save_ai_config(base_url: str = None, ocr_model: str = None,
                   extract_model: str = None, api_key: str = None,
                   timeout: int = None) -> dict:
    """保存配置；参数为 None 表示不修改，空字符串表示清空"""
    cfg = dict(DEFAULT_AI_CONFIG)
    if os.path.exists(AI_CONFIG_FILE):
        try:
            with open(AI_CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    if base_url is not None:
        cfg['base_url'] = base_url.strip()
    if ocr_model is not None:
        cfg['ocr_model'] = ocr_model.strip()
    if extract_model is not None:
        cfg['extract_model'] = extract_model.strip()
    if api_key is not None:
        cfg['api_key'] = api_key.strip()
    if timeout is not None:
        cfg['timeout'] = int(timeout)
    with open(AI_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def mask_key(key: str) -> str:
    if not key:
        return ''
    if len(key) <= 8:
        return key[:2] + '****'
    return f'{key[:4]}****{key[-4:]}'


def is_configured(cfg: dict = None) -> bool:
    cfg = cfg or load_ai_config()
    return bool(cfg.get('api_key') and cfg.get('base_url')
                and cfg.get('ocr_model') and cfg.get('extract_model'))
