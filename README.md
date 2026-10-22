# ReportChecker — 电动工具测试报告校验工具

> Power Tool Test Report Checker
> 桌面版：纯本地运行 · 多引擎 OCR 级联 · 模板驱动校验
> Web 版：网页端 / 手机端 · 阿里云 DocMind 解析 PDF 与图片 · 模板驱动校验

---

## 两种运行形态

| 形态 | 入口 | 文档解析方式 | 适用场景 |
|------|------|-------------|---------|
| **桌面版** | 双击根目录 `run.bat` | 本地多引擎 OCR 级联（PaddleOCR / RapidOCR / Tesseract / EasyOCR），可手动切换 AI 视觉模型 | 无网络、涉密环境；大批量本地处理 |
| **本机网页版** | 双击 `webapp\run_web.bat` | 阿里云 DocMind（AK/SK）解析 PDF / 图片 / Word，可选视觉大模型 | 局域网内电脑 / 手机访问 |
| **在线网页版** | Cloudflare 部署（见下文） | 两段式：视觉模型 OCR → 大模型抽取字段 | 任何网络下的手机、电脑，打开网址即用 |

> **在线地址**：https://reportchecker.cultured-papaya.workers.dev  
> **入口说明**：`run.bat` 只启动桌面版；本机网页版是独立的 `webapp\run_web.bat`；
> 在线版部署在 Cloudflare，无需本机开机，手机电脑直接访问网址即可。

**在线版识别逻辑（两段式）**：

```
上传 PDF / 照片
   ↓ 浏览器用 pdf.js 渲染页面（不上传原始文件）
第 1 段：视觉模型 OCR     页面图像 → 文字（表格按行、单元格用 | 分隔）
第 2 段：大模型字段抽取    文字 + 模板字段定义 → JSON
   ↓
前端本地规则引擎校验（公式 / 限值 / 容差）
```

识别与抽取模型都在 Worker 端调用，API Key 只存在服务端，不会下发到浏览器。

两个版本共用同一套 `templates/` 校验模板与规则语义，校验结论一致。

---

## 功能概述

本工具用于自动校验电动工具安规测试报告（PDF / Word / 图片），支持四大标准系列：

| 标准系列 | 引用标准 | 测试类型 | 模板数量 |
|---------|---------|---------|---------|
| **GB 3883.1-2014** (通用/手持/可移式/园林) | IEC 62841-1:2014 | 温升、耐压、接地、泄漏电流、功率、机械强度等 | 36 个 |
| **GB/T 4208-2017** (外壳防护) | IEC 60529 | IP 防护等级 | 1 个 |
| **GB 4343.1-2024** (电磁兼容发射) | CISPR 14-1 | EMC 发射 | 1 个 |
| **GB 17625.1-2023** (谐波) | IEC 61000-3-2 | 谐波电流、电压波动和闪烁 | 2 个 |

**核心校验逻辑**：
- **计算校验**：ΔT = T_hot - T_room，与报告记录值对比
- **限值校验**：温升 ≤ 标准限值、耐压 ≥ 标准电压等
- **容差校验**：实测值与标准值的偏差检查

---

## 桌面版界面布局

```
┌──────────────────────────┬─────────────────────────────┐
│  菜单栏                   │                              │
├──────────────────────────┼─────────────────────────────┤
│                          │  ┌─ 标准分类 Tab ──────────┐ │
│  📄 文件名 | 类型 | 文字型  │  │ 测试项1 │ 测试项2 │ ... │ │
│                          │  ├─────────────────────────┤ │
│  ┌────────────────────┐  │  │                         │ │
│  │                    │  │  │  异常列表 / 校验结果      │ │
│  │   PDF 页面渲染      │  │  │                         │ │
│  │                    │  │  │  [开始校验] 按钮          │ │
│  │                    │  │  │                         │ │
│  └────────────────────┘  │  └─────────────────────────┘ │
│                          │                              │
│  ‹ 1/5 › 页 识别当前页   │  当前模型：[PaddleOCR] [...]  │
│  − 100% + 适应 ☐识别框   │                              │
│              ⚡一键识别   │                              │
├──────────────────────────┴─────────────────────────────┤
│  状态栏：就绪                                            │
└─────────────────────────────────────────────────────────┘
```

