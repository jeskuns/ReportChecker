"""
Web 版配置模块
路径、AI 服务商预设与 API 配置
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, 'templates')
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
API_CONFIG_FILE = os.path.join(BASE_DIR, 'api_config.json')

os.makedirs(UPLOADS_DIR, exist_ok=True)

# 常用视觉（文字识别）模型预设：均为 OpenAI 兼容的 /chat/completions 接口
PROVIDER_PRESETS = {
    'qwen': {
        'label': '通义千问（阿里百炼）',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'models': ['qwen-vl-max', 'qwen-vl-plus', 'qwen2.5-vl-72b-instruct',
                   'qwen2.5-vl-32b-instruct'],
        'default_model': 'qwen-vl-max',
        'note': 'API Key 在百炼控制台创建，以 sk- 开头',
    },
    'doubao': {
        'label': '豆包（火山方舟）',
        'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
        'models': ['doubao-1-5-vision-pro-32k-250115', 'doubao-1-5-vision-lite-250315'],
        'default_model': 'doubao-1-5-vision-pro-32k-250115',
        'note': '模型名也可填方舟控制台的接入点 ID（ep- 开头）',
    },
    'zhipu': {
        'label': '智谱 GLM-4V',
        'base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'models': ['glm-4v-plus', 'glm-4v-flash'],
        'default_model': 'glm-4v-plus',
        'note': 'glm-4v-flash 免费但精度较低',
    },
    'moonshot': {
        'label': '月之暗面 Kimi',
        'base_url': 'https://api.moonshot.cn/v1',
        'models': ['kimi-latest', 'moonshot-v1-8k-vision-preview'],
        'default_model': 'kimi-latest',
        'note': '需选择支持图片输入的模型',
    },
    'openai': {
        'label': 'OpenAI',
        'base_url': 'https://api.openai.com/v1',
        'models': ['gpt-4o-mini', 'gpt-4o'],
        'default_model': 'gpt-4o-mini',
        'note': '国内网络需自备代理',
    },
    'deepseek': {
        'label': 'DeepSeek V4 Flash（辅助）',
        'base_url': 'https://api.deepseek.com/v1',
        'models': ['deepseek-flash', 'deepseek-v4-pro'],
        'default_model': 'deepseek-flash',
        'note': 'deepseek-flash 支持图片输入，可作辅助识别；需账户有余额',
    },
    'siliconflow': {
        'label': '硅基流动 SiliconFlow',
        'base_url': 'https://api.siliconflow.cn/v1',
        'models': ['Qwen/Qwen2.5-VL-72B-Instruct', 'Qwen/Qwen2.5-VL-32B-Instruct'],
        'default_model': 'Qwen/Qwen2.5-VL-72B-Instruct',
        'note': '兼容通义千问视觉模型，按 token 计费',
    },
    'custom': {
        'label': '自定义（OpenAI 兼容）',
        'base_url': '',
        'models': [],
        'default_model': '',
        'note': '填写任意 OpenAI 兼容接口地址，如自建服务、OneAPI 网关',
    },
}

DEFAULT_PROVIDER = 'qwen'

# 识别引擎：docmind（AK/SK + 本地规则，默认）/ ai_vision（视觉大模型）
ENGINES = {
    'docmind': {
        'label': '阿里云 DocMind 解析 + 本地规则抽取',
        'note': '使用 AccessKey 调用文档智能 OCR，再由规则引擎抽取字段，无需 sk- API Key',
    },
    'ai_vision': {
        'label': '视觉大模型解析',
        'note': '把页面图像发给视觉大模型抽取字段，需要所选服务商的 API Key',
    },
}
DEFAULT_ENGINE = 'docmind'

# 默认 API 配置：默认使用 DocMind + 通义千问（备用）
# 模型名称不写死：优先取环境变量 AI_VISION_MODEL，否则取服务商预设，仍可在页面修改
DEFAULT_API_CONFIG = {
    'engine': DEFAULT_ENGINE,
    'provider': DEFAULT_PROVIDER,
    'base_url': os.environ.get('AI_VISION_BASE_URL')
                or PROVIDER_PRESETS[DEFAULT_PROVIDER]['base_url'],
    'model': os.environ.get('AI_VISION_MODEL')
             or PROVIDER_PRESETS[DEFAULT_PROVIDER]['default_model'],
    'api_key': os.environ.get('AI_VISION_API_KEY', ''),
    'access_key_id': '',
    'access_key_secret': '',
    # 按服务商分别保存的 Key：切换服务商时自动带出对应 Key
    'provider_keys': {},
}

# 阿里云文档智能 DocMind
DOCMIND_ENDPOINT = os.environ.get('DOCMIND_ENDPOINT', 'docmind-api.cn-hangzhou.aliyuncs.com')
DOCMIND_TIMEOUT = 900          # 单文档解析超时（秒）
DOCMIND_POLL_INTERVAL = 5      # 轮询间隔（秒）

# 文档在服务器上的保留时间（秒）
DOC_TTL = 2 * 3600

# AI 解析参数
RENDER_DPI = 200            # 发送给 AI 的页面渲染清晰度
PREVIEW_DPI = 110           # 前端预览清晰度
MAX_PAGES_PER_CALL = 6      # 每次请求最多携带的页面图像数
MAX_PAGES_TOTAL = 20        # 单文档最多解析页数
REQUEST_TIMEOUT = 180       # API 请求超时（秒）


def list_providers() -> list:
    """返回服务商预设（供前端下拉框使用）"""
    return [{'key': k, **v} for k, v in PROVIDER_PRESETS.items()]


def load_api_config() -> dict:
    """加载 API 配置：环境变量优先于配置文件"""
    cfg = dict(DEFAULT_API_CONFIG)
    if os.path.exists(API_CONFIG_FILE):
        try:
            with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            for k in DEFAULT_API_CONFIG:
                if saved.get(k):
                    cfg[k] = saved[k]
        except Exception:
            pass
    # 按服务商带出各自的 Key（切换服务商无需重新粘贴）
    provider_key = (cfg.get('provider_keys') or {}).get(cfg['provider'], '')
    if provider_key:
        cfg['api_key'] = provider_key
    env_key = os.environ.get('DASHSCOPE_API_KEY', '').strip()
    if env_key:
        cfg['api_key'] = env_key
    return cfg


def list_engines() -> list:
    return [{'key': k, **v} for k, v in ENGINES.items()]


def save_api_config(provider: str = None,
                    api_key: str = None,
                    base_url: str = None,
                    model: str = None,
                    access_key_id: str = None,
                    access_key_secret: str = None,
                    engine: str = None) -> dict:
    """保存 API 配置；参数为 None 表示不修改，空字符串表示清空"""
    cfg = dict(DEFAULT_API_CONFIG)
    if os.path.exists(API_CONFIG_FILE):
        try:
            with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg.update(json.load(f))
        except Exception:
            pass

    if engine is not None and engine in ENGINES:
        cfg['engine'] = engine
    if provider is not None and provider in PROVIDER_PRESETS:
        cfg['provider'] = provider
    if base_url is not None:
        cfg['base_url'] = base_url.strip()
    if model is not None:
        cfg['model'] = model.strip()
    if api_key is not None:
        cfg['api_key'] = api_key.strip()
        # 同时按服务商留存，切换服务商时自动带出
        keys = dict(cfg.get('provider_keys') or {})
        keys[cfg['provider']] = cfg['api_key']
        cfg['provider_keys'] = keys
    if access_key_id is not None:
        cfg['access_key_id'] = access_key_id.strip()
    if access_key_secret is not None:
        cfg['access_key_secret'] = access_key_secret.strip()

    with open(API_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return load_api_config()


def mask_key(key: str) -> str:
    if not key:
        return ''
    if len(key) <= 8:
        return key[:2] + '****'
    return f"{key[:4]}****{key[-4:]}"
