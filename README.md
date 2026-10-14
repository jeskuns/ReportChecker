# ReportChecker — 电动工具测试报告校验工具

> Power Tool Test Report Checker
> 纯本地运行 · 多引擎 OCR 级联 · 模板驱动校验 · 多格式支持

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

## 界面布局

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
├── build/ / dist/          # PyInstaller 构建产物
└── venv/                   # Python 虚拟环境
```

---

## 环境要求

### 开发环境
- **Python 3.11**（推荐，PaddleOCR 兼容性最佳）
- Windows 10/11 x64

### 安装步骤

```bash
# 1. 安装 Python 3.11（勾选 "Add Python to PATH"）

# 2. 创建虚拟环境并安装依赖
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 3. 启动程序
run.bat
```

### 完全离线使用

本项目已将所有依赖本地化：
- **Tesseract OCR**：已包含在 `deps/tesseract/` 中（便携版）
- **PaddleOCR 模型**：已包含在 `models/ocr/paddle_det/` 和 `models/ocr/paddle_rec/` 中
- **RapidOCR 模型**：已包含在 `models/ocr/rapid/` 中
- **EasyOCR 模型**：已包含在 `models/ocr/easyocr/` 中

---

## 使用说明

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

模板为 JSON 文件，定义字段坐标和校验规则：

```json
{
  "meta": {
    "name": "温升测试",
    "version": "1.0",
    "standard": "GB 3883.1-2014",
    "clause": "第12章 发热",
    "description": "GB 3883.1 温升测试校验",
    "match_keywords": ["温升", "发热", "绕组温度"]
  },
  "pages": [
    {"page_num": 0, "description": "封面/测试信息页"},
    {"page_num": 1, "description": "测试数据页"}
  ],
  "tables": [
    {
      "table_name": "cover_info",
      "page_num": 0,
      "description": "封面基本信息表",
      "type": "key_value",
      "fields": [
        {"field_name": "report_no", "row": 0, "col": 1, "description": "报告编号", "type": "text"}
      ]
    }
  ],
  "fields": [
    {
      "field_name": "stator_rise",
      "page_num": 1,
      "rect": [100, 200, 200, 230],
      "type": "number",
      "unit": "K",
      "description": "定子温升"
    }
  ],
  "rules": [
    {
      "type": "limit",
      "field_name": "stator_rise",
      "limit": 80,
      "operator": "<=",
      "unit": "K",
      "message": "定子温升超过限值 80K"
    }
  ],
  "limits": {
    "stator_max": 80.0,
    "rotor_max": 95.0
  }
}
```

**规则类型说明**：

| type | 用途 | 必需参数 |
|------|------|---------|
| `limit` | 限值校验（≤、≥、= 等） | field_name, limit, operator |
| `tolerance` | 容差校验（期望值偏差） | field_name, expected |
| `calculation` | 公式计算校验 | field_name, formula |
| `compare` | 两字段比较 | field_name, compare_field |

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v2.2 | 2026-07 | 新增「一键识别」全文档 OCR；优化底部控制栏布局（识别当前页移至页码旁）；引擎标签启动即显示；EasyOCR 模型本地化 |
| v2.1 | 2026-07 | 新增 Word/图片格式支持、RapidOCR 引擎、标准引用修正(IEC 62841)、模板按章节重命名 |
| v2.0 | 2026-07 | 多引擎 OCR 级联架构、PDF 类型自动检测、一键全检、本地化部署 |
| v1.0 | 2025 | 初始版本，PaddleOCR 单引擎 |

---

## 作者

设计：王坤  
借助 AI 开发