### 底部控制栏详解

| 控件 | 位置 | 功能 |
|------|------|------|
| `‹` `›` 翻页按钮 | 左侧 | 上/下一页 |
| `1/5` 页码显示 | 左侧 | 当前页 / 总页数 |
| 页码输入框 | 左侧 | 输入页码回车跳转 |
| **「识别当前页」** | **左侧（页码旁）** | **OCR 识别当前查看的页面，用于逐页精细查看** |
| `−` `+` 缩放 | 中间 | 缩小/放大页面显示 |
| `适应` | 中间 | 恢复适应窗口大小 |
| `☐ 识别框` | 中间 | 切换是否显示 OCR 识别框（含文字标注） |
| **「⚡ 一键识别」** | **右侧（红色醒目）** | **识别整个文档所有页面，无需逐页操作** |
| 模型下拉框 | 右侧 | 选择自动级联 / 指定本地 OCR 引擎 / **AI 视觉模型** |

---

## 技术架构

### 文档识别策略（多格式 + 多引擎自动分流）

```
打开文件 → 格式检测
├── PDF（文字型）→ 方法1：PyMuPDF 直接文本提取（最快、100% 准确）
├── PDF（图片型）/ 图片文件 → OCR 级联链（一种失败自动切换下一种）
│       ├── RapidOCR (ONNX)              ← 首选，轻量无依赖
│       ├── EasyOCR                       ← 备选1，中文优化
│       ├── Tesseract OCR (便携版)        ← 备选2，多语言支持
│       ├── PaddleOCR (paddlepaddle)      ← 备选3，高精度
│       └── 增强预处理兜底                 ← 低质量图片
└── Word (.docx) → python-docx 直接提取文本
```

> 底部「模型」手动切到 **「AI 视觉模型」** 时，图片型页面改由视觉大模型识别（仅手动生效，不参与自动级联）。

### 技术栈

| 组件 | 用途 | 版本 |
|------|------|------|
| PyQt6 | GUI 界面 | 6.x |
| PyMuPDF (fitz) | PDF 渲染与文本提取 | 1.24+ |
| python-docx | Word 文本提取 | 1.1+ |
| PaddleOCR + PaddlePaddle | 主力 OCR 引擎（中文） | 3.7 / 3.0-beta |
| RapidOCR + onnxruntime | 轻量 OCR 引擎 | latest |
| EasyOCR | 备用 OCR 引擎 | 1.7+ |
| Tesseract OCR | 备用 OCR 引擎 | 5.4 (便携版) |
| OpenCV + Pillow | 图像预处理/增强 | 4.10 / latest |
| PyInstaller | EXE 打包 | 6.21 |

### Web 版技术栈

| 组件 | 用途 | 版本 |
|------|------|------|
| FastAPI + Uvicorn | 后端 Web 服务 | 0.110+ / 0.29+ |
| 阿里云 DocMind（默认） | 文档智能 OCR，AK/SK 鉴权，扫描件转文本与表格 | SDK 1.4+ |
| 本地规则抽取 | 从 DocMind 结果按模板标签/表头抽取字段，无需大模型 | — |
| 通义千问 qwen-vl-max（可选） | 视觉大模型解析，支持豆包 / 智谱 / Kimi / OpenAI 等兼容接口 | — |
| PyMuPDF (fitz) | PDF 页面渲染、图片转 PDF、文本层提取 | 1.23+ |
| python-docx | Word 文本提取 | 1.1+ |
| 原生 HTML / CSS / JS | 响应式前端（电脑 + 手机同一套页面） | — |

### Web 版文档解析策略

```
上传文件
├── PDF（文字型 / 扫描型）─┐
├── Word (.docx) ──────────┼→ DocMind 文档智能解析（AK/SK）
└── 图片 → 转 PDF ─────────┘        ↓
                         文本 + 表格（HTML 表格转行）
                                    ↓
                     本地规则按模板标签/表头抽取字段
                                    ↓
                     本地规则引擎校验（公式 / 限值 / 容差）
```

