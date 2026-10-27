"""
国内下载镜像地址（全部为国内可直连源）

一键安装只使用这里列出的地址：
  - Python 运行时：华为云 / npmmirror / 阿里云
  - pip 依赖：清华 TUNA / 阿里云 PyPI
  - get-pip.py：阿里云
  - RapidOCR 模型：ModelScope（阿里系）
  - PaddleOCR 模型：百度飞桨 BOS
"""

# (名称, 索引地址)，按顺序尝试
PYPI_INDEXES = [
    ('清华 TUNA', 'https://pypi.tuna.tsinghua.edu.cn/simple'),
    ('阿里云', 'https://mirrors.aliyun.com/pypi/simple'),
]

# 嵌入式 Python 3.11（amd64）压缩包
PYTHON_EMBED = [
    ('华为云', '3.11.9',
     'https://mirrors.huaweicloud.com/python/3.11.9/python-3.11.9-embed-amd64.zip'),
    ('npmmirror', '3.11.9',
     'https://registry.npmmirror.com/-/binary/python/3.11.9/python-3.11.9-embed-amd64.zip'),
    ('阿里云', '3.11.9',
     'https://mirrors.aliyun.com/python-release/windows/python-3.11.9-embed-amd64.zip'),
]

GET_PIP = [
    ('阿里云', 'https://mirrors.aliyun.com/pypi/get-pip.py'),
]

# RapidOCR 的 3 个 ONNX 模型（ModelScope，文件大小与官方一致）
MODELSCOPE_RAPID_BASE = (
    'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/master/onnx/PP-OCRv4/'
)

# PaddleOCR 官方推理模型（百度 BOS，国内直连）
PADDLE_BOS_BASE = (
    'https://paddle-model-ecology.bj.bcebos.com/paddlex/'
    'official_inference_model/paddle3.0.0/'
)
