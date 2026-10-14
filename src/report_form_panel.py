"""ReportFormPanel — 右侧单页表单式面板

布局：
  顶部：紧凑分类标签栏（温升、EMC 等）
  中部：根据模板动态生成的表单（标签 + 输入框）
  识别后自动将数值填入框内
  底部：计算 + 校验 按钮
"""
from __future__ import annotations

import re
import traceback
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import TEST_CATEGORIES, get_template_display_name


class ReportFormPanel(QWidget):
    """右侧面板 — 单页表单式界面"""

    def __init__(self, checker, theme=None):
        super().__init__()
        self._checker = checker
        self._theme = theme  # Theme 类引用
        self._test_type = ""
        self._ocr_text = ""
        self._extracted: Dict[str, Any] = {}
        self._calculated: Dict[str, Any] = {}
        self._field_edits: Dict[str, QLineEdit] = {}       # field_name -> 输入框
        self._array_edits: Dict[str, List[QLineEdit]] = {} # field_name -> [edit1, edit2, ...]
        self._field_meta: Dict[str, Dict] = {}             # field_name -> 字段元数据
        self._table_meta: List[Dict] = []                  # 表格结构元数据（headers + fields）
        self._verify_result_widgets: List[QWidget] = []
        self._init_ui()

    # ────────────── UI 构建 ──────────────

    def _init_ui(self):
        T = self._theme
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(6, 4, 6, 6)
        self._main_layout.setSpacing(4)

        # ── 顶部标签栏 ──
        self._tab_bar = QWidget()
        self._tab_bar.setFixedHeight(32)
        self._tab_bar.setStyleSheet(f"background: {T.CARD()}; border-radius: 6px;")
        tab_lay = QHBoxLayout(self._tab_bar)
        tab_lay.setContentsMargins(6, 2, 6, 2)
        tab_lay.setSpacing(4)

        self._tab_buttons: Dict[str, QPushButton] = {}
        for cat_name, test_list in TEST_CATEGORIES.items():
            for test_name in test_list:
                display = get_template_display_name(test_name)
                btn = QPushButton(display)
                btn.setCheckable(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setFixedHeight(24)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        font-size: 11px; font-weight: 600;
                        color: {T.TEXT_SEC()}; background: transparent;
                        border: 1px solid transparent; border-radius: 4px;
                        padding: 2px 10px;
                    }}
                    QPushButton:hover {{
                        color: {T.PRIMARY()}; background: {T.HOVER()};
                    }}
                    QPushButton:checked {{
                        color: white; background: {T.PRIMARY()};
                        border-color: {T.PRIMARY()};
                    }}
                """)
                btn.clicked.connect(lambda checked, tn=test_name: self._switch_test_type(tn))
                self._tab_buttons[test_name] = btn
                tab_lay.addWidget(btn)
        tab_lay.addStretch()
        self._main_layout.addWidget(self._tab_bar)

        # ── 中部表单区域 ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {T.BORDER()}; background: {T.CARD()}; border-radius: 6px; }}")

        self._form_container = QWidget()
        self._form_container.setStyleSheet(f"background: {T.CARD()};")
        self._form_layout = QVBoxLayout(self._form_container)
        self._form_layout.setContentsMargins(10, 10, 10, 10)
        self._form_layout.setSpacing(6)

        self._form_title = QLabel("请选择测试项目")
        self._form_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self._form_title.setStyleSheet(f"color: {T.TEXT()}; padding: 2px 0;")
        self._form_layout.addWidget(self._form_title)

        self._fields_layout = QVBoxLayout()
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        self._fields_layout.setSpacing(5)
        self._form_layout.addLayout(self._fields_layout)
        self._form_layout.addStretch()

        self._scroll.setWidget(self._form_container)
        self._main_layout.addWidget(self._scroll, 1)

        # ── 底部按钮栏 ──
        self._action_bar = QWidget()
        self._action_bar.setFixedHeight(44)
        self._action_bar.setStyleSheet(f"background: {T.CARD()}; border-radius: 6px;")
        action_lay = QHBoxLayout(self._action_bar)
        action_lay.setContentsMargins(8, 4, 8, 4)
        action_lay.setSpacing(8)

        self._calc_btn = QPushButton("计算")
        self._calc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._calc_btn.setStyleSheet(T.BTN_PRIMARY())
        self._calc_btn.clicked.connect(self._do_calculate)
        self._calc_btn.setEnabled(False)

        self._verify_btn = QPushButton("校验")
        self._verify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._verify_btn.setStyleSheet(f"""
            QPushButton {{
                background: {T.SUCCESS()}; color: white; border: none;
                border-radius: 4px; padding: 6px 18px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #1E8449; }}
            QPushButton:pressed {{ background: #145A32; }}
            QPushButton:disabled {{ background: {T.BORDER()}; color: {T.TEXT_SEC()}; }}
        """)
        self._verify_btn.clicked.connect(self._do_verify)
        self._verify_btn.setEnabled(False)

        self._status_indicator = QLabel("")
        self._status_indicator.setFixedSize(28, 28)
        self._status_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_indicator.setStyleSheet(
            f"font-size: 16px; border-radius: 14px; background: {T.BORDER()};")

        action_lay.addWidget(self._calc_btn)
        action_lay.addWidget(self._verify_btn)
        action_lay.addWidget(self._status_indicator)
        action_lay.addStretch()
        self._main_layout.addWidget(self._action_bar)

    # ────────────── 切换测试类型 ──────────────

    def _switch_test_type(self, test_type: str):
        if self._test_type == test_type:
            return
        for tn, btn in self._tab_buttons.items():
            btn.setChecked(tn == test_type)
        self._test_type = test_type
        self._build_form_from_template()
        if self._ocr_text:
            self._auto_fill_from_ocr()
        self._reset_status()

    def switch_test_type(self, test_type: str):
        self._switch_test_type(test_type)

    # ────────────── 表单构建 ──────────────

    def _clear_form_fields(self):
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._field_edits.clear()
        self._array_edits.clear()
        self._field_meta.clear()
        self._table_meta.clear()

    def _build_form_from_template(self):
        T = self._theme
        self._clear_form_fields()

        try:
            loaded = self._checker.load_template(self._test_type)
        except Exception:
            loaded = False

        tmpl = self._checker._current_template if loaded else None
        if not tmpl:
            self._form_title.setText("（未找到该测试模板）")
            self._calc_btn.setEnabled(False)
            return

        display = get_template_display_name(self._test_type)
        self._form_title.setText(display)

        fields = tmpl.get('fields', [])
        tables_def = tmpl.get('tables', [])

        if tables_def:
            for tdef in tables_def:
                self._build_table_section(tdef, tmpl)
        elif fields:
            self._build_fields_section(fields)
        else:
            ph = QLabel("（模板无字段定义）")
            ph.setStyleSheet(f"color: {T.TEXT_SEC()}; padding: 10px;")
            self._fields_layout.addWidget(ph)

        self._fields_layout.addStretch()
        self._calc_btn.setEnabled(True)

    def _build_table_section(self, tdef: Dict, tmpl: Dict):
        T = self._theme
        tname = tdef.get('table_name', '')
        desc = tdef.get('description', tname)
        is_data_grid = bool(tdef.get('data_grid'))

        # 保存表格结构元数据，供 OCR 智能填充使用
        headers = [h.get('label', '') for h in tdef.get('headers', [])]
        self._table_meta.append({
            'title': desc,
            'headers': headers,
            'fields': tdef.get('fields', []),
        })

        title = QLabel(desc)
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color: {T.PRIMARY()}; padding: 8px 0 2px 0;"
            f"border-bottom: 1px solid {T.BORDER()};")
        self._fields_layout.addWidget(title)

        fields = tdef.get('fields', [])

        if is_data_grid:
            # 把列头和数据行放在同一个 QGridLayout 中，列宽自动对齐
            self._add_data_grid(headers, fields)
        else:
            for f in fields:
                self._add_field_row(f)

    def _add_data_grid(self, headers: List[str], fields: List[Dict]):
        """把列头和所有数据行放到同一个 QGridLayout 内，列宽自动对齐"""
        T = self._theme
        n_cols = max(len(headers), 1)

        grid_widget = QWidget()
        grid_widget.setStyleSheet(
            f"background: {T.CARD()}; border: 1px solid {T.BORDER()}; border-radius: 4px;")
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, 90)
        # 列头标签
        corner = QLabel("")
        grid.addWidget(corner, 0, 0)
        for col, h in enumerate(headers):
            lbl = QLabel(str(h))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color: {T.PRIMARY()}; font-size: 10px; font-weight: 600;"
                f" background: {T.HOVER()}; padding: 4px 6px; border-radius: 3px;")
            grid.addWidget(lbl, 0, col + 1)

        # 数据行
        for row_idx, f in enumerate(fields, start=1):
            self._add_grid_row(grid, row_idx, f, n_cols)

        # 让所有列（除列头外）等宽拉伸
        for c in range(1, n_cols + 1):
            grid.setColumnStretch(c, 1)

        self._fields_layout.addWidget(grid_widget)

    def _add_grid_row(self, grid: QGridLayout, row_idx: int, f: Dict, n_cols: int):
        T = self._theme
        field_name = f.get('name') or f.get('field_name', '')
        ftype = f.get('type', 'number')
        desc = f.get('description', field_name)
        unit = f.get('unit', '')
        show_label = f.get('show_label', True)
        is_computed = f.get('computed', False)

        self._field_meta[field_name] = f

        # 行标签
        if show_label:
            lbl = QLabel(desc)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(f"color: {T.TEXT()}; font-size: 12px; font-weight: 600;")
            lbl.setToolTip(f"字段: {field_name}")
            grid.addWidget(lbl, row_idx, 0)
        else:
            # 无标签行：放一个空 label 占位
            grid.addWidget(QLabel(""), row_idx, 0)

        edit_style = self._edit_style()
        if is_computed:
            edit_style = self._computed_edit_style()

        if ftype in ('number_array', 'text_array'):
            array_size = f.get('array_size', n_cols)
            edits: List[QLineEdit] = []
            for i in range(array_size):
                edit = QLineEdit()
                edit.setFixedHeight(28)
                edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
                edit.setStyleSheet(edit_style + " font-size: 12px;")
                if is_computed:
                    edit.setReadOnly(True)
                    edit.setPlaceholderText("自动计算")
                else:
                    edit.setPlaceholderText("数值" + (f" ({unit})" if unit else ""))
                grid.addWidget(edit, row_idx, i + 1)
                edits.append(edit)
            self._array_edits[field_name] = edits
        else:
            edit = QLineEdit()
            edit.setFixedHeight(28)
            edit.setStyleSheet(edit_style + " font-size: 12px;")
            if is_computed:
                edit.setReadOnly(True)
                edit.setPlaceholderText("自动计算")
            else:
                edit.setPlaceholderText(f"输入{desc}" + (f" ({unit})" if unit else ""))
            grid.addWidget(edit, row_idx, 1, 1, n_cols)
            self._field_edits[field_name] = edit

    def _grid_max_cols(self, fields: List[Dict], headers: List[str]) -> int:
        """保留旧接口，避免遗漏调用"""
        m = len(headers)
        for f in fields:
            if f.get('type') == 'number_array':
                m = max(m, f.get('array_size', len(headers) if headers else 1))
        return max(m, 1)

    def _build_fields_section(self, fields: List[Dict]):
        T = self._theme
        title = QLabel("检测字段")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color: {T.PRIMARY()}; padding: 6px 0 2px 0;"
            f"border-bottom: 1px solid {T.BORDER()};")
        self._fields_layout.addWidget(title)
        for f in fields:
            if f.get('field_name') or f.get('name'):
                self._add_field_row(f)

    def _add_grid_header(self, headers: List[str], max_cols: int):
        """兼容旧版调用（不再单独使用，列头已合并到 _add_data_grid 中）"""
        return

    def _add_field_row(self, f: Dict, headers: List[str] = None, max_cols: int = None):
        """简单（无表格）单行字段"""
        T = self._theme
        field_name = f.get('name') or f.get('field_name', '')
        ftype = f.get('type', 'number')
        desc = f.get('description', field_name)
        unit = f.get('unit', '')

        self._field_meta[field_name] = f

        if ftype == 'number_array':
            array_size = f.get('array_size', 1)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)

            lbl = QLabel(desc)
            lbl.setFixedWidth(100)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(f"color: {T.TEXT()}; font-size: 12px; font-weight: 600;")
            row.addWidget(lbl)

            edits: List[QLineEdit] = []
            for i in range(array_size):
                edit = QLineEdit()
                edit.setFixedHeight(26)
                edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
                edit.setStyleSheet(self._edit_style())
                edit.setPlaceholderText(f"#{i + 1}" + (f" {unit}" if unit else ""))
                edits.append(edit)
                row.addWidget(edit, 1)
            row.addStretch()

            container = QWidget()
            container.setLayout(row)
            self._fields_layout.addWidget(container)
            self._array_edits[field_name] = edits
        else:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)

            lbl = QLabel(desc)
            lbl.setFixedWidth(100)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(f"color: {T.TEXT()}; font-size: 12px;")
            lbl.setToolTip(f"字段: {field_name}")

            edit = QLineEdit()
            edit.setStyleSheet(self._edit_style())
            edit.setPlaceholderText(f"输入{desc}" + (f" ({unit})" if unit else ""))

            row.addWidget(lbl)
            row.addWidget(edit, 1)
            row.addStretch()

            container = QWidget()
            container.setLayout(row)
            self._fields_layout.addWidget(container)
            self._field_edits[field_name] = edit

    def _add_array_row(self, field_name: str, desc: str, unit: str,
                       f: Dict, headers: List[str] = None, max_cols: int = None):
        """兼容旧接口：重定向到 _add_field_row（data_grid 场景已由 _add_data_grid 处理）"""
        self._add_field_row(f, headers=headers, max_cols=max_cols)

    def _edit_style(self) -> str:
        T = self._theme
        return (f"QLineEdit {{ background: {T.BG()}; color: {T.TEXT()};"
                f" border: 1px solid {T.BORDER()}; border-radius: 4px;"
                f" padding: 4px 8px; font-size: 12px; }}"
                f" QLineEdit:focus {{ border-color: {T.PRIMARY()}; }}")

    def _computed_edit_style(self) -> str:
        T = self._theme
        return (f"QLineEdit {{ background: {T.HOVER()}; color: {T.PRIMARY()};"
                f" border: 1px solid {T.BORDER()}; border-radius: 4px;"
                f" padding: 4px 8px; font-size: 12px; font-weight: 600; }}"
                f" QLineEdit:focus {{ border-color: {T.PRIMARY()}; }}")

    # ────────────── OCR 自动填入 ──────────────

    def set_ocr_text(self, text: str):
        """外部调用：OCR 完成后传入识别文本"""
        self._ocr_text = self._fix_ocr_decimals(text or "")
        self._extracted.clear()
        # 每次重新识别前，清空所有已填入的输入框，避免残留旧数据
        self._clear_all_inputs()
        if self._test_type:
            self._auto_fill_from_ocr()

    @staticmethod
    def _fix_ocr_decimals(text: str) -> str:
        """修复OCR常见的小数点拆分问题

        OCR 经常把 0.94 拆成 0. 94 或 0 . 94，
        本方法把 "数字. 空格 数字" 合并为 "数字.数字"
        """
        if not text:
            return text
        # 修复 "0. 94" -> "0.94"（小数点后跟空格再跟数字）
        text = re.sub(r'(\d+)\.\s+(\d+)', r'\1.\2', text)
        # 修复 "0 .94" -> "0.94"（数字后跟空格再跟小数点）
        text = re.sub(r'(\d+)\s+\.(\d+)', r'\1.\2', text)
        # 修复 "0 . 94" -> "0.94"（三段拆分）
        text = re.sub(r'(\d+)\s+\.\s+(\d+)', r'\1.\2', text)
        return text

    def _clear_all_inputs(self):
        """清空所有表单输入框"""
        for edit in self._field_edits.values():
            edit.setText("")
        for edits in self._array_edits.values():
            for edit in edits:
                edit.setText("")

    def get_fill_rate(self) -> float:
        """计算当前表单填入率（已填字段数 / 总字段数 * 100）"""
        total = 0
        filled = 0
        for edit in self._field_edits.values():
            total += 1
            if edit.text().strip():
                filled += 1
        for edits in self._array_edits.values():
            for edit in edits:
                total += 1
                if edit.text().strip():
                    filled += 1
        return (filled / total * 100) if total > 0 else 0.0

    def check_column_consistency(self) -> bool:
        """检查同列数值是否合理：同一数组的相邻元素差异不应过大

        例如 stator_resistance = [冷态R1, 热态R2_0.94, 热态R2_1, 热态R2_1.06]
        冷态和热态的比值通常在 1.0~2.0 之间，如果差10倍以上说明识别错了。
        """
        for field_name, edits in self._array_edits.items():
            vals = []
            for edit in edits:
                text = edit.text().strip()
                try:
                    vals.append(float(text))
                except (ValueError, AttributeError):
                    vals.append(None)

            # 对电阻类字段：冷态R1 不应该为0，热态R2/R1 比值应该合理
            if 'resistance' in field_name:
                cold = vals[0] if len(vals) > 0 else None
                if cold is not None and cold > 0:
                    for i in range(1, len(vals)):
                        hot = vals[i]
                        if hot is not None:
                            ratio = hot / cold
                            # 电阻比值通常在 0.3~10.0 之间（OCR误差容忍更宽）
                            if ratio < 0.2 or ratio > 20.0:
                                return False

            # 对输入输出参数类字段：第1列是电压，应该在合理范围
            if field_name in ('no_load', 'rated_load_1', 'rated_load_2',
                              'voltage_0_94_1', 'voltage_0_94_2',
                              'voltage_1_06_1', 'voltage_1_06_2'):
                # 第1列是电压，应该在 150~300 范围（放宽容忍度）
                for v in vals[:1]:
                    if v is not None and (v < 150 or v > 300):
                        return False

        return True

    def _auto_fill_from_ocr(self):
        """从 OCR 文本中提取字段值并填入输入框"""
        if not self._ocr_text or not self._test_type:
            return

        tmpl = getattr(self._checker, '_current_template', None)
        if not tmpl:
            return

        self._smart_description_fill()

    def _fill_fields(self, extracted: Dict[str, Any]):
        """将提取的值填入对应输入框"""
        for field_name, value in extracted.items():
            if field_name in self._field_edits:
                edit = self._field_edits[field_name]
                edit.setText(self._format_value(value))
            elif field_name in self._array_edits:
                edits = self._array_edits[field_name]
                if isinstance(value, list):
                    for i, v in enumerate(value):
                        if i < len(edits):
                            edits[i].setText(self._format_value(v))
                else:
                    edits[0].setText(self._format_value(value))

    def _format_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            if value == int(value):
                return str(int(value))
            return f"{value:.2f}"
        return str(value)

    # ────────────── 页眉页脚过滤 ──────────────

    # 常见页眉/页脚关键词（整行匹配时跳过）
    _HEADER_FOOTER_KEYWORDS = [
        '检测报告', '检验报告', '测试报告', '试验报告',
        '第', '页', 'page', '共', 'of',
        '报告编号', '报告日期', '样品编号', '委托单位',
        '检验结论', '批准', '审核', '编制', '检验员',
        '实验室', '检测中心', '质量监督',
    ]

    # 带单位的标题行特征（含这些模式且数字少的行是表头而非数据）
    _UNIT_PATTERNS = re.compile(
        r'\(V\)|\(Hz\)|\(A\)|\(W\)|\(Ω\)|\(K\)|\(℃\)|'
        r'r/min|N·m|cosφ|η\(|功率因素|效率|'
        r'冷态R|热态R|电压U|频率f|电流I|输入功率|输出功率|转速n|转矩T',
        re.IGNORECASE
    )

    # 常见页眉/页脚正则模式
    _HEADER_FOOTER_PATTERNS = [
        re.compile(r'^第\s*\d+\s*页.*共\s*\d+\s*页', re.IGNORECASE),
        re.compile(r'^page\s+\d+', re.IGNORECASE),
        re.compile(r'^\d+\s*/\s*\d+$'),  # 1/5
        re.compile(r'^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?$'),  # 日期
        re.compile(r'^报告编号[:：].*', re.IGNORECASE),
        re.compile(r'^样品编号[:：].*', re.IGNORECASE),
        re.compile(r'^报告日期[:：].*$', re.IGNORECASE),
        re.compile(r'^[A-Z]{2,}[-_]?\d{3,}'),  # 编号 like EMC-2024-001
    ]

    def _filter_header_footer(self, text: str) -> str:
        """过滤页眉页脚干扰行，保留正文数据行"""
        if not text:
            return text
        lines = text.split('\n')
        if len(lines) <= 2:
            return text

        filtered = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                filtered.append(line)  # 保留空行（维持行结构）
                continue

            # 跳过匹配正则模式的行
            skip = False
            for pat in self._HEADER_FOOTER_PATTERNS:
                if pat.match(stripped):
                    skip = True
                    break
            if skip:
                continue

            # 跳过纯数字行（页码）
            if re.fullmatch(r'\d+', stripped):
                continue

            # 跳过非常短的行（<4字符且不含数字，可能是页眉残留）
            if len(stripped) < 4 and not re.search(r'\d', stripped):
                continue

            # 首尾各2行如果只包含关键词（非数据行），也跳过
            is_edge = (i < 2 or i >= len(lines) - 2)
            if is_edge:
                # 首尾行如果不含数字或只含少量数字，可能是页眉页脚
                nums_in_line = len(re.findall(r'\d', stripped))
                if nums_in_line <= 1 and any(kw in stripped for kw in self._HEADER_FOOTER_KEYWORDS):
                    continue

            filtered.append(line)

        return '\n'.join(filtered)

    # ────────────── 表格结构解析 ──────────────

    def _parse_table_rows(self, text: str) -> Dict[str, List[List[float]]]:
        """把 OCR 平铺文本解析成 行标签 -> [候选数值列表...] 的映射

        策略：
          1. 按行分割
          2. 用多空格(2+)分割每行为 [标签部分] 和 [数据部分]
          3. 仅从数据部分提取数值，避免标签内数字干扰
          4. 同一标签可能对应多行（如表头行+数据行），全部保留
          5. 返回 {label_key: [[num1, num2, ...], [num1, ...], ...]}
        """
        result: Dict[str, List[List[float]]] = {}
        if not text:
            return result

        lines = text.split('\n')
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 跳过带单位的标题行（如表头：电压U(V)  频率f(Hz)...）
            # 特征：含单位模式且数字个数少于4（数据行通常有更多数字）
            if self._UNIT_PATTERNS.search(stripped):
                nums_in_line = len(re.findall(r'[-+]?\d+(?:\.\d+)?', stripped))
                if nums_in_line < 4:
                    continue  # 标题行，跳过

            # 用 2+ 个空格/制表符分割
            parts = re.split(r' {2,}|\t+', stripped, maxsplit=1)

            label = ''
            data_part = stripped

            if len(parts) == 2:
                # 正常情况：标签 + 数据，用多空格分隔
                label = parts[0].strip()
                data_part = parts[1].strip()
            else:
                # 无法分割：整行可能纯数据或纯标签
                # 尝试提取行首文字标签
                m = re.match(r'^([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9（）()\[\]【】·.+\-]*?)\s', stripped)
                if m:
                    label = m.group(1).strip()
                    data_part = stripped[m.end():].strip()
                else:
                    # 纯数据行（无标签）
                    label = ''
                    data_part = stripped

            # 从数据部分提取数值
            nums = []
            for m in re.finditer(r'[-+]?\d+(?:\.\d+)?', data_part):
                try:
                    nums.append(float(m.group()))
                except ValueError:
                    continue

            if not nums:
                continue  # 无数值的行跳过

            # 清理标签
            label = re.sub(r'[（(）)\[\]【】{}]', '', label)
            label = re.sub(r'[，,;；:：、\s]+$', '', label)
            label = label.strip()

            if label:
                # 用标签的主关键词作为索引键（保留足够长度区分带序号的行）
                key = label if len(label) <= 20 else label[:20]
                if key not in result:
                    result[key] = []
                result[key].append(nums)

                # 也存储更短的子串作为别名
                for length in (2, 3, 4):
                    if len(label) > length:
                        short_key = label[:length]
                        if short_key not in result:
                            result[short_key] = []
                        result[short_key].append(nums)
            else:
                # 无标签的纯数据行，用特殊键存储
                # 这样 _match_table_field 可以通过上下文匹配
                key = '__no_label__'
                if key not in result:
                    result[key] = []
                result[key].append(nums)

        return result

    def _match_table_field(self, table_rows: Dict[str, List[List[float]]],
                           description: str, expected_count: int) -> List[float]:
        """在解析出的表格行中，按字段描述匹配最佳行

        Args:
            table_rows: _parse_table_rows 的返回值 {label: [candidates]}
            description: 字段描述（如 "空载"、"定子"）
            expected_count: 期望的数值个数

        Returns:
            匹配到的数值列表，未匹配返回空列表
        """
        if not description or not table_rows:
            return []

        keywords = self._description_keywords(description)
        best_nums = []
        best_score = 0

        for keyword in keywords:
            for row_key, candidates in table_rows.items():
                if row_key == '__no_label__':
                    continue  # 无标签行不参与关键字匹配
                if not (keyword in row_key or row_key in keyword):
                    continue
                # 对每个候选行评分，选最佳
                for nums in candidates:
                    score = len(nums)
                    if len(nums) == expected_count:
                        score += 100  # 完美匹配：数值个数正好
                    elif len(nums) >= expected_count:
                        score += 50  # 数量够多，取前N个
                    # 关键词匹配精度
                    if keyword == row_key:
                        score += 30
                    # 数据行偏好：纯数字行（标签后全是数字）得分更高
                    if len(nums) == expected_count:
                        score += 20  # 额外奖励精确匹配
                    if score > best_score:
                        best_score = score
                        best_nums = nums

        if not best_nums:
            return []

        if len(best_nums) >= expected_count:
            return best_nums[:expected_count]
        return best_nums

    # ────────────── 智能填充（改造版）──────────────

    def _smart_description_fill(self):
        """智能填充：分段识别 + 表格结构感知

        对温升测试模板，按表格标题分段提取：
          1. 输入输出参数表（空载/额定负载/0.94倍/1.06倍）
          2. 电阻法测量结果（室温 + 电阻数值 + 温升数值）
          3. 热电偶法测量结果
        每段独立解析，避免跨段干扰。
        """
        # Step 1: 过滤页眉页脚
        clean_text = self._filter_header_footer(self._ocr_text)

        # Step 2: 规范化文本
        normalized = self._normalize_ocr_text(clean_text)

        # Step 3: 分段：按表格标题切分文本
        sections = self._split_sections(clean_text)

        # Step 4: 逐段提取
        # 4a) 输入输出参数表
        io_section = sections.get('输入输出参数', '')
        if io_section:
            self._fill_io_table(io_section)

        # 4b) 电阻法测量结果（室温 + 电阻数值 + 温升数值）
        resistance_section = sections.get('电阻法测量结果', '')
        if resistance_section:
            self._fill_resistance_section(resistance_section)

        # 4c) 热电偶法测量结果
        thermo_section = sections.get('热电偶法测量结果', '')
        if thermo_section:
            self._fill_thermocouple_section(thermo_section)

        # 4d) 级联空值校验
        self._validate_cascade_empty()

        # 5) 兜底：对仍未填入的字段，用旧版全文匹配
        self._fallback_fill(normalized, clean_text)

    # ────────────── 分段提取 ──────────────

    _SECTION_TITLES = [
        '输入输出参数',
        '电阻法测量结果',
        '温升数值',
        '热电偶法测量结果',
    ]

    def _split_sections(self, text: str) -> Dict[str, str]:
        """按表格标题将 OCR 文本切分为多个段落"""
        sections: Dict[str, str] = {}
        lines = text.split('\n')

        current_section = None
        current_lines = []

        for line in lines:
            stripped = line.strip()
            # 检测是否命中表格标题
            matched_title = None
            for title in self._SECTION_TITLES:
                if title in stripped:
                    matched_title = title
                    break

            if matched_title:
                # 保存上一段
                if current_section:
                    sections[current_section] = '\n'.join(current_lines)
                current_section = matched_title
                current_lines = [line]
            elif current_section:
                current_lines.append(line)

        # 保存最后一段
        if current_section:
            sections[current_section] = '\n'.join(current_lines)

        return sections

    # 输入输出参数表每列的值域范围（用于逐格校验）
    # 列顺序：电压U(V), 频率f(Hz), 电流I(A), 输入功率P1(W), 输出功率P2(W),
    #         转速n(r/min), 转矩T(N·m), 效率η(%), 功率因数cosφ
    _IO_COLUMN_RANGES = [
        (150, 300),    # 0: 电压 ~220V
        (40, 65),      # 1: 频率 ~50Hz
        (0.1, 50),     # 2: 电流
        (100, 2000),   # 3: 输入功率
        (50, 1500),    # 4: 输出功率
        (1000, 15000), # 5: 转速
        (0.1, 100),    # 6: 转矩
        (10, 100),     # 7: 效率%
        (0.1, 1.0),    # 8: 功率因数
    ]

    def _validate_io_cell(self, col_idx: int, value: float) -> bool:
        """校验输入输出参数表某列的值是否在合理范围内"""
        if col_idx < 0 or col_idx >= len(self._IO_COLUMN_RANGES):
            return True
        lo, hi = self._IO_COLUMN_RANGES[col_idx]
        return lo <= value <= hi

    def _fill_io_table(self, section_text: str):
        """提取输入输出参数表：7行 × 9列

        行标签：空载、额定负载(×2)、0.94倍(×2)、1.06倍(×2)
        列：电压U、频率f、电流I、输入功率P1、输出功率P2、转速n、转矩T、效率η、功率因数cosφ
        每格填入前校验值域，超出范围则跳过。
        """
        table_rows = self._parse_table_rows(section_text)
        io_fields = [
            ('no_load', '空载', 9),
            ('rated_load_1', '额定负载1', 9),
            ('rated_load_2', '额定负载2', 9),
            ('voltage_0_94_1', '0.94倍额定电压1', 9),
            ('voltage_0_94_2', '0.94倍额定电压2', 9),
            ('voltage_1_06_1', '1.06倍额定电压1', 9),
            ('voltage_1_06_2', '1.06倍额定电压2', 9),
        ]
        for field_name, desc, expected in io_fields:
            edits = self._array_edits.get(field_name)
            if not edits:
                continue
            nums = self._match_table_field(table_rows, desc, expected)
            if not nums:
                nums = self._extract_row_numbers_by_description(
                    self._normalize_ocr_text(section_text), desc, expected)
            for idx, num in enumerate(nums):
                if idx < len(edits):
                    # 逐格校验：检查值是否在对应列的合理范围内
                    if idx < len(self._IO_COLUMN_RANGES):
                        if not self._validate_io_cell(idx, num):
                            print(f"[VALIDATE] 跳过 {field_name}[{idx}]={num}，超出范围{self._IO_COLUMN_RANGES[idx]}")
                            continue
                    edits[idx].setText(self._format_value(num))

    def _fill_resistance_section(self, section_text: str):
        """提取电阻法测量结果：室温 + 电阻数值 + 温升数值"""
        # 1) 室温（单值字段）
        normalized = self._normalize_ocr_text(section_text)
        for field_name, edit in self._field_edits.items():
            meta = self._field_meta.get(field_name)
            if not meta or meta.get('computed', False):
                continue
            desc = meta.get('description', '')
            if not desc:
                continue
            val = self._find_value_by_description(normalized, desc)
            if val is not None:
                edit.setText(self._format_value(val))

        # 2) 电阻数值表（定子/转子 × 4列）
        table_rows = self._parse_table_rows(section_text)
        resistance_fields = [
            ('stator_resistance', '定子', 4),
            ('rotor_resistance', '转子', 4),
        ]
        for field_name, desc, expected in resistance_fields:
            edits = self._array_edits.get(field_name)
            if not edits:
                continue
            nums = self._match_table_field(table_rows, desc, expected)
            if not nums:
                nums = self._extract_row_numbers_by_description(
                    normalized, desc, expected)
            for idx, num in enumerate(nums):
                if idx < len(edits):
                    edits[idx].setText(self._format_value(num))

        # 3) 温升数值表（6列）
        temp_fields = [
            ('temperature_rise', '温升', 6),
        ]
        for field_name, desc, expected in temp_fields:
            edits = self._array_edits.get(field_name)
            if not edits:
                continue
            nums = self._match_table_field(table_rows, desc, expected)
            if not nums:
                nums = self._extract_row_numbers_by_description(
                    normalized, desc, expected)
            for idx, num in enumerate(nums):
                if idx < len(edits):
                    edits[idx].setText(self._format_value(num))

    def _fill_thermocouple_section(self, section_text: str):
        """提取热电偶法测量结果"""
        table_rows = self._parse_table_rows(section_text)
        normalized = self._normalize_ocr_text(section_text)

        thermo_fields = [
            ('thermocouple_temperature', '热态温度', 9),
        ]
        for field_name, desc, expected in thermo_fields:
            edits = self._array_edits.get(field_name)
            if not edits:
                continue
            nums = self._match_table_field(table_rows, desc, expected)
            if not nums:
                nums = self._extract_row_numbers_by_description(
                    normalized, desc, expected)
            for idx, num in enumerate(nums):
                if idx < len(edits):
                    edits[idx].setText(self._format_value(num))

    def _fallback_fill(self, normalized: str, clean_text: str):
        """兜底：对仍未填入的字段，用旧版全文匹配"""
        table_rows = self._parse_table_rows(clean_text)

        # 数组字段兜底
        for field_name, edits in self._array_edits.items():
            # 跳过已填入的
            if any(e.text().strip() for e in edits):
                continue
            meta = self._field_meta.get(field_name)
            if not meta or meta.get('computed', False):
                continue
            desc = meta.get('description', '')
            if not desc:
                continue
            expected = len(edits)
            nums = self._match_table_field(table_rows, desc, expected)
            if not nums:
                nums = self._extract_row_numbers_by_description(
                    normalized, desc, expected)
            for idx, num in enumerate(nums):
                if idx < len(edits):
                    edits[idx].setText(self._format_value(num))

        # 普通字段兜底
        for field_name, edit in self._field_edits.items():
            if edit.text().strip():
                continue
            meta = self._field_meta.get(field_name)
            if not meta or meta.get('computed', False):
                continue
            desc = meta.get('description', '')
            if not desc:
                continue
            val = self._find_value_by_description(normalized, desc)
            if val is not None:
                edit.setText(self._format_value(val))

    def _validate_cascade_empty(self):
        """级联空值校验：如果0.94/1.06倍电压数据为空，对应电阻值也清空

        电阻数值表的列结构：[冷态R1, 热态R2_0.94倍, 热态R2_1倍, 热态R2_1.06倍]
        - 列0（冷态R1）：始终保留
        - 列1（0.94倍）：仅当0.94倍额定电压有数据时保留
        - 列2（1倍）：仅当额定负载有数据时保留
        - 列3（1.06倍）：仅当1.06倍额定电压有数据时保留

        温升数值表同理：列对应 [转子0.94, 转子1, 转子1.06, 定子0.94, 定子1, 定子1.06]
        """
        # 检查 0.94倍额定电压 是否有数据
        v_094_has_data = self._field_has_data('voltage_0_94_1') or \
                         self._field_has_data('voltage_0_94_2')
        # 检查 1.06倍额定电压 是否有数据
        v_106_has_data = self._field_has_data('voltage_1_06_1') or \
                         self._field_has_data('voltage_1_06_2')
        # 检查 额定负载 是否有数据
        rated_has_data = self._field_has_data('rated_load_1') or \
                        self._field_has_data('rated_load_2')

        # 如果0.94倍电压没数据，清空电阻表和温升表的0.94倍列
        if not v_094_has_data:
            self._clear_array_column('stator_resistance', 1)
            self._clear_array_column('rotor_resistance', 1)
            # 温升表：列0,3是0.94倍
            self._clear_array_columns('temperature_rise', [0, 3])
            self._clear_array_columns('temperature_rise_calc', [0, 3])

        # 如果1.06倍电压没数据，清空1.06倍列
        if not v_106_has_data:
            self._clear_array_column('stator_resistance', 3)
            self._clear_array_column('rotor_resistance', 3)
            # 温升表：列2,5是1.06倍
            self._clear_array_columns('temperature_rise', [2, 5])
            self._clear_array_columns('temperature_rise_calc', [2, 5])

        # 如果额定负载没数据，清空1倍列
        if not rated_has_data:
            self._clear_array_column('stator_resistance', 2)
            self._clear_array_column('rotor_resistance', 2)
            self._clear_array_columns('temperature_rise', [1, 4])
            self._clear_array_columns('temperature_rise_calc', [1, 4])

    def _field_has_data(self, field_name: str) -> bool:
        """检查某个数组字段是否有有效数据（非空、非全零）"""
        edits = self._array_edits.get(field_name)
        if not edits:
            return False
        for edit in edits:
            text = edit.text().strip()
            if text and text != '0' and text != '0.0' and text != '0.00':
                return True
        return False

    def _clear_array_column(self, field_name: str, col_idx: int):
        """清空某个数组字段的指定列"""
        edits = self._array_edits.get(field_name)
        if edits and col_idx < len(edits):
            edits[col_idx].setText("")

    def _clear_array_columns(self, field_name: str, col_indices: list):
        """清空某个数组字段的多个列"""
        edits = self._array_edits.get(field_name)
        if not edits:
            return
        for idx in col_indices:
            if idx < len(edits):
                edits[idx].setText("")

    def _normalize_ocr_text(self, text: str) -> str:
        """规范化 OCR 文本：统一空白、替换全角标点"""
        text = text.replace('（', '(').replace('）', ')')
        text = re.sub(r'[，,;；\t]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _find_value_by_description(self, text: str, description: str) -> Optional[float]:
        """根据字段中文描述在 OCR 文本中匹配最近的数值"""
        if not description or not text:
            return None
        candidates = self._description_keywords(description)
        for key in candidates:
            val = self._extract_number_after(text, key)
            if val is not None:
                return val
        return None

    @staticmethod
    def _description_keywords(description: str) -> List[str]:
        """生成描述的多级关键词列表，提升 OCR 匹配成功率

        逐级缩短关键词长度，应对 OCR 字符错认/丢失。
        例如 "开始室温t1" 在 OCR 中可能变成 "开始室溪t"，
        用前缀 "开始室" 就能匹配上。
        """
        desc = description.strip()
        candidates = [desc]
        # 常见别名映射
        aliases = {
            '开始室温': ['开始室温', '开始室温t1', 't1', '开始室', '室温'],
            '结束室温': ['结束室温', '结束时室温', '结束时室温t2', 't2', '结束室', '结束'],
            '空载': ['空载'],
            '额定负载1': ['额定负载1', '额定负载'],
            '额定负载2': ['额定负载2', '额定负载'],
            '0.94倍额定电压1': ['0.94倍额定电压1', '0.94倍额定电压', '0.94倍', '0.94'],
            '0.94倍额定电压2': ['0.94倍额定电压2', '0.94倍额定电压', '0.94倍', '0.94'],
            '1.06倍额定电压1': ['1.06倍额定电压1', '1.06倍额定电压', '1.06倍', '1.06'],
            '1.06倍额定电压2': ['1.06倍额定电压2', '1.06倍额定电压', '1.06倍', '1.06'],
            '定子': ['定子'],
            '转子': ['转子'],
            '温升Δt（K）': ['温升', '温升Δt'],
            '热态温度(℃)': ['热态温度'],
        }
        for k, vlist in aliases.items():
            if k in desc:
                for v in vlist:
                    if v not in candidates:
                        candidates.append(v)
        # 逐级缩短前缀兜底（应对 OCR 字符错认）
        for n in [len(desc), len(desc) - 1, len(desc) - 2, 4, 3, 2]:
            if n >= 2 and n < len(desc):
                prefix = desc[:n]
                if prefix not in candidates:
                    candidates.append(prefix)
        return candidates

    def _extract_number_after(self, text: str, keyword: str) -> Optional[float]:
        """找到 keyword 后出现的第一个有效数值

        跳过标签中的数字（如 t1 中的 1），优先返回带小数点或2位以上的数值。
        """
        if not keyword:
            return None
        # 先定位关键词位置
        idx = text.find(keyword)
        if idx < 0:
            return None
        # 取关键词后面的文本（到行尾或最多200字符）
        rest = text[idx + len(keyword):]
        end = rest.find('\n')
        if end >= 0:
            rest = rest[:end]
        # 提取所有数值
        all_nums = re.findall(r'[-+]?\d+(?:\.\d+)?', rest)
        if not all_nums:
            return None
        # 过滤掉标签中的纯单位数（如 t1 的 1、t2 的 2）
        # 优先返回带小数点的数值或2位以上整数
        for n in all_nums:
            val = float(n)
            if '.' in n or abs(val) >= 10:
                return val
        # 如果没有大数，返回第一个非单位数字
        for n in all_nums:
            val = float(n)
            # 跳过 0 和 1（可能是 t1/t2 的标签数字）
            if val > 2:
                return val
        # 兜底返回第一个
        try:
            return float(all_nums[0])
        except ValueError:
            return None

    def _extract_row_numbers_by_description(self, text: str, description: str, count: int) -> List[float]:
        """根据行标签（description）提取该行/段落后面的 count 个数值"""
        if not description or not text or count <= 0:
            return []

        keywords = self._description_keywords(description)
        for keyword in keywords:
            idx = text.find(keyword)
            if idx < 0:
                continue
            # 优先取行首开始，避免行标签自身数字干扰
            start = text.rfind('\n', 0, idx) + 1
            snippet = text[start: start + 500]
            label_end = snippet.find(keyword) + len(keyword)
            after_label = snippet[label_end:]

            nums = []
            for m in re.finditer(r'[-+]?\d+(?:\.\d+)?', after_label):
                try:
                    nums.append(float(m.group()))
                except ValueError:
                    continue

            if len(nums) >= count:
                return nums[:count]
            if nums:
                return nums
        return []

    # ────────────── 计算 ──────────────

    def _do_calculate(self):
        """根据模板中的公式规则计算温升值，填入计算值输入框

        公式: Δt = (R2 - R1) / R1 * (234.5 + t1) - (t2 - t1)
        其中 R1=冷态电阻, R2=热态电阻, t1=开始室温, t2=结束室温
        """
        T = self._theme
        if not self._test_type:
            return

        tmpl = getattr(self._checker, '_current_template', None)
        if not tmpl:
            return

        # 先收集输入框中的值（确保 _extracted 是最新的）
        self._collect_input_values()

        rules = tmpl.get('rules', [])
        calculated = {}

        error_msgs = []
        for rule in rules:
            if rule.get('type') != 'formula_verify':
                continue
            formula = rule.get('formula', '')
            # output_field: 兼容 field_name / output_field / result_field
            output_field = rule.get('field_name') or rule.get('output_field') or rule.get('result_field', '')
            desc = rule.get('description', rule.get('message', output_field))

            # 从公式中自动提取变量名
            inputs = rule.get('inputs', [])
            if not inputs:
                inputs = self._extract_formula_vars(formula)

            try:
                vals = [self._get_input_value(k) for k in inputs]
                # 检查是否有变量缺失
                missing = [k for k, v in zip(inputs, vals) if v is None]
                if missing:
                    error_msgs.append(f"{desc}: 缺少输入值 {missing}")
                    continue
                result = self._eval_formula(formula, inputs, vals)
                if result is not None:
                    calculated[output_field] = result
                    # 填入对应输入框
                    self._set_output_field_value(output_field, result)
                else:
                    error_msgs.append(f"{desc}: 计算结果为空")
            except Exception as e:
                error_msgs.append(f"{desc}: {e}")

        self._calculated = calculated
        self._verify_btn.setEnabled(True)
        self._status_indicator.setText("...")
        self._status_indicator.setStyleSheet(
            f"font-size: 12px; border-radius: 14px; background: {T.HOVER()}; color: {T.TEXT_SEC()};")

        # 如果有错误，弹出提示
        if error_msgs:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "计算错误", "\n".join(error_msgs))

    def _set_output_field_value(self, output_field: str, result):
        """将计算结果填入对应输入框，支持 temperature_rise_0 -> temperature_rise[0]"""
        # 1) 直接匹配字段名
        if output_field in self._field_edits:
            self._field_edits[output_field].setText(self._format_value(result))
            return
        if output_field in self._array_edits:
            edits = self._array_edits[output_field]
            if isinstance(result, list):
                for i, v in enumerate(result):
                    if i < len(edits):
                        edits[i].setText(self._format_value(v))
            else:
                edits[0].setText(self._format_value(result))
            return

        # 2) 带下标匹配：temperature_rise_0 -> temperature_rise[0]
        match = re.match(r'^(.+?)_(\d+)$', output_field)
        if match:
            base_name = match.group(1)
            idx = int(match.group(2))
            if base_name in self._array_edits:
                edits = self._array_edits[base_name]
                if idx < len(edits):
                    edits[idx].setText(self._format_value(result))

    @staticmethod
    def _extract_formula_vars(formula: str) -> List[str]:
        """从公式字符串中提取变量名（排除数字和Python关键字）"""
        import keyword
        tokens = re.findall(r'[a-zA-Z_]\w*', formula)
        exclude = set(keyword.kwlist) | {'abs', 'min', 'max', 'round', 'int', 'float', 'len', 'True', 'False', 'None'}
        return [t for t in tokens if t not in exclude]

    def _collect_input_values(self):
        """从输入框收集当前值到 _extracted"""
        for field_name, edit in self._field_edits.items():
            text = edit.text().strip()
            if text:
                try:
                    self._extracted[field_name] = float(text)
                except ValueError:
                    self._extracted[field_name] = text
        for field_name, edits in self._array_edits.items():
            vals = []
            for edit in edits:
                text = edit.text().strip()
                try:
                    vals.append(float(text) if text else None)
                except ValueError:
                    vals.append(text if text else None)
            self._extracted[field_name] = vals
            # 同时创建带下标的独立键，方便公式引用特定列
            for i, v in enumerate(vals):
                if v is not None:
                    self._extracted[f"{field_name}_{i}"] = v

    def _get_input_value(self, key: str) -> Any:
        return self._extracted.get(key)

    def _get_report_value(self, report_field: str) -> Any:
        """从 _extracted 中取报告值，支持带下标如 temperature_rise_report_0 -> 数组元素"""
        # 1) 直接匹配
        val = self._extracted.get(report_field)
        if val is not None:
            return val
        # 2) 带下标拆分：base_name_idx -> 从 base_name 数组取第 idx 个
        match = re.match(r'^(.+?)_(\d+)$', report_field)
        if match:
            base_name = match.group(1)
            idx = int(match.group(2))
            arr = self._extracted.get(base_name)
            if isinstance(arr, list) and idx < len(arr):
                return arr[idx]
        return None

    def _eval_formula(self, formula: str, inputs: List[str], vals: List) -> Any:
        """安全计算公式"""
        # 数组模式：如果 vals 中有 list，逐元素计算
        has_list = any(isinstance(v, list) for v in vals)
        if has_list:
            max_len = max((len(v) for v in vals if isinstance(v, list)), default=0)
            results = []
            for i in range(max_len):
                elem_vals = []
                for v in vals:
                    if isinstance(v, list):
                        elem_vals.append(v[i] if i < len(v) else 0)
                    elif v is not None:
                        elem_vals.append(v)
                    else:
                        elem_vals.append(0)
                r = self._eval_single(formula, inputs, elem_vals)
                if r is not None:
                    results.append(r)
            return results if results else None
        else:
            return self._eval_single(formula, inputs, vals)

    def _eval_single(self, formula: str, inputs: List[str], vals: List) -> Optional[float]:
        """计算单个公式"""
        try:
            namespace = {}
            for name, val in zip(inputs, vals):
                if val is None:
                    return None
                namespace[name] = float(val)
            # 安全的 eval：只允许数学运算
            result = eval(formula, {"__builtins__": {}}, namespace)
            return float(result)
        except Exception:
            return None

    # ────────────── 校验 ──────────────

    def _do_verify(self):
        """校验：将计算值与识别的报告值比对，一致=通过，不一致=不通过"""
        T = self._theme
        tmpl = getattr(self._checker, '_current_template', None)
        if not tmpl:
            return

        # 先收集输入值，再计算
        self._collect_input_values()
        self._do_calculate()

        rules = tmpl.get('rules', [])
        results = []
        all_pass = True

        for rule in rules:
            rtype = rule.get('type', '')
            if rtype == 'formula_verify':
                desc = rule.get('description', rule.get('message', ''))
                output_field = rule.get('field_name') or rule.get('output_field') or rule.get('result_field', '')
                report_source = rule.get('report_field', output_field)
                tolerance_pct = rule.get('tolerance_pct', 5.0)
                tolerance_abs = rule.get('tolerance', None)
                calc_val = self._calculated.get(output_field)
                report_val = self._get_report_value(report_source)

                # 任何一个为空 → 不通过
                if calc_val is None and report_val is None:
                    results.append({
                        'field': desc,
                        'calc': '—',
                        'report': '—',
                        'pass': False
                    })
                    all_pass = False
                elif calc_val is None:
                    results.append({
                        'field': desc,
                        'calc': '—（计算失败）',
                        'report': self._format_value(report_val),
                        'pass': False
                    })
                    all_pass = False
                elif report_val is None:
                    results.append({
                        'field': desc,
                        'calc': self._format_value(calc_val),
                        'report': '—（未识别）',
                        'pass': False
                    })
                    all_pass = False
                else:
                    try:
                        if isinstance(calc_val, list) and isinstance(report_val, list):
                            for i, (cv, rv) in enumerate(zip(calc_val, report_val)):
                                if cv is not None and rv is not None:
                                    ok, diff = self._compare_values(float(cv), float(rv), tolerance_pct, tolerance_abs)
                                    results.append({
                                        'field': f"{desc}[{i}]",
                                        'calc': self._format_value(cv),
                                        'report': self._format_value(rv),
                                        'pass': ok
                                    })
                                    if not ok:
                                        all_pass = False
                        else:
                            ok, diff = self._compare_values(float(calc_val), float(report_val), tolerance_pct, tolerance_abs)
                            results.append({
                                'field': desc,
                                'calc': self._format_value(calc_val),
                                'report': self._format_value(report_val),
                                'pass': ok
                            })
                            if not ok:
                                all_pass = False
                    except (TypeError, ValueError):
                        results.append({
                            'field': desc,
                            'calc': str(calc_val),
                            'report': str(report_val),
                            'pass': False
                        })
                        all_pass = False

            elif rtype == 'limit':
                field = rule.get('field', rule.get('field_name', ''))
                limit_val = rule.get('value', rule.get('limit', 0))
                operator = rule.get('operator', '<=')
                desc = rule.get('description', rule.get('message', field))
                # 先从计算结果中取，再从输入值中取
                val = self._calculated.get(field)
                if val is None:
                    val = self._extracted.get(field)
                if val is not None:
                    if isinstance(val, list):
                        for i, v in enumerate(val):
                            if v is not None:
                                ok = self._check_limit(float(v), limit_val, operator)
                                results.append({
                                    'field': f"{desc}[{i}]",
                                    'calc': self._format_value(v),
                                    'report': f"{operator} {limit_val}",
                                    'pass': ok
                                })
                                if not ok:
                                    all_pass = False
                    else:
                        try:
                            ok = self._check_limit(float(val), limit_val, operator)
                            results.append({
                                'field': desc,
                                'calc': self._format_value(val),
                                'report': f"{operator} {limit_val}",
                                'pass': ok
                            })
                            if not ok:
                                all_pass = False
                        except (TypeError, ValueError):
                            pass

            elif rtype == 'tolerance':
                field_a = rule.get('field_a', '')
                field_b = rule.get('field_b', '')
                tolerance = rule.get('tolerance', 0.5)
                desc = rule.get('description', f"{field_a} vs {field_b}")
                va = self._extracted.get(field_a)
                vb = self._extracted.get(field_b)
                if va is not None and vb is not None:
                    if isinstance(va, list) and isinstance(vb, list):
                        for i, (a, b) in enumerate(zip(va, vb)):
                            if a is not None and b is not None:
                                diff = abs(float(a) - float(b))
                                ok = diff <= tolerance
                                results.append({
                                    'field': f"{desc}[{i}]",
                                    'calc': self._format_value(a),
                                    'report': self._format_value(b),
                                    'pass': ok
                                })
                                if not ok:
                                    all_pass = False

        # 显示校验结果
        self._show_verify_results(results, all_pass)

    @staticmethod
    def _compare_values(calc: float, report: float, tolerance_pct: float, tolerance_abs: float = None) -> tuple:
        """比较计算值和报告值，返回 (pass, diff)"""
        diff = abs(calc - report)
        if tolerance_abs is not None:
            return diff <= tolerance_abs, diff
        if report != 0:
            pct = diff / abs(report) * 100
            return pct <= tolerance_pct, diff
        return diff <= 0.01, diff

    def _check_limit(self, val: float, limit: float, op: str) -> bool:
        ops = {
            '<=': val <= limit,
            '<': val < limit,
            '>=': val >= limit,
            '>': val > limit,
            '==': abs(val - limit) < 0.01,
        }
        return ops.get(op, False)

    def _show_verify_results(self, results: List[Dict], all_pass: bool):
        T = self._theme
        if all_pass:
            self._status_indicator.setText("✓")
            self._status_indicator.setStyleSheet(
                f"font-size: 16px; border-radius: 14px; background: {T.SUCCESS()}; color: white;")
        else:
            self._status_indicator.setText("✗")
            self._status_indicator.setStyleSheet(
                f"font-size: 16px; border-radius: 14px; background: {T.DANGER()}; color: white;")

        # 在表单底部显示详细结果
        self._clear_verify_results()
        if not results:
            return

        T = self._theme
        title = QLabel("校验结果")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color: {T.PRIMARY()}; padding: 6px 0 2px 0;"
            f"border-bottom: 1px solid {T.BORDER()};")
        self._fields_layout.addWidget(title)

        for r in results:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)

            field_lbl = QLabel(r.get('field', ''))
            field_lbl.setFixedWidth(120)
            field_lbl.setStyleSheet(f"color: {T.TEXT()}; font-size: 11px;")

            calc_lbl = QLabel(f"计算: {r.get('calc', '')}")
            calc_lbl.setStyleSheet(f"color: {T.TEXT_SEC()}; font-size: 11px;")

            report_lbl = QLabel(f"报告: {r.get('report', '')}")
            report_lbl.setStyleSheet(f"color: {T.TEXT_SEC()}; font-size: 11px;")

            pass_val = r.get('pass')
            if pass_val is True:
                pass_str = "✓"
                pass_color = T.SUCCESS()
            elif pass_val is False:
                pass_str = "✗"
                pass_color = T.DANGER()
            else:
                pass_str = "—"
                pass_color = T.TEXT_SEC()
            pass_lbl = QLabel(pass_str)
            pass_lbl.setFixedWidth(20)
            pass_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pass_lbl.setStyleSheet(f"color: {pass_color}; font-size: 14px; font-weight: bold;")

            row.addWidget(field_lbl)
            row.addWidget(calc_lbl, 1)
            row.addWidget(report_lbl, 1)
            row.addWidget(pass_lbl)
            row.addStretch()

            container = QWidget()
            container.setLayout(row)
            self._fields_layout.addWidget(container)
            self._verify_result_widgets.append(container)

    def _clear_verify_results(self):
        for w in self._verify_result_widgets:
            w.deleteLater()
        self._verify_result_widgets.clear()

    def _reset_status(self):
        T = self._theme
        self._status_indicator.setText("")
        self._status_indicator.setStyleSheet(
            f"font-size: 16px; border-radius: 14px; background: {T.BORDER()};")
        self._verify_btn.setEnabled(False)
        self._calculated.clear()
        self._clear_verify_results()

    # ────────────── 主题刷新 ──────────────

    def refresh_theme(self):
        """主题变化时刷新样式"""
        T = self._theme
        self._tab_bar.setStyleSheet(f"background: {T.CARD()}; border-radius: 6px;")
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {T.BORDER()}; background: {T.CARD()}; border-radius: 6px; }}")
        self._form_container.setStyleSheet(f"background: {T.CARD()};")
        self._form_title.setStyleSheet(f"color: {T.TEXT()}; padding: 2px 0;")
        self._action_bar.setStyleSheet(f"background: {T.CARD()}; border-radius: 6px;")
        self._calc_btn.setStyleSheet(T.BTN_PRIMARY())
        self._verify_btn.setStyleSheet(f"""
            QPushButton {{
                background: {T.SUCCESS()}; color: white; border: none;
                border-radius: 4px; padding: 6px 18px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #1E8449; }}
            QPushButton:pressed {{ background: #145A32; }}
            QPushButton:disabled {{ background: {T.BORDER()}; color: {T.TEXT_SEC()}; }}
        """)
        # 刷新标签按钮样式
        for btn in self._tab_buttons.values():
            btn.setStyleSheet(f"""
                QPushButton {{
                    font-size: 11px; font-weight: 600;
                    color: {T.TEXT_SEC()}; background: transparent;
                    border: 1px solid transparent; border-radius: 4px;
                    padding: 2px 10px;
                }}
                QPushButton:hover {{
                    color: {T.PRIMARY()}; background: {T.HOVER()};
                }}
                QPushButton:checked {{
                    color: white; background: {T.PRIMARY()};
                    border-color: {T.PRIMARY()};
                }}
            """)
        # 重建表单以刷新输入框样式
        if self._test_type:
            current_ocr = self._ocr_text
            self._build_form_from_template()
            if current_ocr:
                self._auto_fill_from_ocr()