> **可选**：设置中把识别引擎切到「视觉大模型」，则跳过 DocMind，直接将页面图像发给
> 通义千问等模型抽取字段（需 `sk-` 开头的 API Key）。

> **关键设计**：识别只负责「读文档」，是否合格由本地规则引擎判定，结果可复核、可追溯，不依赖模型自行下结论。

---

## 项目结构

```
ReportChecker/
├── run.bat                 # 一键启动脚本
├── run.py                  # 源码模式启动器
├── requirements.txt        # Python 依赖
├── ReportChecker.spec      # PyInstaller 打包配置
├── README.md               # 本文件
├── 项目汇报.md              # 项目汇报文档
├── src/                    # 源代码
│   ├── main.py             # 入口
│   ├── launcher.py         # EXE 打包模式入口
│   ├── gui_app.py          # GUI（PDF视图、Tab切换、OCR识别、一键全检）
│   ├── core_checker.py     # 核心引擎（DocumentLoader + 5引擎OCR级联）
│   ├── ai_ocr.py           # AI 视觉模型识别引擎（手动选择时使用）
│   ├── ai_config.py        # AI 模型配置（地址 / 模型 / Key，模型名不写死）
│   ├── config.py           # 配置管理（标准分类、模板路径、限值）
│   ├── utils.py            # 工具函数（数值解析、容差检查）
│   └── coordinate_tool.py  # PDF 坐标测量工具（独立运行）
├── templates/              # JSON 校验模板（按标准章节命名）
│   ├── GB3883/             # 通用安全（按章节：clause11/12/20/26、appendix_c/d）
│   ├── GB3883/GB3883_2XX/  # 手持式专用（20种工具）
│   ├── GB3883/GB3883_3XX/  # 可移式专用（8种工具）
│   ├── GB3883/GB3883_4XX/  # 园林工具
│   ├── GB4208/             # 外壳防护等级（IP）
│   ├── GB4343/             # EMC 发射
│   └── GB17625/            # 谐波/闪烁
├── scripts/                # 辅助脚本
│   ├── pdf_to_word.py      # PDF → Word 转换
│   └── gen_heating_excel.py # 温升模板 Excel 生成器
├── deps/                   # 本地依赖（无需系统安装）
│   └── tesseract/          # Tesseract OCR 便携版
├── models/                 # OCR 模型（paddle_det/paddle_rec/rapid/easyocr）
├── result/                 # 校验结果输出目录
├── webapp/                 # Web 版（网页端 / 手机端）
│   ├── run_web.bat         # 一键启动脚本
│   ├── server.py           # FastAPI 服务与接口
│   ├── doc_loader.py       # PDF / Word / 图片 → 页面图像与文本（预览、视觉模型用）
│   ├── docmind_ocr.py      # 阿里云 DocMind 解析（AK/SK，默认识别引擎）
│   ├── rule_extract.py     # 本地规则抽取字段（从 DocMind 文本/表格）
│   ├── ai_parser.py        # 视觉大模型按模板提取字段（可选引擎）
│   ├── rule_engine.py      # 模板加载 + 规则校验引擎
│   ├── web_config.py       # 路径、引擎与服务商预设、API 配置
│   ├── requirements.txt    # Web 版依赖
│   ├── static/             # 响应式前端（index.html / style.css / app.js）
│   ├── uploads/            # 上传文件临时目录（自动清理，不入库）
│   └── api_config.json     # AI Key 配置（运行时生成，不入库）
├── build/ / dist/          # PyInstaller 构建产物
└── venv/                   # Python 虚拟环境
```

---

## 环境要求

### 桌面版
- **Python 3.11**（推荐，PaddleOCR 兼容性最佳）
- Windows 10/11 x64

### Web 版
- **Python 3.10+**（无需安装 PaddleOCR 等本地 OCR 依赖）
- 可访问阿里百炼接口的网络
- 手机端只需浏览器，无需安装 App

### 桌面版安装步骤

```bash
# 1. 安装 Python 3.11（勾选 "Add Python to PATH"）

# 2. 创建虚拟环境并安装依赖
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 3. 启动程序
run.bat
```

### Web 版安装步骤

```bash
# 1. 安装依赖（轻量，仅 FastAPI / PyMuPDF / requests 等）
python -m pip install -r webapp\requirements.txt

# 2. 启动服务（run_web.bat 会自动检查依赖）
webapp\run_web.bat
```

### 完全离线使用

本项目已将所有依赖本地化：
- **Tesseract OCR**：已包含在 `deps/tesseract/` 中（便携版）
- **PaddleOCR 模型**：已包含在 `models/ocr/paddle_det/` 和 `models/ocr/paddle_rec/` 中
- **RapidOCR 模型**：已包含在 `models/ocr/rapid/` 中
- **EasyOCR 模型**：已包含在 `models/ocr/easyocr/` 中

---

## 桌面版使用说明

### 基本流程
1. **双击 `run.bat`** 启动程序
2. **打开文件**：菜单栏 → 文件 → 打开文件（支持 PDF / Word / 图片）
3. **OCR 识别**：
   - **逐页查看**：用翻页按钮浏览各页，点击「识别当前页」对当前页做 OCR
   - **一键全识别**：点击右侧红色「⚡ 一键识别」，自动识别文档所有页面
4. **选择测试类型**：右侧 Tab 选择对应的测试项
5. **开始校验**：点击「开始校验」按钮
6. **查看结果**：异常列表用红/黄/绿三色标识

### 两种识别模式对比

| 模式 | 按钮位置 | 适用场景 |
|------|----------|---------|
| **识别当前页** | 左侧页码旁边 | 查看特定页的 OCR 结果，快速定位问题 |
| **⚡ 一键识别** | 底部右侧（红色） | 多页报告批量 OCR，一次性识别全部页面 |

> **注意**：文字型 PDF 无需 OCR，PyMuPDF 直接提取文本（毫秒级）。  
> 图片型 PDF 或图片文件才需要走 OCR 引擎级联识别。

### 使用 AI 模型识别（可选）

底部右侧「模型」下拉框除本地 OCR 引擎外，还提供 **「AI 视觉模型」**，可手动选择：

1. 菜单栏 → **设置 → AI 模型设置**
2. 选择服务商（地址自动填入），**模型名称可直接输入修改**，不写死任何模型
3. 填写 API Key（阿里百炼为 `sk-` 开头），点「测试连接」确认可用后保存
4. 把底部「模型」下拉框切到 **「AI 视觉模型」**
5. 点击「识别当前页」或「⚡ 一键识别」

说明：

- 服务商预置含 **DeepSeek V4 Flash**（`deepseek-flash`，支持图片输入），桌面端已预填其地址、模型与 Key，可直接选用
- AI 仅在手动选中时调用，**自动模式不会走 AI**，避免产生调用费用
- 配置保存在根目录 `ai_config.json`（已加入 `.gitignore`，不入库）
- 也可用环境变量统一指定：`AI_VISION_BASE_URL` / `AI_VISION_MODEL` / `AI_VISION_API_KEY`
- AI 只返回文字，不返回识别框，因此「识别框」高亮对 AI 模式不生效
- 若提示「账户余额不足（402）」，需先到对应平台充值

### 一键全检（校验）
- 打开文件并完成 OCR 后，选择对应测试项 Tab
- 点击「开始校验」按钮
- 自动加载模板 → 提取字段 → 执行规则校验
- 弹出异常列表，可导出结果

### 坐标测量工具
```bash
python src/coordinate_tool.py
```
用于在 PDF/图片上拖拽框选区域测量坐标，辅助制作模板。

### 温升模板 Excel 配置工具
```bash
python scripts/gen_heating_excel.py
```
生成 `温升模板配置.xlsx`，在 Excel 中填写详细的字段、坐标、限值和校验规则后，再生成 JSON 模板。

---

## Web 版使用说明（网页端 / 手机端）

### 1. 启动服务

```bash
cd webapp
run_web.bat
```

启动后控制台会输出访问地址：

- **电脑浏览器**：`http://127.0.0.1:8000`
- **手机浏览器**：`http://电脑局域网IP:8000`（手机与电脑连同一 WiFi）

> 用 `ipconfig` 查看电脑局域网 IP，例如 `http://192.168.1.100:8000`。  
> Windows 首次启动如弹出防火墙提示，请允许「专用网络」访问，否则手机连不上。

### 2. 配置识别凭证（首次必做）

打开页面右上角 **「识别与接口设置」**，顶部先选择 **识别引擎**（默认已选 DocMind）。

**引擎 A：阿里云 DocMind（默认，推荐）**

1. 填写阿里云 **AccessKey ID / Secret**（`LTAI` 开头）
2. 点击 **「测试连接」**，返回「AccessKey 校验通过」
3. 保存即可，**不需要** `sk-` 开头的百炼 API Key

> AccessKey 通过阿里云 OpenAPI 签名调用文档智能 DocMind，负责把扫描件解析成文本与表格；
> 字段抽取与判定全部在本地完成，报告内容不外传给大模型。
> 若用环境变量注入，`ALIYUN_AK` / `ALIYUN_SK` 优先级高于页面配置。

**引擎 B：视觉大模型（可选）**

选择「视觉大模型解析」后，需要：

1. 选择服务商（默认 **通义千问**），Base URL 与模型会自动填入预设值
2. 填写对应服务商的 **API Key**（阿里百炼为 `sk-` 开头）
3. 测试连接后保存

> **注意**：`LTAI` 开头的 AccessKey **不能**直接调用百炼大模型（会返回 401 invalid_api_key），
> 调用大模型必须使用控制台创建的 `sk-` 开头 API Key。

**内置服务商预设（均为 OpenAI 兼容 `/chat/completions` 接口）**：

| 服务商 | Base URL | 常用视觉模型 |
|--------|----------|-------------|
| 通义千问（默认） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-vl-max / qwen-vl-plus |
| 豆包（火山方舟） | `https://ark.cn-beijing.volces.com/api/v3` | doubao-1-5-vision-pro-32k |
| 智谱 GLM-4V | `https://open.bigmodel.cn/api/paas/v4` | glm-4v-plus / glm-4v-flash |
| 月之暗面 Kimi | `https://api.moonshot.cn/v1` | kimi-latest |
| OpenAI | `https://api.openai.com/v1` | gpt-4o-mini / gpt-4o |
| DeepSeek V4 Flash（辅助） | `https://api.deepseek.com/v1` | deepseek-flash / deepseek-v4-pro |
| 硅基流动 | `https://api.siliconflow.cn/v1` | Qwen2.5-VL-72B-Instruct |
| 自定义 | 任意 OpenAI 兼容地址 | 手动填写 |

> 模型名称不是写死的：预设值只是建议，**可直接编辑成任意模型名**，也可用环境变量
> `AI_VISION_MODEL` / `AI_VISION_BASE_URL` / `AI_VISION_API_KEY` 覆盖默认值。
>
> **DeepSeek V4 Flash**：`deepseek-flash` 支持图片输入，可作为辅助识别模型。
> Key 已按服务商单独保存在 `provider_keys` 中，切换服务商会自动带出，互不覆盖。
> 若返回 `402 Insufficient Balance`，说明该 DeepSeek 账户余额为 0，需先充值。

> 视觉引擎也可用环境变量注入 Key，优先级高于页面配置：
> ```powershell
> $env:DASHSCOPE_API_KEY = "sk-xxxx"
> ```
> 配置保存在 `webapp/api_config.json`（已加入 `.gitignore`，不会入库）。

### 3. 校验流程

1. **上传报告**：点击/拖入 PDF、Word 或图片；手机端可直接调用相机拍照
2. **预览确认**：左侧可翻页查看页面，确认传对了文件
3. **选择测试项目**：右侧勾选一个或多个模板（可多选批量校验）
4. **开始校验**：DocMind 识别文档 → 本地规则抽取字段 → 规则引擎判定
5. **查看结果**：每个模板显示 通过 / 警告 / 不通过 统计与逐条明细，可展开查看提取的原始数据

### 4. 识别引擎对比

| | DocMind + 本地规则（默认） | 视觉大模型 |
|---|---|---|
| 凭证 | 阿里云 AccessKey（LTAI） | API Key（sk-） |
| 报告外传 | 仅传阿里云 DocMind 做 OCR | 页面图像发送给所选模型 |
| 字段抽取 | 本地按标签/表头匹配 | 模型按模板字段理解 |
| 复杂表格 | 依赖表格结构与标签规范 | 理解力更强，适应性更好 |
| 成本 | DocMind 按量计费 | 按 token 计费 |

### 5. 结果判定说明

| 标记 | 含义 |
|------|------|
| ✓ 绿 | 规则通过（计算与记录一致、未超限值） |
| ! 黄 | 需人工关注（报告未记录该值、容差偏差） |
| ✗ 红 | 不通过（公式偏差超容差、超出标准限值、字段缺失） |

### 6. 接口一览（供二次开发）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/templates` | 可用模板列表 |
| POST | `/api/upload` | 上传报告，返回 `doc_id` |
| GET | `/api/doc/{doc_id}/page/{n}.png` | 页面预览图 |
| POST | `/api/check` | 提交校验任务（`doc_id` + 模板名数组） |
| GET | `/api/task/{task_id}` | 轮询任务进度与结果 |
| GET/POST | `/api/config` | 读取 / 保存识别引擎与接口配置 |
| POST | `/api/config/test` | 按当前引擎测试 DocMind AccessKey 或大模型 Key |

### 7. 运行说明与限制

- 上传文件保存在服务器临时目录，**2 小时后自动清理**
- 单文件上限 **100MB**
- DocMind 引擎需外网访问 `docmind-api.cn-hangzhou.aliyuncs.com`，单文档解析最长等待 **900 秒**
- 视觉引擎需外网访问所选模型服务；**离线环境请使用桌面版**
- 使用视觉引擎时报告图像会发送给模型服务商，涉密报告建议使用 DocMind 引擎或桌面版

---

## 在线网页版（Cloudflare）

### 目录结构

```
cloudflare/
├── src/index.js              # Worker：/api/health、/api/extract（两段式识别+抽取）
├── public/                   # 静态前端（顶部工具栏 + 左侧预览 + 右侧测试项目，手机自动上下排列）
│   ├── index.html
│   ├── style.css / app.js / rules.js
│   ├── templates.js          # 由 templates/ 自动生成
│   └── vendor/               # pdf.js（本地打包，不依赖外部 CDN）
├── scripts/build-templates.mjs   # 模板 → templates.js
├── scripts/copy-vendor.mjs       # 复制 pdf.js
└── wrangler.jsonc
```

### 本地调试

```bash
cd cloudflare
npm install
npm run dev        # 构建模板 + wrangler dev，默认 http://127.0.0.1:8787
```

本地调试时在 `cloudflare/.dev.vars` 写入 `AI_API_KEY=sk-xxx`（该文件不入库）。

### 部署

```bash
npx wrangler login          # 首次需要授权 Cloudflare 账号
cd cloudflare
npm run build
npx wrangler deploy
npx wrangler secret put AI_API_KEY   # 写入服务端密钥
```

未登录时可先用 `npx wrangler deploy --temporary` 得到一个临时预览地址（不会带密钥）。

### 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `AI_API_KEY` | 模型密钥，**用 secret 配置**，不下发浏览器 | — |
| `AI_BASE_URL` | OpenAI 兼容接口地址 | `https://api.deepseek.com/v1` |
| `OCR_MODEL` | 第一段识别模型（需支持图片输入） | `deepseek-flash` |
| `EXTRACT_MODEL` | 第二段字段抽取模型 | `deepseek-flash` |
| `ACCESS_CODE` | 可选访问码，防止接口被公开滥用 | 未设置 |

### 在线版限制

- 浏览器最多渲染 **10 页**，每批 4 页发送，避免请求体过大
- 原始 PDF 不上传，只上传渲染后的页面 JPEG，降低泄密风险
- 识别精度取决于模型；金额/限值等关键字段请人工复核

---

## 构建 EXE

```bash
# 使用 PyInstaller 打包
pyinstaller ReportChecker.spec

# 输出：dist/ReportChecker/ReportChecker.exe
```

**打包注意事项**：
- `ReportChecker.spec` 已配置好所有 hiddenimports 和数据目录
- 首次 EXE 运行可能较慢（PaddleOCR 模型加载约 30 秒）
- 确保 `deps/`、`models/`、`templates/` 目录与 EXE 在同一目录

---

## 模板格式

模板为 JSON 文件，定义表格字段与校验规则。**桌面版与 Web 版共用同一份模板**：
桌面版按坐标/OCR 取字段；Web 版 DocMind 引擎按 `description` 标签与 `headers` 表头匹配抽取，
视觉引擎则把字段定义作为 AI 提取指令。

```json
{
  "standard": "GB 3883.1-2014",
  "clause": "12",
  "title": "发热",
  "description": "温升试验",
  "version": "2.1",
  "tables": [
    {
      "title": "温升数值",
      "data_grid": true,
      "headers": [
        {"label": "转子 0.94倍"},
        {"label": "转子 1倍"},
        {"label": "定子 0.94倍"},
        {"label": "定子 1倍"}
      ],
      "fields": [
        {
          "name": "temperature_rise",
          "type": "number_array",
          "description": "温升Δt（K）报告值",
          "array_size": 4,
          "unit": "K"
        },
        {
          "name": "temperature_rise_calc",
          "type": "number_array",
          "description": "温升Δt（K）计算值",
          "array_size": 4,
          "unit": "K",
          "computed": true
        }
      ]
    }
  ],
  "rules": [
    {
      "type": "formula_verify",
      "description": "定子温升 0.94倍",
      "formula": "(stator_resistance_1 - stator_resistance_0) / stator_resistance_0 * (234.5 + start_room_temp) - (end_room_temp - start_room_temp)",
      "output_field": "temperature_rise_calc_0",
      "report_field": "temperature_rise_0",
      "tolerance_pct": 5.0
    },
    {
      "type": "limit",
      "description": "温升限值",
      "field": "temperature_rise",
      "operator": "<=",
      "value": 105
    }
  ]
}
```

**字段类型**：

| type | 说明 | 必备项 |
|------|------|-------|
| `number` | 单个数值 | `name`, `description` |
| `number_array` | 一行/一列的数值数组 | 另需 `array_size` |
| `text` | 文本（如「合格」「电阻法」） | `name`, `description` |
| `computed: true` | 计算值字段，无需报告记录 | 配合 `formula_verify` 使用 |

**规则类型**：

| type | 用途 | 关键参数 |
|------|------|---------|
| `formula_verify` | 公式计算值 vs 报告记录值 | `formula`, `output_field`, `report_field`, `tolerance_pct` |
| `limit` | 限值判定（支持数组逐元素） | `field`, `operator`, `value` |
| `tolerance` | 两个字段/数组差值判定 | `field_a`, `field_b`, `tolerance` |

> `report_field` / `output_field` 使用 `字段名_下标` 引用数组元素，例如 `temperature_rise_0` 表示 `temperature_rise` 数组第 1 个元素。

**新增测试项目**：在 `templates/` 下对应标准目录新增 JSON 即可，两个版本自动生效，无需改代码。

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v3.0 | 2026-10 | **新增 Web 版**：FastAPI + 响应式前端，电脑/手机浏览器可用；通义千问 qwen-vl 解析 PDF 与图片；AI 提取字段 + 本地规则引擎校验；支持多模板批量校验；API Key 页面内配置 |
| v2.2 | 2026-07 | 新增「一键识别」全文档 OCR；优化底部控制栏布局（识别当前页移至页码旁）；引擎标签启动即显示；EasyOCR 模型本地化 |
| v2.1 | 2026-07 | 新增 Word/图片格式支持、RapidOCR 引擎、标准引用修正(IEC 62841)、模板按章节重命名 |
| v2.0 | 2026-07 | 多引擎 OCR 级联架构、PDF 类型自动检测、一键全检、本地化部署 |
| v1.0 | 2025 | 初始版本，PaddleOCR 单引擎 |

---

## 作者

设计：王坤  
借助 AI 开发
