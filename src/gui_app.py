"""
GUI 应用模块 (PyQt6)
现代 Notion/Linear 风格界面，包含 PDF 视图、Tab 切换、异常列表、设置选项
"""

import os
import sys
from typing import Optional, Dict, List, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QScrollArea, QListWidget, QListWidgetItem,
    QMenuBar, QMenu, QStatusBar, QFileDialog,
    QMessageBox, QPushButton, QLineEdit, QProgressBar,
    QColorDialog, QSlider, QDialog, QFormLayout, QTextEdit,
    QSizePolicy, QSplitter, QSplashScreen, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox,
)
from PyQt6.QtGui import (
    QImage, QPixmap, QColor, QFont, QCursor, QIcon, QPainter,
    QAction, QPen, QBrush, QPolygonF, QMouseEvent,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QPointF, QRectF

from core_checker import ReportChecker
from config import TEST_CATEGORIES, GUI_CONFIG, get_template_display_name
from ai_config import (PROVIDER_PRESETS, load_ai_config, mask_key as mask_ai_key,
                       save_ai_config)
from ai_ocr import (AI_ENGINE_NAME, extract_fields_from_text,
                    test_connection as test_ai_connection)

# =========================== 主题常量 ===========================

# 预设配色方案定义
# 每套方案包含：名称、背景色、卡片色、主色、主色浅、成功/危险/警告/信息色、文字色、次文字色、边框色、悬停色
COLOR_SCHEMES = {
    "深蓝商务": {
        "name": "深蓝商务",
        "bg": "#F5F6F8", "card": "#FFFFFF", "primary": "#2C3E50",
        "primary_light": "#34495E", "success": "#27AE60", "danger": "#E74C3C",
        "warning": "#F39C12", "info": "#3498DB", "text": "#2C3E50",
        "text_sec": "#7F8C8D", "border": "#E8EAED", "hover": "#ECEEF1",
        "table_alt_bg": "#FAFBFC", "table_header_bg": "#F8F9FA",
    },
    "清新墨绿": {
        "name": "清新墨绿",
        "bg": "#F0F5F0", "card": "#FFFFFF", "primary": "#1B5E20",
        "primary_light": "#2E7D32", "success": "#388E3C", "danger": "#C62828",
        "warning": "#F57F17", "info": "#1565C0", "text": "#1B3A1B",
        "text_sec": "#6B8E6B", "border": "#D0E0D0", "hover": "#E8F0E8",
        "table_alt_bg": "#F5FAF5", "table_header_bg": "#E8F0E8",
    },
    "暖橙科技": {
        "name": "暖橙科技",
        "bg": "#FFF8F0", "card": "#FFFFFF", "primary": "#E65100",
        "primary_light": "#F57C00", "success": "#2E7D32", "danger": "#C62828",
        "warning": "#FF8F00", "info": "#0277BD", "text": "#3E2723",
        "text_sec": "#8D6E63", "border": "#F0E0D0", "hover": "#FFF0E0",
        "table_alt_bg": "#FFFBF5", "table_header_bg": "#FFF0E0",
    },
    "暗夜护眼": {
        "name": "暗夜护眼",
        "bg": "#1E1E2E", "card": "#2A2A3E", "primary": "#7C8FE8",
        "primary_light": "#9AADF0", "success": "#4CAF50", "danger": "#EF5350",
        "warning": "#FFA726", "info": "#42A5F5", "text": "#E0E0E0",
        "text_sec": "#9E9E9E", "border": "#3A3A4E", "hover": "#363650",
        "table_alt_bg": "#303048", "table_header_bg": "#363650",
    },
    "简约灰白": {
        "name": "简约灰白",
        "bg": "#EEEEEE", "card": "#FFFFFF", "primary": "#424242",
        "primary_light": "#616161", "success": "#43A047", "danger": "#E53935",
        "warning": "#FB8C00", "info": "#1E88E5", "text": "#212121",
        "text_sec": "#757575", "border": "#D0D0D0", "hover": "#E0E0E0",
        "table_alt_bg": "#F5F5F5", "table_header_bg": "#EEEEEE",
    },
    "淡紫优雅": {
        "name": "淡紫优雅",
        "bg": "#F5F0FA", "card": "#FFFFFF", "primary": "#6A1B9A",
        "primary_light": "#8E24AA", "success": "#2E7D32", "danger": "#C62828",
        "warning": "#F9A825", "info": "#1565C0", "text": "#311B52",
        "text_sec": "#7E57C2", "border": "#E1D5F0", "hover": "#F0E8F8",
        "table_alt_bg": "#F8F4FC", "table_header_bg": "#F0E8F8",
    },
}

DEFAULT_SCHEME_NAME = "深蓝商务"
R = "8px"
RS = "6px"


class Theme:
    """动态主题 — 根据当前配色方案生成所有样式"""
    _scheme = COLOR_SCHEMES[DEFAULT_SCHEME_NAME]

    @classmethod
    def set_scheme(cls, name: str):
        if name in COLOR_SCHEMES:
            cls._scheme = COLOR_SCHEMES[name]

    @classmethod
    def get_scheme_name(cls) -> str:
        return cls._scheme["name"]

    # ── 颜色属性 ──
    @classmethod
    def prop(cls, key: str) -> str:
        return cls._scheme.get(key, COLOR_SCHEMES[DEFAULT_SCHEME_NAME][key])

    @classmethod
    def BG(cls): return cls.prop("bg")
    @classmethod
    def CARD(cls): return cls.prop("card")
    @classmethod
    def PRIMARY(cls): return cls.prop("primary")
    @classmethod
    def PRIMARY_LIGHT(cls): return cls.prop("primary_light")
    @classmethod
    def SUCCESS(cls): return cls.prop("success")
    @classmethod
    def DANGER(cls): return cls.prop("danger")
    @classmethod
    def WARNING(cls): return cls.prop("warning")
    @classmethod
    def INFO(cls): return cls.prop("info")
    @classmethod
    def TEXT(cls): return cls.prop("text")
    @classmethod
    def TEXT_SEC(cls): return cls.prop("text_sec")
    @classmethod
    def BORDER(cls): return cls.prop("border")
    @classmethod
    def HOVER(cls): return cls.prop("hover")
    @classmethod
    def TABLE_ALT_BG(cls): return cls.prop("table_alt_bg")
    @classmethod
    def TABLE_HEADER_BG(cls): return cls.prop("table_header_bg")

    # ── 全局 QSS ──
    @classmethod
    def global_stylesheet(cls) -> str:
        s = cls._scheme
        return f"""
        /* 全局背景 */
        QMainWindow, QDialog, QWidget#centralWidget {{ background: {s['bg']}; }}
        QWidget {{ color: {s['text']}; font-family: "Microsoft YaHei", "Segoe UI", sans-serif; }}

        /* 菜单栏 */
        QMenuBar {{ background: {s['card']}; color: {s['text']}; border-bottom: 1px solid {s['border']}; }}
        QMenuBar::item:selected {{ background: {s['hover']}; }}
        QMenu {{ background: {s['card']}; color: {s['text']}; border: 1px solid {s['border']}; border-radius: {RS}; }}
        QMenu::item:selected {{ background: {s['primary']}; color: white; }}

        /* 滚动条 */
        QScrollBar:vertical {{ background: {s['bg']}; width: 8px; border-radius: 4px; }}
        QScrollBar::handle:vertical {{ background: {s['border']}; border-radius: 4px; min-height: 30px; }}
        QScrollBar::handle:vertical:hover {{ background: {s['text_sec']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

        /* 状态栏 */
        QStatusBar {{ background: {s['card']}; color: {s['text_sec']}; border-top: 1px solid {s['border']}; font-size: 12px; }}

        /* 输入框 */
        QLineEdit {{ background: {s['card']}; color: {s['text']}; border: 1px solid {s['border']}; border-radius: {RS}; padding: 4px 8px; }}

        /* 提示框 */
        QToolTip {{ background: {s['primary']}; color: white; border: none; border-radius: 4px; padding: 4px 8px; }}
        """

    # ── 组件样式 ──
    @classmethod
    def BTN_PRIMARY(cls):
        s = cls._scheme
        return (
            f"QPushButton {{ background: {s['primary']}; color: white; font-weight: 600; border: none;"
            f" border-radius: {RS}; padding: 8px 18px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {s['primary_light']}; }}"
            f"QPushButton:pressed {{ background: #1A252F; }}"
            f"QPushButton:disabled {{ background: {s['border']}; color: {s['text_sec']}; }}"
        )

    @classmethod
    def BTN_SECONDARY(cls):
        s = cls._scheme
        return (
            f"QPushButton {{ background: {s['card']}; color: {s['text']}; border: 1px solid {s['border']};"
            f" border-radius: {RS}; padding: 6px 12px; font-weight: 500; }}"
            f"QPushButton:hover {{ background: {s['hover']}; border-color: #CBD0D8; }}"
            f"QPushButton:pressed {{ background: #DFE1E5; }}"
        )

    @classmethod
    def BTN_TOOL(cls):
        s = cls._scheme
        return (
            f"QPushButton {{ background: {s['card']}; color: {s['text']}; border: 1px solid {s['border']};"
            f" border-radius: {RS}; font-weight: 600; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {s['hover']}; border-color: #CBD0D8; }}"
            f"QPushButton:checked {{ background: {s['primary']}; color: white; border-color: {s['primary']}; }}"
        )

    @classmethod
    def LIST_WIDGET(cls):
        s = cls._scheme
        return (
            f"QListWidget {{ background: {s['card']}; color: {s['text']}; font-size: 12px;"
            f" border: 1px solid {s['border']}; border-radius: {R}; padding: 6px; outline: none; }}"
            f"QListWidget::item {{ padding: 6px 4px; border-bottom: 1px solid #F2F3F5; }}"
            f"QListWidget::item:last {{ border-bottom: none; }}"
            f"QListWidget::item:alternate {{ background: {s['table_alt_bg']}; }}"
        )

    @classmethod
    def TEXT_EDIT(cls):
        s = cls._scheme
        return (
            f"QTextEdit {{ background: {s['card']}; color: {s['text']}; font-size: 12px;"
            f" border: 1px solid {s['border']}; border-radius: {R}; padding: 10px; line-height: 1.5; }}"
        )

    @classmethod
    def TAB_STYLE(cls):
        s = cls._scheme
        return f"""
        QTabWidget::pane {{ border: none; background: transparent; }}
        QTabBar::tab {{ height: 32px; padding: 6px 16px; margin: 0 2px;
            background-color: {s['card']}; border: none; border-radius: {RS};
            font-size: 13px; color: {s['text_sec']}; font-weight: 500; }}
        QTabBar::tab:hover {{ background-color: {s['hover']}; }}
        QTabBar::tab:selected {{ background-color: {s['primary']}; color: white; font-weight: 600; }}
        """

    @classmethod
    def SUB_TAB_STYLE(cls):
        s = cls._scheme
        return f"""
        QTabWidget::pane {{ border: none; background: transparent; top: -1px; }}
        QTabBar::tab {{ height: 28px; padding: 4px 10px; margin: 0 1px;
            background-color: {s['card']}; border: none; border-radius: {RS};
            font-size: 12px; color: {s['text_sec']}; font-weight: 500; }}
        QTabBar::tab:hover {{ background-color: {s['hover']}; }}
        QTabBar::tab:selected {{ background-color: {s['primary']}; color: white; font-weight: 600; }}
        """

    @classmethod
    def PROGRESS_BAR(cls):
        s = cls._scheme
        return (
            f"QProgressBar {{ background: {s['border']}; border: none; border-radius: 4px; height: 8px;"
            f" text-align: center; font-size: 11px; color: {s['text']}; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0 y1:0 x2:1 y2:0,"
            f" stop:0 #2ECC71, stop:1 #27AE60); border-radius: 4px; }}"
        )

    @classmethod
    def TABLE_WIDGET(cls):
        s = cls._scheme
        return (
            f"QTableWidget {{ background: {s['card']}; color: {s['text']}; font-size: 12px;"
            f" border: 1px solid {s['border']}; border-radius: {R}; gridline-color: #F0F1F3;"
            f" selection-background-color: #E8F0FE; selection-color: {s['text']}; }}"
            f"QTableWidget::item {{ padding: 4px 8px; }}"
            f"QHeaderView::section {{ background: {s['table_header_bg']}; color: {s['text']}; font-size: 12px;"
            f" font-weight: 600; padding: 6px 8px; border: none;"
            f" border-bottom: 2px solid {s['primary']}; border-right: 1px solid {s['border']}; }}"
            f"QHeaderView::section:last {{ border-right: none; }}"
        )


# =========================== 闪屏 ===========================

def create_splash() -> QSplashScreen:
    """创建启动闪屏，显示 Logo + 加载提示"""
    pixmap = QPixmap(420, 220)
    pixmap.fill(QColor(Theme.BG()))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # 卡片背景
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(Theme.CARD())))
    painter.drawRoundedRect(10, 10, 400, 200, 12, 12)
    # 标题（偏上）
    title_rect = pixmap.rect().adjusted(0, -20, 0, 0)
    painter.setPen(QColor(Theme.PRIMARY()))
    painter.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
    painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "ReportChecker")
    # 副标题（标题下方，不重叠）
    sub_rect = pixmap.rect().adjusted(0, 40, 0, 0)
    painter.setFont(QFont("Microsoft YaHei", 10))
    painter.setPen(QColor(Theme.TEXT_SEC()))
    painter.drawText(sub_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                     "电动工具测试报告校验工具")
    # 加载提示（偏底部，上移约 8px 避免被卡片底边裁切）
    hint_rect = pixmap.rect().adjusted(0, 0, 0, -18)
    painter.setFont(QFont("Microsoft YaHei", 9))
    painter.setPen(QColor(Theme.TEXT_SEC()))
    painter.drawText(hint_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                     "正在初始化...")
    painter.end()
    splash = QSplashScreen(pixmap)
    return splash


# =========================== 设置对话框 ===========================

class SettingsDialog(QDialog):
    """设置对话框 — 配色方案选择 + 透明度"""

    def __init__(self, parent=None, current_scheme: str = DEFAULT_SCHEME_NAME, opacity: int = 95):
        super().__init__(parent)
        self._scheme_name = current_scheme
        self._opacity = opacity
        self._card_buttons: Dict[str, QPushButton] = {}
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("外观设置")
        self.setFixedSize(580, 460)
        self.setStyleSheet(f"background: {Theme.BG()};")
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # —— 配色方案卡片 ——
        card = QWidget()
        card.setStyleSheet(f"background: {Theme.CARD()}; border-radius: {R};")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(12)

        card_title = QLabel("配色方案")
        card_title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        card_title.setStyleSheet(f"color: {Theme.TEXT()};")
        card_layout.addWidget(card_title)

        # 方案网格：2列 × 3行
        grid = QHBoxLayout()
        grid.setSpacing(10)
        col_left = QVBoxLayout()
        col_right = QVBoxLayout()
        col_left.setSpacing(10)
        col_right.setSpacing(10)

        scheme_names = list(COLOR_SCHEMES.keys())
        for i, name in enumerate(scheme_names):
            btn = self._create_scheme_card(name)
            if i % 2 == 0:
                col_left.addWidget(btn)
            else:
                col_right.addWidget(btn)

        grid.addLayout(col_left)
        grid.addLayout(col_right)
        card_layout.addLayout(grid)
        layout.addWidget(card)

        # —— 透明度卡片 ——
        op_card = QWidget()
        op_card.setStyleSheet(f"background: {Theme.CARD()}; border-radius: {R};")
        op_card_layout = QVBoxLayout(op_card)
        op_card_layout.setContentsMargins(20, 16, 20, 16)
        op_card_layout.setSpacing(10)

        op_title = QLabel("窗口透明度")
        op_title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        op_title.setStyleSheet(f"color: {Theme.TEXT()};")
        op_card_layout.addWidget(op_title)

        op_row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(self._opacity)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.opacity_value_label = QLabel(f"{self._opacity}%")
        self.opacity_value_label.setStyleSheet(f"color: {Theme.TEXT_SEC()}; min-width: 36px; font-size: 14px; font-weight: bold;")
        op_row.addWidget(self.opacity_slider)
        op_row.addWidget(self.opacity_value_label)
        op_card_layout.addLayout(op_row)
        layout.addWidget(op_card)

        # —— 按钮 ——
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ok_btn.setStyleSheet(Theme.BTN_PRIMARY())
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setStyleSheet(Theme.BTN_SECONDARY())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        self.setLayout(layout)

    def _create_scheme_card(self, scheme_name: str) -> QPushButton:
        s = COLOR_SCHEMES[scheme_name]
        is_active = (scheme_name == self._scheme_name)
        # 用扁平按钮模拟卡片
        btn = QPushButton()
        btn.setFixedSize(255, 72)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        # 绘制预览：左侧色条 + 右侧名称
        pixmap = QPixmap(255, 72)
        pixmap.fill(QColor(s["card"]))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 左侧主色竖条
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(s["primary"])))
        painter.drawRoundedRect(0, 0, 8, 72, 4, 4)

        # 模拟色块：BG / Card / Primary / Success / Danger
        swatch_y = 14
        swatch_h = 24
        swatches = [
            (s["bg"], "背景"),
            (s["card"], "卡片"),
            (s["primary"], "主色"),
            (s["success"], "成功"),
            (s["danger"], "强调"),
        ]
        painter.setPen(QPen(QColor(s["border"]), 1))
        x = 20
        for color, _label in swatches:
            painter.setBrush(QBrush(QColor(color)))
            painter.drawRoundedRect(x, swatch_y, swatch_h, swatch_h, 4, 4)
            x += swatch_h + 4

        # 方案名称
        painter.setPen(QColor(s["text"]))
        painter.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        painter.drawText(20, 60, scheme_name)

        # 当前选中标记
        if is_active:
            painter.setPen(QPen(QColor(s["primary"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(1, 1, 253, 70, 6, 6)
            # 勾
            check_x = 228
            painter.setPen(QPen(QColor(s["primary"]), 3))
            painter.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
            painter.drawText(check_x, 50, "✓")

        painter.end()
        btn.setIcon(QIcon(pixmap))
        btn.setIconSize(QSize(255, 72))
        btn.setFlat(True)
        btn.clicked.connect(lambda: self._select_scheme(scheme_name))
        self._card_buttons[scheme_name] = btn
        return btn

    def _select_scheme(self, scheme_name: str):
        if scheme_name == self._scheme_name:
            return
        self._scheme_name = scheme_name
        # 刷新所有卡片图标
        for name, btn in self._card_buttons.items():
            s = COLOR_SCHEMES[name]
            is_active = (name == scheme_name)
            pixmap = QPixmap(255, 72)
            pixmap.fill(QColor(s["card"]))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(s["primary"])))
            painter.drawRoundedRect(0, 0, 8, 72, 4, 4)
            swatch_y = 14
            swatch_h = 24
            swatches = [
                (s["bg"], "背景"), (s["card"], "卡片"), (s["primary"], "主色"),
                (s["success"], "成功"), (s["danger"], "强调"),
            ]
            painter.setPen(QPen(QColor(s["border"]), 1))
            x = 20
            for color, _label in swatches:
                painter.setBrush(QBrush(QColor(color)))
                painter.drawRoundedRect(x, swatch_y, swatch_h, swatch_h, 4, 4)
                x += swatch_h + 4
            painter.setPen(QColor(s["text"]))
            painter.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
            painter.drawText(20, 60, name)
            if is_active:
                painter.setPen(QPen(QColor(s["primary"]), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(1, 1, 253, 70, 6, 6)
                painter.setPen(QPen(QColor(s["primary"]), 3))
                painter.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
                painter.drawText(228, 50, "✓")
            painter.end()
            btn.setIcon(QIcon(pixmap))

    def _on_opacity_changed(self, value: int):
        self._opacity = value
        self.opacity_value_label.setText(f"{value}%")

    def get_scheme_name(self) -> str:
        return self._scheme_name

    def get_opacity(self) -> int:
        return self._opacity


# =========================== AI 模型设置对话框 ===========================

class AISettingsDialog(QDialog):
    """AI 视觉模型设置 — 地址、模型名称、API Key（模型名不写死，可自由修改）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg = load_ai_config()
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("AI 模型设置")
        self.setFixedSize(520, 420)
        self.setStyleSheet(f"background: {Theme.BG()};")

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        card = QWidget()
        card.setStyleSheet(f"background: {Theme.CARD()}; border-radius: {R};")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(10)

        title = QLabel("AI 视觉模型识别")
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Theme.TEXT()};")
        card_layout.addWidget(title)

        hint = QLabel("两段式：识别模型读页面 → 抽取模型出字段。在右下角「模型」选择「AI 视觉模型」后生效。")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: 12px; color: {Theme.TEXT_SEC()};")
        card_layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)

        self.provider_combo = QComboBox()
        for key, preset in PROVIDER_PRESETS.items():
            self.provider_combo.addItem(preset['label'], key)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("服务商", self.provider_combo)

        self.base_url_edit = QLineEdit(self._cfg.get('base_url', ''))
        self.base_url_edit.setPlaceholderText('https://.../v1')
        form.addRow("Base URL", self.base_url_edit)

        self.ocr_combo = QComboBox()
        self.ocr_combo.setEditable(True)
        self.ocr_combo.setCurrentText(self._cfg.get('ocr_model', ''))
        form.addRow("识别模型", self.ocr_combo)

        self.extract_combo = QComboBox()
        self.extract_combo.setEditable(True)
        self.extract_combo.setCurrentText(self._cfg.get('extract_model', ''))
        form.addRow("抽取模型", self.extract_combo)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(
            f"已保存 {mask_ai_key(self._cfg.get('api_key', ''))}（留空表示不修改）"
            if self._cfg.get('api_key') else 'sk-...')
        form.addRow("API Key", self.key_edit)

        card_layout.addLayout(form)

        self.result_label = QLabel('')
        self.result_label.setWordWrap(True)
        self.result_label.setVisible(False)
        card_layout.addWidget(self.result_label)

        layout.addWidget(card)

        btn_row = QHBoxLayout()
        test_btn = QPushButton("测试连接")
        test_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        test_btn.setStyleSheet(Theme.BTN_SECONDARY())
        test_btn.clicked.connect(self._test_connection)
        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        ok_btn = QPushButton("保存")
        ok_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ok_btn.setStyleSheet(Theme.BTN_PRIMARY())
        ok_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.setStyleSheet(Theme.BTN_SECONDARY())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)
        self._sync_provider_from_config()

    def _sync_provider_from_config(self):
        """按已保存的 Base URL 反查服务商，找不到则选自定义"""
        current = self._cfg.get('base_url', '')
        for idx in range(self.provider_combo.count()):
            key = self.provider_combo.itemData(idx)
            if PROVIDER_PRESETS[key]['base_url'] == current:
                self.provider_combo.blockSignals(True)
                self.provider_combo.setCurrentIndex(idx)
                self.provider_combo.blockSignals(False)
                self._fill_models(key, keep_current=True)
                return
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentIndex(self.provider_combo.count() - 1)
        self.provider_combo.blockSignals(False)
        self.ocr_combo.clear()
        self.extract_combo.clear()

    def _fill_models(self, provider: str, keep_current: bool = False):
        ocr_cur = self.ocr_combo.currentText() if keep_current else ''
        ext_cur = self.extract_combo.currentText() if keep_current else ''
        models = PROVIDER_PRESETS[provider]['models']
        for combo, cur in ((self.ocr_combo, ocr_cur), (self.extract_combo, ext_cur)):
            combo.clear()
            combo.addItems(models)
            combo.setCurrentText(cur)

    def _on_provider_changed(self, index: int):
        key = self.provider_combo.itemData(index)
        if not key:
            return
        preset = PROVIDER_PRESETS[key]
        self.base_url_edit.setText(preset['base_url'])
        models = preset['models']
        for combo in (self.ocr_combo, self.extract_combo):
            combo.clear()
            combo.addItems(models)
            if models:
                combo.setCurrentText(models[0])

    def _collect(self) -> dict:
        return {
            'base_url': self.base_url_edit.text().strip(),
            'ocr_model': self.ocr_combo.currentText().strip(),
            'extract_model': self.extract_combo.currentText().strip(),
            'api_key': self.key_edit.text().strip() or self._cfg.get('api_key', ''),
        }

    def _test_connection(self):
        ok, msg = test_ai_connection(self._collect())
        self.result_label.setVisible(True)
        color = Theme.SUCCESS() if ok else Theme.DANGER()
        self.result_label.setStyleSheet(f"font-size: 12px; color: {color};")
        self.result_label.setText(msg)

    def _save(self):
        cfg = self._collect()
        if not cfg['base_url'] or not cfg['ocr_model'] or not cfg['extract_model']:
            QMessageBox.warning(self, "配置不完整", "请填写 Base URL、识别模型和抽取模型")
            return
        save_ai_config(base_url=cfg['base_url'], ocr_model=cfg['ocr_model'],
                       extract_model=cfg['extract_model'],
                       api_key=self.key_edit.text().strip() or None)
        self.accept()


# =========================== 工作线程 ===========================

class CheckWorker(QThread):
    """校验工作线程 — 后台执行 OCR 识别和规则校验"""
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal(bool, list)

    def __init__(self, checker: ReportChecker, template_name: str):
        super().__init__()
        self._checker = checker
        self._template_name = template_name

    def run(self):
        try:
            self.progress_updated.emit(20, "加载模板...")
            self._checker.load_template(self._template_name)
            self.progress_updated.emit(50, "提取字段数据...")
            self._checker.extract_all_fields()
            self.progress_updated.emit(80, "执行规则校验...")
            errors = self._checker.check_rules()
            self.progress_updated.emit(100, "校验完成")
            self.finished.emit(True, errors)
        except Exception:
            self.finished.emit(False, [])


class OCRPageWorker(QThread):
    """OCR 当前页工作线程"""
    finished = pyqtSignal(object, str)
    engine_try = pyqtSignal(str, bool)
    engine_result = pyqtSignal(str, bool)
    progress = pyqtSignal(float)

    def __init__(self, checker: ReportChecker, page_num: int, draw_boxes: bool):
        super().__init__()
        self._checker = checker
        self._page_num = page_num
        self._draw_boxes = draw_boxes

    def run(self):
        try:
            self.progress.emit(0.05)
            result = self._checker.render_page_with_highlight(
                self._page_num, draw_boxes=self._draw_boxes,
                on_engine_try=lambda n, a: self.engine_try.emit(n, a),
                on_engine_result=lambda n, s: self.engine_result.emit(n, s),
            )
            self.progress.emit(0.8)
            img_array = result[0] if isinstance(result, tuple) else result
            used_engine = result[1] if isinstance(result, tuple) else ""
            self.finished.emit(img_array, used_engine)
        except Exception:
            self.finished.emit(None, "")


class OCRMultiEngineWorker(QThread):
    """自动质量保障模式：用每个引擎单独识别，返回所有结果

    主线程根据填入率选最佳结果。
    """
    finished = pyqtSignal(object, list)  # (img_array, [(engine_name, text), ...])
    engine_try = pyqtSignal(str, bool)
    engine_result = pyqtSignal(str, bool)
    progress = pyqtSignal(float)

    def __init__(self, checker: ReportChecker, page_num: int, draw_boxes: bool):
        super().__init__()
        self._checker = checker
        self._page_num = page_num
        self._draw_boxes = draw_boxes

    def run(self):
        try:
            self.progress.emit(0.05)
            # 用高DPI渲染页面图像，提升OCR精度
            render_result = self._checker.render_page(self._page_num, dpi=450)
            if not render_result:
                self.finished.emit(None, [])
                return
            img_array, _ = render_result
            self.progress.emit(0.3)

            # 如果是Adobe模式，优先尝试COM文本提取
            com_text = None
            adobe_capture = getattr(self._checker, '_adobe_live_capture', None)
            if adobe_capture and adobe_capture.has_com_text_extraction:
                try:
                    com_text = adobe_capture.extract_text_via_com(self._page_num)
                except Exception:
                    com_text = None

            # 用每个引擎单独识别
            all_results = self._checker.ocr_engine.recognize_region_all_engines(
                img_array,
                on_engine_try=lambda n, a: self.engine_try.emit(n, a),
                on_engine_result=lambda n, s: self.engine_result.emit(n, s),
            )
            self.progress.emit(0.9)

            # 如果COM文本提取成功，加到结果列表最前面
            if com_text and com_text.strip():
                all_results.insert(0, ("COM文本提取", com_text))

            self.finished.emit(img_array, all_results)
        except Exception:
            self.finished.emit(None, [])


class OCRAllWorker(QThread):
    """OCR 全部页面工作线程 —— 逐页识别整个文档"""
    progress = pyqtSignal(int, int, str)
    engine_try = pyqtSignal(str, bool)
    engine_result = pyqtSignal(str, bool)
    page_done = pyqtSignal(int, object, str)
    all_done = pyqtSignal(bool, str)

    def __init__(self, checker: ReportChecker, draw_boxes: bool):
        super().__init__()
        self._checker = checker
        self._draw_boxes = draw_boxes
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            page_count = self._checker.get_page_count()
            for p in range(page_count):
                if self._cancelled:
                    self.all_done.emit(False, "用户取消")
                    return
                self.progress.emit(p + 1, page_count, f"正在识别第 {p + 1}/{page_count} 页...")
                try:
                    result = self._checker.render_page_with_highlight(
                        p, draw_boxes=self._draw_boxes,
                        on_engine_try=lambda n, a: self.engine_try.emit(n, a),
                        on_engine_result=lambda n, s: self.engine_result.emit(n, s),
                    )
                    img_array = result[0] if isinstance(result, tuple) else result
                    used_engine = result[1] if isinstance(result, tuple) else ""
                    self.page_done.emit(p, img_array, used_engine)
                except Exception:
                    self.page_done.emit(p, None, "")
            self.all_done.emit(True, f"全部 {page_count} 页识别完成")
        except Exception:
            self.all_done.emit(False, "识别过程发生错误")


# =========================== PDF 视图组件 ===========================

class PDFViewer(QWidget):
    """PDF 视图组件 — 显示渲染后的页面图像，支持缩放/适应窗口"""

    # 点击空白区域打开文件的信号
    clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._bg_color = Theme.BG()
        self._scale_factor = 1.0
        self._original_pixmap = None
        self._fit_mode = True
        self._progress = 0.0
        self._init_ui()

    def set_progress(self, value: float):
        """设置进度 0.0~1.0，在 scroll_area 底部画一条细进度条 + 百分比标签。"""
        self._progress = max(0.0, min(1.0, float(value)))
        if not hasattr(self, '_progress_bar'):
            return
        if self._progress <= 0.0:
            self._progress_bar.hide()
            self._progress_pct.hide()
            return
        # 进度 >= 1.0 也显示（100% 完成态，不消失）
        if self._progress >= 1.0:
            self._progress = 1.0
        # 关键：真正更新进度条控件的位置和值
        sa = self.scroll_area
        sa_w = sa.viewport().width()
        sa_h = sa.height()
        if sa_w <= 0:
            return
        bar_h = 4
        pct = int(self._progress * 100)
        self._progress_bar.setGeometry(2, sa_h - bar_h - 2, sa_w - 4, bar_h)
        self._progress_bar.setValue(pct)
        self._progress_bar.show()
        self._progress_bar.raise_()
        # 百分比标签，紧追进度条右侧
        fill_w = max(bar_h, int((sa_w - 4) * self._progress))
        self._progress_pct.setText(f"{pct}%")
        self._progress_pct.adjustSize()
        pct_x = min(2 + fill_w + 4, sa_w - self._progress_pct.width() - 2)
        pct_x = max(2, pct_x)
        self._progress_pct.move(pct_x, sa_h - bar_h - 20)
        self._progress_pct.show()
        self._progress_pct.raise_()
        QApplication.processEvents()  # 强制刷新进度显示

    def reset_progress(self):
        """重置进度（打开新文件或重新识别时调用）。"""
        self._progress = 0.0
        if hasattr(self, '_progress_bar'):
            self._progress_bar.setValue(0)
            self._progress_bar.hide()
        if hasattr(self, '_progress_pct'):
            self._progress_pct.hide()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_progress_bar') and self._progress_bar.isVisible():
            self.set_progress(self._progress)
        if self._fit_mode and self._original_pixmap is not None:
            self._apply_fit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._original_pixmap is None:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _init_ui(self):
        self.layout = QVBoxLayout()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(f"background-color: {self._bg_color};")
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            f"QScrollArea {{ border: 2px solid {Theme.BORDER()}; background: {self._bg_color}; }}"
            f"QScrollArea::viewport {{ border: none; background: {self._bg_color}; }}")
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.addWidget(self.scroll_area)
        self.setLayout(self.layout)
        # 进度条（QProgressBar，放在 scroll_area 上，底部绝对定位）
        self._progress_bar = QProgressBar(self.scroll_area)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setStyleSheet(
            "QProgressBar { border: none; border-radius: 2px; background: rgba(255,255,255,200); }"
            "QProgressBar::chunk { background: #2ECC71; border-radius: 2px; }")
        self._progress_bar.hide()
        # 百分比标签，跟在进度条右侧
        self._progress_pct = QLabel(self.scroll_area)
        self._progress_pct.setStyleSheet(
            f"font-size: 11px; color: {Theme.SUCCESS()}; font-weight: bold;"
            "background: rgba(255,255,255,220); padding: 1px 5px; border-radius: 3px;")
        self._progress_pct.hide()

    def set_image(self, image_array):
        if image_array is None:
            self.image_label.clear()
            self._original_pixmap = None
            return
        height, width, channel = image_array.shape
        bytes_per_line = channel * width
        img_data = image_array.copy()
        q_image = QImage(img_data.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        self._original_pixmap = QPixmap.fromImage(q_image)
        if self._fit_mode:
            QTimer.singleShot(0, self._apply_fit)
        else:
            self._apply_scale()

    def _compute_fit_factor(self) -> float:
        if self._original_pixmap is None:
            return 1.0
        vp = self.scroll_area.viewport()
        avail_w = max(1, vp.width() - 4)
        avail_h = max(1, vp.height() - 4)
        pw, ph = self._original_pixmap.width(), self._original_pixmap.height()
        if pw <= 0 or ph <= 0:
            return 1.0
        return min(avail_w / pw, avail_h / ph)

    def _apply_fit(self):
        if self._original_pixmap is None:
            return
        self._scale_factor = self._compute_fit_factor()
        self._do_scale()

    def _apply_scale(self):
        if self._original_pixmap is None:
            return
        self._do_scale()

    def _do_scale(self):
        if self._original_pixmap is None:
            return
        new_w = max(1, int(self._original_pixmap.width() * self._scale_factor))
        new_h = max(1, int(self._original_pixmap.height() * self._scale_factor))
        scaled = self._original_pixmap.scaled(new_w, new_h,
                                              Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.adjustSize()

    def zoom_in(self):
        self._fit_mode = False
        self._scale_factor = min(self._scale_factor * 1.25, 5.0)
        self._apply_scale()

    def zoom_out(self):
        self._fit_mode = False
        self._scale_factor = max(self._scale_factor / 1.25, 0.5)
        self._apply_scale()

    def zoom_reset(self):
        self._fit_mode = True
        self._apply_fit()

    def get_scale_factor(self) -> float:
        return self._scale_factor

    def is_fit_mode(self) -> bool:
        return self._fit_mode

    def set_bg_color(self, color: str):
        self._bg_color = color
        self.image_label.setStyleSheet(f"background-color: {color};")
        self.scroll_area.setStyleSheet(
            f"QScrollArea {{ border: 2px solid {Theme.BORDER()}; background: {color}; }}"
            f"QScrollArea::viewport {{ border: none; background: {color}; }}")


# =========================== 异常列表组件 ===========================

class ErrorList(QWidget):
    """异常列表组件"""
    item_clicked = pyqtSignal(int, list)

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(Theme.LIST_WIDGET())
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.layout.addWidget(self.list_widget)
        self.setLayout(self.layout)

    def _on_item_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.item_clicked.emit(data.get('page_num', 0), data.get('rect', [0, 0, 0, 0]))

    def set_errors(self, errors: List[Dict[str, Any]]):
        self.list_widget.clear()
        for error in errors:
            level = error.get('level', 'info')
            message = error.get('message', '')
            item = QListWidgetItem(message)
            colors = {
                'error': (QColor(255, 0, 0), QColor(255, 200, 200)),
                'warning': (QColor(255, 165, 0), QColor(255, 255, 200)),
                'info': (QColor(0, 100, 0), QColor(200, 255, 200)),
            }
            fg, bg = colors.get(level, (QColor(Theme.TEXT()), QColor(Theme.CARD())))
            item.setForeground(fg)
            item.setBackground(bg)
            item.setData(Qt.ItemDataRole.UserRole, error)
            self.list_widget.addItem(item)


# =========================== Tab 内容组件 ===========================

# ── TabContent 已替换为 ReportFormPanel（见 report_form_panel.py）──


# =========================== 工具函数 ===========================

def _create_tool_icon() -> QIcon:
    """创建电动工具图标"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    body_color, accent_color, dark_color = QColor(60, 80, 120), QColor(220, 160, 40), QColor(40, 50, 70)
    pen = QPen(dark_color, 2)
    painter.setPen(pen)
    painter.setBrush(QBrush(accent_color))
    tip = QPolygonF([QPointF(2, 32), QPointF(18, 22), QPointF(18, 42)])
    painter.drawPolygon(tip)
    painter.setBrush(QBrush(body_color))
    painter.drawRect(18, 18, 20, 28)
    painter.setBrush(QBrush(dark_color))
    painter.drawRoundedRect(24, 44, 22, 16, 4, 4)
    painter.setBrush(QBrush(body_color))
    painter.drawRoundedRect(38, 14, 20, 36, 6, 6)
    painter.setPen(QPen(accent_color, 2))
    painter.drawLine(22, 24, 36, 24)
    painter.drawLine(22, 40, 36, 40)
    painter.setBrush(QBrush(QColor(255, 50, 50)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(52, 20, 4, 4)
    painter.end()
    return QIcon(pixmap)


# =========================== 主应用窗口 ===========================

class ReportCheckerApp(QMainWindow):
    """主应用窗口 — 现代 Notion/Linear 风格"""

    def __init__(self):
        super().__init__()
        self._checker = ReportChecker()
        self._current_pdf_path = ""
        self._current_page = 0
        self._bg_color = Theme.BG()
        self._opacity = 95
        self._show_boxes = False
        self._current_scheme = DEFAULT_SCHEME_NAME
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("ReportChecker — 电动工具测试报告校验工具")
        self.setStyleSheet(Theme.global_stylesheet())
        screen = QApplication.primaryScreen().availableGeometry()
        max_w, max_h = int(screen.width() * 0.9), int(screen.height() * 0.9)
        w = min(GUI_CONFIG['window_width'], max_w)
        h = min(GUI_CONFIG['window_height'], max_h)
        x = max(0, (screen.width() - w) // 2)
        y = max(0, (screen.height() - h) // 2)
        self.setGeometry(x, y, w, h)
        self.setWindowIcon(_create_tool_icon())
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()

    # ── 菜单栏 ──

    def _create_menu(self):
        menu_bar = self.menuBar()
        # 菜单栏样式由 global_stylesheet 统一管理

        file_menu = QMenu("文件", self)
        open_act = QAction("打开报告文件", self)
        open_act.triggered.connect(self._open_pdf)
        file_menu.addAction(open_act)
        live_act = QAction("从 Adobe 窗口捕获", self)
        live_act.setToolTip("不打开文件，直接检测已打开的 Adobe Acrobat 窗口进行识别")
        live_act.triggered.connect(self._capture_from_adobe_window)
        file_menu.addAction(live_act)
        import_act = QAction("导入模板", self)
        import_act.triggered.connect(self._import_template)
        file_menu.addAction(import_act)
        new_act = QAction("新建模板", self)
        new_act.triggered.connect(self._new_template)
        file_menu.addAction(new_act)
        gen_act = QAction("生成 Word 底稿", self)
        gen_act.setToolTip("把 models/reports 下标准报告 PDF 转为 Word 版式底稿")
        gen_act.triggered.connect(self._generate_word_drafts)
        file_menu.addAction(gen_act)
        file_menu.addSeparator()
        exit_act = QAction("退出", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)
        menu_bar.addMenu(file_menu)

        settings_menu = QMenu("设置", self)
        appear_act = QAction("外观设置", self)
        appear_act.triggered.connect(self._show_settings)
        settings_menu.addAction(appear_act)
        ai_act = QAction("AI 模型设置", self)
        ai_act.setToolTip("配置 AI 视觉模型的接口地址、模型名称与 API Key")
        ai_act.triggered.connect(self._show_ai_settings)
        settings_menu.addAction(ai_act)
        menu_bar.addMenu(settings_menu)

        help_menu = QMenu("帮助", self)
        about_act = QAction("关于", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)
        menu_bar.addMenu(help_menu)

    # ── 主布局 ──

    def _create_main_layout(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = self._create_pdf_view()
        right = self._create_tabs()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setHandleWidth(4)
        init_w = max(800, self.width())
        splitter.setSizes([int(init_w * 0.38), int(init_w * 0.62)])
        outer.addWidget(splitter, 1)

    def _create_pdf_view(self) -> QWidget:
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # 文件名条 — 点击可打开文件
        self._file_name_bar = QLabel("未打开文件")
        self._file_name_bar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._file_name_bar.setToolTip("点击打开报告文件")
        self._file_name_bar.setStyleSheet(
            f"font-size: 12px; color: {Theme.TEXT_SEC()}; padding: 8px 14px;"
            f"background: {Theme.CARD()}; border-radius: {R}; border: 1px solid {Theme.BORDER()};"
            f"QLabel:hover {{ background: {Theme.HOVER()}; }}")
        self._file_name_bar.mousePressEvent = lambda e: self._open_pdf()
        lay.addWidget(self._file_name_bar)

        self.pdf_viewer = PDFViewer()
        # 未打开文件时点击 PDF 区域也可以打开文件
        self.pdf_viewer.clicked.connect(self._open_pdf)

        # 控制栏
        ctrl = QHBoxLayout()
        ctrl.setContentsMargins(6, 4, 6, 4)
        ctrl.setSpacing(6)

        # 缩放（只保留缩放控件，删除页码导航）
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setFixedSize(22, 22)
        self.zoom_out_button.setToolTip("缩小")
        self.zoom_out_button.setStyleSheet(Theme.BTN_TOOL())
        self.zoom_out_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.zoom_out_button.clicked.connect(self._zoom_out)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(38)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setStyleSheet(f"color: {Theme.TEXT_SEC()}; font-size: 11px; font-weight: 600;")

        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setFixedSize(22, 22)
        self.zoom_in_button.setToolTip("放大")
        self.zoom_in_button.setStyleSheet(Theme.BTN_TOOL())
        self.zoom_in_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.zoom_in_button.clicked.connect(self._zoom_in)

        self.zoom_reset_button = QPushButton("适应")
        self.zoom_reset_button.setFixedSize(36, 22)
        self.zoom_reset_button.setToolTip("适应窗口")
        self.zoom_reset_button.setStyleSheet(Theme.BTN_TOOL())
        self.zoom_reset_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.zoom_reset_button.clicked.connect(self._zoom_reset)

        # 分隔线
        sep = QLabel("│")
        sep.setStyleSheet(f"color: {Theme.BORDER()}; font-size: 16px;")
        ctrl.addWidget(sep)

        self.boxes_button = QPushButton("☐ 识别框")
        self.boxes_button.setFixedHeight(24)
        self.boxes_button.setMinimumWidth(72)
        self.boxes_button.setToolTip("显示 OCR 识别框")
        self.boxes_button.setStyleSheet(Theme.BTN_TOOL())
        self.boxes_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.boxes_button.setCheckable(True)
        self.boxes_button.setChecked(False)
        self.boxes_button.clicked.connect(self._toggle_boxes)

        # 识别并填入 — 放在识别框右侧，加醒目背景色
        self.ocr_button = QPushButton("识别并填入")
        self.ocr_button.setFixedHeight(24)
        self.ocr_button.setMinimumWidth(92)
        self.ocr_button.setToolTip("识别第2页（测试结果页），并把数据自动填入右侧模板")
        s = Theme._scheme
        self.ocr_button.setStyleSheet(
            f"QPushButton {{ background: {s['primary']}; color: white; font-weight: 600;"
            f" border: none; border-radius: 4px; padding: 4px 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {s['primary_light']}; }}"
            f"QPushButton:pressed {{ background: #1A252F; }}"
            f"QPushButton:disabled {{ background: {s['border']}; color: {s['text_sec']}; }}")
        self.ocr_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.ocr_button.setEnabled(False)
        self.ocr_button.clicked.connect(self._ocr_current_page)

        # 交叉比对按钮
        self.cross_verify_button = QPushButton("多模型交叉比对")
        self.cross_verify_button.setFixedHeight(24)
        self.cross_verify_button.setMinimumWidth(108)
        self.cross_verify_button.setToolTip("用所有可用引擎分别识别，交叉比对选最佳结果")
        self.cross_verify_button.setStyleSheet(
            f"QPushButton {{ background: {s['card']}; color: {s['primary']}; font-weight: 600;"
            f" border: 1px solid {s['primary']}; border-radius: 4px; padding: 4px 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {s['hover']}; }}"
            f"QPushButton:pressed {{ background: {s['border']}; }}"
            f"QPushButton:disabled {{ color: {s['text_sec']}; border-color: {s['border']}; }}")
        self.cross_verify_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.cross_verify_button.setEnabled(False)
        self.cross_verify_button.clicked.connect(self._cross_verify_ocr)

        # 布局：缩放 | 分隔 | 识别框 | 识别并填入 | 交叉比对 | stretch
        ctrl.addWidget(self.zoom_out_button)
        ctrl.addWidget(self.zoom_label)
        ctrl.addWidget(self.zoom_in_button)
        ctrl.addWidget(self.zoom_reset_button)
        ctrl.addWidget(self.boxes_button)
        ctrl.addWidget(self.ocr_button)
        ctrl.addWidget(self.cross_verify_button)
        ctrl.addStretch()

        lay.addWidget(self.pdf_viewer, 1)
        lay.addLayout(ctrl)
        container.setMinimumWidth(280)
        return container

    def _create_tabs(self) -> QWidget:
        """创建右侧面板 — 使用 ReportFormPanel"""
        from report_form_panel import ReportFormPanel
        self._form_panel = ReportFormPanel(self._checker, Theme)
        # 默认选中第一个测试类型
        first_test = None
        for cat_name, test_list in TEST_CATEGORIES.items():
            if test_list:
                first_test = test_list[0]
                break
        if first_test:
            self._form_panel.switch_test_type(first_test)
        # 底部引擎标签栏
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self._form_panel, 1)

        engine_bar = QHBoxLayout()
        engine_bar.setContentsMargins(8, 2, 0, 2)
        engine_bar.setSpacing(2)
        engine_label = QLabel("当前模型：")
        engine_label.setStyleSheet(f"font-size: 12px; color: {Theme.TEXT_SEC()}; font-weight: 600;")
        engine_bar.addWidget(engine_label)
        self._engine_label_container = QWidget()
        self._engine_label_container.setStyleSheet(
            f"background: {Theme.CARD()}; border: 1px solid {Theme.BORDER()}; border-radius: {R};")
        self._engine_label_layout = QHBoxLayout(self._engine_label_container)
        self._engine_label_layout.setContentsMargins(8, 2, 8, 2)
        self._engine_label_layout.setSpacing(4)
        self._engine_label_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        engine_bar.addWidget(self._engine_label_container, 1)

        # 模型选择下拉框
        model_label = QLabel("模型：")
        model_label.setStyleSheet(f"font-size: 12px; color: {Theme.TEXT_SEC()}; font-weight: 600;")
        engine_bar.addWidget(model_label)
        self._engine_combo = QComboBox()
        self._engine_combo.setFixedHeight(26)
        self._engine_combo.setMinimumWidth(120)
        self._engine_combo.setStyleSheet(
            f"background: {Theme.CARD()}; color: {Theme.TEXT()};"
            f" border: 1px solid {Theme.BORDER()}; border-radius: 4px; padding: 2px 8px; font-size: 12px;")
        self._engine_combo.addItem("自动")
        engine_bar.addWidget(self._engine_combo)
        self._engine_combo.currentTextChanged.connect(self._on_engine_combo_changed)

        lay.addLayout(engine_bar)

        self._engine_labels: Dict[str, QLabel] = {}
        self._refresh_engine_labels()
        container.setMinimumWidth(360)
        return container

    def _create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setStyleSheet(
            f"QStatusBar {{ background: {Theme.CARD()}; color: {Theme.TEXT_SEC()};"
            f" border-top: 1px solid {Theme.BORDER()}; font-size: 12px; }}")
        self.status_bar.showMessage("就绪 — 请先打开报告文件")

    # ── 引擎标签 ──

    def _refresh_engine_labels(self):
        for i in reversed(range(self._engine_label_layout.count())):
            w = self._engine_label_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        self._engine_labels.clear()
        # 始终获取引擎列表，不依赖是否打开文件，以便用户第一时间看到引擎可用状态
        engines = self._checker.get_ocr_engine_list()
        if not engines:
            # 没有任何引擎信息时，显示占位提示
            placeholder = QLabel("（未检测到可用 OCR 引擎）")
            placeholder.setStyleSheet(f"font-size: 11px; color: {Theme.TEXT_SEC()}; padding: 3px 8px;")
            self._engine_label_layout.addWidget(placeholder)
            self._engine_label_layout.addStretch()
            return
        for eng in engines:
            disp_name = eng["name"].replace("OCR", "").replace("  ", " ").strip() or eng["name"]
            available = eng.get("available", False)
            detail = eng.get("detail", "")
            lbl = QLabel(disp_name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if detail:
                lbl.setToolTip(detail)
            if available:
                lbl.setStyleSheet(
                    f"font-size: 11px; padding: 3px 10px; border: 1px solid {Theme.BORDER()};"
                    f"border-radius: 12px; background: {Theme.CARD()}; color: {Theme.TEXT()}; font-weight: 600;")
            else:
                lbl.setStyleSheet(
                    f"font-size: 11px; padding: 3px 10px; border: 1px solid #F0F0F0;"
                    f"border-radius: 12px; background: #FAFAFA; color: #BBB; font-weight: 600;")
            self._engine_label_layout.addWidget(lbl)
            self._engine_labels[eng["name"]] = lbl
        self._engine_label_layout.addStretch()

        # 同步更新模型选择下拉框
        self._update_engine_combo(engines)

    def _update_engine_combo(self, engines):
        """根据引擎列表更新下拉框选项（保留当前选择）"""
        if not hasattr(self, '_engine_combo'):
            return
        current_text = self._engine_combo.currentText()
        current_name = self._engine_combo.currentData()
        self._engine_combo.blockSignals(True)
        self._engine_combo.clear()
        self._engine_combo.addItem("自动")
        for eng in engines:
            name = eng.get("name", "")
            available = eng.get("available", False)
            label = name if available else f"{name} (不可用)"
            self._engine_combo.addItem(label, name)
        # 恢复之前的选择：优先按引擎名匹配，避免"(不可用)"后缀变化导致选中丢失
        idx = self._engine_combo.findData(current_name) if current_name else 0
        if idx < 0:
            idx = self._engine_combo.findText(current_text)
        if idx < 0:
            idx = 0
        self._engine_combo.setCurrentIndex(idx)
        self._engine_combo.blockSignals(False)

    def _on_engine_combo_changed(self, text: str):
        """用户切换模型：自动/手动指定引擎"""
        if not hasattr(self, '_checker') or not self._checker:
            return
        if text == "自动" or not text:
            self._checker.set_ocr_engine("")
            self.status_bar.showMessage("已切换为自动模式（级联识别）", 0)
        else:
            # 从 userData 取引擎名（去掉" (不可用)"后缀）
            engine_name = self._engine_combo.currentData() or text
            ok = self._checker.set_ocr_engine(engine_name)
            if not ok and engine_name == AI_ENGINE_NAME:
                # AI 未配置：直接打开设置，保存后自动重试
                self._show_ai_settings()
                ok = self._checker.set_ocr_engine(engine_name)
            if ok:
                self.status_bar.showMessage(f"已切换为 {engine_name} 引擎", 0)
            else:
                QMessageBox.warning(self, "引擎不可用", f"{engine_name} 引擎不可用，请检查安装或配置")
                self._engine_combo.blockSignals(True)
                self._engine_combo.setCurrentIndex(0)
                self._engine_combo.blockSignals(False)

    def _highlight_engine_label(self, name: str, state: str):
        lbl = self._engine_labels.get(name)
        if lbl is None:
            return
        styles = {
            "trying": (
                f"font-size: 11px; padding: 3px 10px; border: 1px solid #E0A800;"
                f"border-radius: 12px; background: #FFF8E1; color: #8A6D00; font-weight: 600;"),
            "ok": (
                f"font-size: 11px; padding: 3px 10px; border: 1px solid #28A745;"
                f"border-radius: 12px; background: #E8F5E9; color: #155724; font-weight: 600;"),
            "fail": (
                f"font-size: 11px; padding: 3px 10px; border: 1px solid #DC3545;"
                f"border-radius: 12px; background: #FFEBEE; color: #721C24; font-weight: 600;"),
        }
        s = styles.get(state)
        if s:
            lbl.setStyleSheet(s)

    # ── 设置 ──

    def _update_ocr_status(self):
        if hasattr(self, "_refresh_engine_labels"):
            try:
                self._refresh_engine_labels()
            except Exception:
                pass

    def _apply_theme(self):
        """应用当前配色方案到整个界面"""
        Theme.set_scheme(self._current_scheme)
        # 重新设置全局样式
        self.setStyleSheet(Theme.global_stylesheet())
        # 刷新 PDF 视图背景（set_bg_color 会同时更新 image_label 和 scroll_area）
        self.pdf_viewer.set_bg_color(Theme.BG())
        # 刷新文件名条
        self._file_name_bar.setStyleSheet(
            f"font-size: 12px; color: {Theme.TEXT_SEC()}; padding: 8px 14px;"
            f"background: {Theme.CARD()}; border-radius: {R}; border: 1px solid {Theme.BORDER()};"
            f"QLabel:hover {{ background: {Theme.HOVER()}; }}")
        # 刷新缩放标签
        self.zoom_label.setStyleSheet(f"color: {Theme.TEXT_SEC()}; font-size: 11px; font-weight: 600;")
        # 刷新所有按钮样式
        btn_style = Theme.BTN_TOOL()
        # ocr_button 使用自定义醒目样式，不用默认工具按钮样式
        s = Theme._scheme
        self.ocr_button.setStyleSheet(
            f"QPushButton {{ background: {s['primary']}; color: white; font-weight: 600;"
            f" border: none; border-radius: 4px; padding: 4px 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {s['primary_light']}; }}"
            f"QPushButton:pressed {{ background: #1A252F; }}"
            f"QPushButton:disabled {{ background: {s['border']}; color: {s['text_sec']}; }}")
        self.zoom_out_button.setStyleSheet(btn_style)
        self.zoom_in_button.setStyleSheet(btn_style)
        self.zoom_reset_button.setStyleSheet(btn_style)
        self.boxes_button.setStyleSheet(btn_style)
        # 刷新右侧面板
        if hasattr(self, '_form_panel'):
            self._form_panel.refresh_theme()
        # 刷新状态栏
        self.status_bar.setStyleSheet(
            f"QStatusBar {{ background: {Theme.CARD()}; color: {Theme.TEXT_SEC()};"
            f" border-top: 1px solid {Theme.BORDER()}; font-size: 12px; }}")
        # 刷新引擎容器
        self._engine_label_container.setStyleSheet(
            f"background: {Theme.CARD()}; border: 1px solid {Theme.BORDER()}; border-radius: {R};")
        self._refresh_engine_labels()
        self._bg_color = Theme.BG()

    def _show_settings(self):
        dialog = SettingsDialog(self, self._current_scheme, self._opacity)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_scheme = dialog.get_scheme_name()
            self._opacity = dialog.get_opacity()
            self.setWindowOpacity(self._opacity / 100.0)
            if new_scheme != self._current_scheme:
                self._current_scheme = new_scheme
                self._apply_theme()
            self.status_bar.showMessage(f"设置已更新 - 配色: {new_scheme}, 透明度: {self._opacity}%")

    def _show_ai_settings(self):
        """打开 AI 视觉模型设置，保存后刷新引擎列表"""
        dialog = AISettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._refresh_engine_labels()
            cfg = load_ai_config()
            self.status_bar.showMessage(
                f"AI 模型已保存：{cfg['model']} @ {cfg['base_url']}", 0)

    # ── 文件操作 ──

    def _open_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择报告文件", "",
            "报告文件 (*.pdf *.docx *.doc *.jpg *.jpeg *.png *.bmp *.tif *.tiff);;"
            "PDF 文件 (*.pdf);;Word 文件 (*.docx *.doc);;"
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if not file_path:
            return
        self._close_current_file()
        self._open_file(file_path)

    def _open_file(self, file_path: str):
        try:
            abs_path = os.path.abspath(file_path)
            if not self._checker.open_document(abs_path):
                QMessageBox.warning(self, "打开失败", f"无法打开文件:\n{file_path}")
                return
            self.pdf_viewer.reset_progress()  # 新文件重置进度
            self._current_pdf_path = abs_path
            self._current_page = 0
            page_count = self._checker.get_page_count()
            self._update_page_info()
            self._render_current_page()
            self.ocr_button.setEnabled(True)
            self.cross_verify_button.setEnabled(True)
            doc_type = self._checker.get_document_type()
            type_label = {
                'pdf': "PDF",
                'adobe_image_pdf': "PDF(Adobe渲染)",
                'adobe_live': "PDF(窗口捕获)",
                'word': "Word",
                'image': "图片",
            }.get(doc_type, "文档")
            text_label = "文字型" if self._checker.is_text_based_pdf() else "图片型"
            self._file_name_bar.setText(
                f"\U0001f4c4 {os.path.basename(abs_path)}\u3000|\u3000{type_label}\u3000|\u3000{text_label}")
            self.status_bar.showMessage(f"已打开: {os.path.basename(abs_path)} | {type_label} | {text_label}")
            self._refresh_engine_labels()
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "打开异常", f"打开文件时发生错误:\n{str(e)}")

    def _capture_from_adobe_window(self):
        """从已打开的 Adobe Acrobat 窗口捕获 PDF 页面（不打开文件）。"""
        try:
            from adobe_window_capture import AdobeWindowCapture

            # 先检查是否有 Acrobat 窗口（不 connect，只是快速检查）
            cap = AdobeWindowCapture()
            if not cap.is_available():
                QMessageBox.warning(
                    self, "未找到 Adobe 窗口",
                    "请先在 Adobe Acrobat / Adobe Reader 中手动打开目标 PDF 文件，\n"
                    "然后再使用此功能。"
                )
                return

            # 关闭当前文档
            self._close_current_file()

            # 尝试通过 DocumentLoader 的窗口捕获模式打开
            if hasattr(self._checker, '_document_loader'):
                loader = self._checker._document_loader
                if loader.open_pdf_from_adobe_window():
                    # 获取已连接的 capture 对象（在 loader 内部创建的）
                    live_cap = loader._adobe_live_capture
                    self._current_pdf_path = "[Adobe窗口捕获]"
                    self._current_page = 0
                    page_count = self._checker.get_page_count()
                    self._update_page_info()
                    self._render_current_page()
                    self.ocr_button.setEnabled(True)
                    self.cross_verify_button.setEnabled(True)
                    doc_type = self._checker.get_document_type()
                    type_label = {
                        'adobe_live': "PDF(窗口捕获)",
                    }.get(doc_type, "窗口捕获")
                    title_text = live_cap.window_title if live_cap else "Adobe窗口"
                    self._file_name_bar.setText(
                        f"\U0001f4c4 {title_text}\u3000|\u3000{type_label}")
                    self.status_bar.showMessage(
                        f"已捕获: {title_text} | {type_label}")
                    self._refresh_engine_labels()
                    return

            QMessageBox.warning(
                self, "捕获失败",
                "无法从 Adobe Acrobat 窗口捕获页面。\n"
                "请确认：\n"
                "1. Adobe Acrobat 已打开并显示目标 PDF\n"
                "2. PDF 不是空白页面"
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "捕获异常", f"捕获时发生错误:\n{str(e)}")

    def _close_current_file(self):
        try:
            self._checker.close_document()
        except Exception:
            pass
        self._current_pdf_path = ""
        self._current_page = 0
        self.pdf_viewer.set_image(None)
        self._update_page_info()
        self.ocr_button.setEnabled(False)
        self._file_name_bar.setText("未打开文件")
        self.status_bar.showMessage("未打开任何文件")

    def _import_template(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "导入模板", "", "JSON 文件 (*.json)")
        if not file_path:
            return
        try:
            import shutil
            template_name = os.path.basename(file_path)
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            dest_path = os.path.join(root_dir, 'templates', template_name)
            shutil.copy(file_path, dest_path)
            QMessageBox.information(self, "导入成功", f"模板 {template_name} 已导入")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"导入模板时发生错误: {str(e)}")

    def _new_template(self):
        QMessageBox.information(
            self, "新建模板",
            "请手动创建 JSON 模板文件并放置在 templates/ 目录下。\n\n"
            "模板格式参考：\n"
            "{\n"
            '  "meta": {\n'
            '    "name": "测试模板",\n'
            '    "version": "1.0"\n'
            "  },\n"
            '  "fields": [...],\n'
            '  "rules": [...],\n'
            '  "limits": {...}\n'
            "}")

    def _generate_word_drafts(self):
        import subprocess
        script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scripts", "pdf_to_word.py")
        if not os.path.exists(script):
            QMessageBox.warning(self, "脚本缺失", f"未找到生成脚本:\n{script}")
            return
        try:
            proc = subprocess.Popen(
                [sys.executable, script],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            out, _ = proc.communicate(timeout=600)
            dst = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "models", "reports", "word_drafts")
            if proc.returncode == 0:
                QMessageBox.information(
                    self, "生成完成",
                    f"标准报告 Word 底稿已生成。\n\n输出目录:\n{dst}\n\n"
                    "打开待检报告后，可在右侧『对照底稿』中选择对应标准 Word 进行并排核对。")
            else:
                QMessageBox.warning(self, "生成失败", f"{out[-2000:]}")
        except Exception as e:
            QMessageBox.warning(self, "生成异常", str(e))

    def _show_about(self):
        about_text = (
            "ReportChecker — 电动工具测试报告校验工具\n\n"
            "版本: 2.0.0\n"
            "技术栈: PyQt6 + PyMuPDF + Multi-OCR\n\n"
            "功能特点:\n"
            "- 纯本地运行，不联网\n"
            "- 模板驱动识别，支持多标准\n"
            "- 自动校验温升计算、限值判定\n"
            "- 支持多种测试类型切换\n"
            "- 多 OCR 引擎自动切换\n\n"
            "设计: 王坤\n"
            "借助 AI 开发\n\n"
            "使用说明:\n"
            "1. 点击『文件』→『打开报告文件』选择报告\n"
            "2. 在右侧选择测试类型 Tab\n"
            "3. 点击『开始校验』执行校验\n"
            "4. 查看下方异常列表，点击可定位到对应位置\n"
            "5. 点击『设置』→『外观设置』调整界面")
        QMessageBox.about(self, "关于", about_text)

    # ── 渲染 / 缩放 / 翻页 ──

    def _render_current_page(self):
        render_result = self._checker.render_page(self._current_page)
        if render_result:
            img_array, _ = render_result
            self.pdf_viewer.set_image(img_array)
            self._update_zoom_label()

    def _update_zoom_label(self):
        scale = self.pdf_viewer.get_scale_factor()
        self.zoom_label.setText(f"{int(scale * 100)}%")

    def _zoom_in(self):
        self.pdf_viewer.zoom_in()
        self._update_zoom_label()

    def _zoom_out(self):
        self.pdf_viewer.zoom_out()
        self._update_zoom_label()

    def _zoom_reset(self):
        self.pdf_viewer.zoom_reset()
        self._update_zoom_label()

    def _toggle_boxes(self):
        self._show_boxes = not self._show_boxes
        self.boxes_button.setChecked(self._show_boxes)
        self.boxes_button.setText("\u2611 识别框" if self._show_boxes else "\u2610 识别框")
        if self._current_pdf_path:
            self._ocr_current_page()

    def _on_engine_try(self, name: str, available: bool):
        self._highlight_engine_label(name, "trying")

    def _on_engine_result(self, name: str, success: bool):
        self._highlight_engine_label(name, "ok" if success else "fail")

    # ── 多模型交叉比对 ──

    def _cross_verify_ocr(self):
        """多引擎交叉比对识别"""
        if not self._checker or not self._checker.is_ocr_available():
            QMessageBox.warning(self, "OCR不可用", "没有可用的OCR引擎")
            return

        page_count = self._checker.get_page_count()
        target_page = min(self._OCR_PAGE_INDEX, page_count - 1)
        if target_page < 0:
            QMessageBox.warning(self, "页码错误", "文档页数不足")
            return

        self.cross_verify_button.setEnabled(False)
        self.cross_verify_button.setText("比对中...")
        self.status_bar.showMessage("正在用多引擎交叉比对识别...")
        QApplication.processEvents()

        # 在后台线程执行
        from PyQt6.QtCore import QThread, pyqtSignal

        class CrossVerifyWorker(QThread):
            finished_cv = pyqtSignal(dict)

            def __init__(self, checker, page):
                super().__init__()
                self._checker = checker
                self._page = page

            def run(self):
                try:
                    result = self._checker.cross_verify_ocr(self._page)
                    self.finished_cv.emit(result)
                except Exception as e:
                    self.finished_cv.emit({
                        'results': {}, 'best_text': '',
                        'agreement': 0.0, 'used_engines': [],
                        'error': str(e)
                    })

        self._cv_worker = CrossVerifyWorker(self._checker, target_page)
        self._cv_worker.finished_cv.connect(self._on_cross_verify_finished)
        self._cv_worker.start()

    def _on_cross_verify_finished(self, result):
        """交叉比对完成"""
        self.cross_verify_button.setEnabled(True)
        self.cross_verify_button.setText("多模型交叉比对")

        if 'error' in result:
            self.status_bar.showMessage(f"交叉比对失败: {result['error']}", 0)
            return

        best_text = result.get('best_text', '')
        agreement = result.get('agreement', 0.0)
        engines = result.get('used_engines', [])

        if best_text:
            self._form_panel.set_ocr_text(best_text)
            pct = int(agreement * 100)
            self.status_bar.showMessage(
                f"交叉比对完成：{', '.join(engines)} | 一致性 {pct}%", 0)
        else:
            self.status_bar.showMessage("交叉比对未识别到文字", 0)

    # ── OCR ──

    # 固定识别第2页（索引1），即测试结果页
    _OCR_PAGE_INDEX = 1

    def _ocr_current_page(self):
        if not self._checker.is_ocr_available():
            QMessageBox.warning(self, "OCR不可用", "没有可用的OCR引擎")
            return
        # 不管当前翻到第几页，始终识别第2页（测试结果页）
        page_count = self._checker.get_page_count()
        target_page = min(self._OCR_PAGE_INDEX, page_count - 1)
        if target_page < 0:
            QMessageBox.warning(self, "页码错误", "文档页数不足")
            return
        # 先跳转到第2页，避免 viewer 状态不一致导致滚动
        if self._current_page != target_page:
            self._current_page = target_page
            self.pdf_viewer.set_page(self._checker, target_page)
            self._update_zoom_label()
        self.pdf_viewer.reset_progress()
        self.ocr_button.setEnabled(False)
        self.cross_verify_button.setEnabled(False)
        self.ocr_button.setText("识别中...")

        # 判断自动模式 vs 手动模式
        forced = getattr(self._checker.ocr_engine, '_forced_engine_name', None)
        if forced:
            # 手动模式：只用手动指定的引擎
            self.status_bar.showMessage(f"正在用 {forced} 识别第{target_page + 1}页...")
            self._ocr_worker = OCRPageWorker(
                self._checker, target_page, self._show_boxes)
            self._ocr_worker.engine_try.connect(self._on_engine_try)
            self._ocr_worker.engine_result.connect(self._on_engine_result)
            self._ocr_worker.progress.connect(self.pdf_viewer.set_progress)
            self._ocr_worker.finished.connect(self._on_ocr_page_finished)
            self._ocr_worker.start()
        else:
            # 自动模式：用每个引擎单独识别，选填入率最高的
            self.status_bar.showMessage(
                f"自动模式：正在用所有引擎逐个识别第{target_page + 1}页，选最佳结果...")
            self._ocr_worker = OCRMultiEngineWorker(
                self._checker, target_page, self._show_boxes)
            self._ocr_worker.engine_try.connect(self._on_engine_try)
            self._ocr_worker.engine_result.connect(self._on_engine_result)
            self._ocr_worker.progress.connect(self.pdf_viewer.set_progress)
            self._ocr_worker.finished.connect(self._on_multi_engine_finished)
            self._ocr_worker.start()

    def _on_multi_engine_finished(self, img_array, all_results):
        """自动模式：用每个引擎识别，选填入率最高且列一致性通过的结果"""
        self.pdf_viewer.set_progress(1.0)
        self.ocr_button.setEnabled(True)
        self.cross_verify_button.setEnabled(True)
        self.ocr_button.setText("识别并填入")

        if img_array is not None:
            self.pdf_viewer.set_image(img_array)
            self._update_zoom_label()

        if not all_results:
            self.status_bar.showMessage("OCR识别失败：所有引擎均无结果", 0)
            return

        # 文本型PDF：优先用内置提取
        text_pdf_text = None
        if self._checker.is_text_based_pdf():
            text_pdf_text = self._get_ocr_page_text()

        best_rate = -1
        best_engine = ""
        best_text = ""
        best_consistent = False

        # 如果文本型PDF有结果，先试它
        if text_pdf_text and text_pdf_text.strip():
            self._form_panel.set_ocr_text(text_pdf_text)
            rate = self._form_panel.get_fill_rate()
            consistent = self._form_panel.check_column_consistency()
            if rate >= 95 and consistent:
                self._refresh_engine_labels()
                self.status_bar.showMessage(
                    f"OCR完成（文本提取，填入率{rate:.0f}%）", 0)
                return
            best_rate = rate
            best_engine = "文本提取"
            best_text = text_pdf_text
            best_consistent = consistent

        # 逐个引擎结果试填，选填入率最高且列一致性通过的
        for engine_name, text in all_results:
            self._form_panel.set_ocr_text(text)
            rate = self._form_panel.get_fill_rate()
            consistent = self._form_panel.check_column_consistency()

            # 达到95%且列一致性通过 → 直接用
            if rate >= 95 and consistent:
                best_rate = rate
                best_engine = engine_name
                best_text = text
                best_consistent = True
                break

            # 记录最佳候选：优先选一致性通过的，其次选填入率高的
            if consistent and not best_consistent:
                best_rate = rate
                best_engine = engine_name
                best_text = text
                best_consistent = True
            elif consistent == best_consistent and rate > best_rate:
                best_rate = rate
                best_engine = engine_name
                best_text = text

        # 用最佳结果重新填入
        if best_text:
            self._form_panel.set_ocr_text(best_text)

        self._refresh_engine_labels()
        status = "通过" if best_consistent else "异常"
        if best_rate >= 95 and best_consistent:
            self.status_bar.showMessage(
                f"OCR完成（{best_engine}，填入率{best_rate:.0f}%，列一致性{status}）", 0)
        else:
            self.status_bar.showMessage(
                f"OCR完成（{best_engine}，填入率{best_rate:.0f}%，列一致性{status}，未达95%）", 0)

    def _on_ocr_page_finished(self, img_array, used_engine):
        self.pdf_viewer.set_progress(1.0)
        self.ocr_button.setEnabled(True)
        self.cross_verify_button.setEnabled(True)
        self.ocr_button.setText("识别并填入")
        if img_array is not None:
            self.pdf_viewer.set_image(img_array)
            self._update_zoom_label()
            self._refresh_engine_labels()
            ocr_text = self._get_ocr_page_text()

            forced = getattr(self._checker.ocr_engine, 'forced_engine_name', None)
            template = getattr(self._checker, '_current_template', None)
            if forced == AI_ENGINE_NAME and template:
                # 第二段：大模型从 OCR 文本中抽取字段，直接填入表单
                try:
                    self.status_bar.showMessage("AI 正在抽取字段…")
                    extracted = extract_fields_from_text(ocr_text, template)
                    self._form_panel._fill_fields(extracted)
                    self.status_bar.showMessage("AI 识别完成（OCR + 字段抽取）", 0)
                    return
                except Exception as e:
                    self.status_bar.showMessage(f"字段抽取失败：{e}，已回退文本匹配", 0)

            self._form_panel.set_ocr_text(ocr_text)
            if used_engine:
                self.status_bar.showMessage(f"OCR完成（{used_engine}）", 0)
            else:
                self.status_bar.showMessage("OCR识别完成", 0)
        else:
            self.status_bar.showMessage("OCR识别失败", 0)

    # ── 一键识别全部页面（已合并到"识别并填入"，仅保留兼容入口） ──

    def _ocr_all_pages(self):
        """兼容入口：直接走单页识别并自动填入模板"""
        self._ocr_current_page()

    def _get_ocr_page_text(self) -> str:
        """获取第2页（测试结果页）的OCR文本

        优先级：
        1. Adobe COM 文本提取（100%准确，不依赖OCR）
        2. PyMuPDF 文本提取（文本型PDF）
        3. 高DPI渲染 + OCR（图片型PDF / 扫描件）
        """
        page_count = self._checker.get_page_count()
        page_num = min(self._OCR_PAGE_INDEX, page_count - 1)
        try:
            # ── 优先级1: Adobe COM 文本提取 ──
            adobe_capture = getattr(self._checker, '_adobe_live_capture', None)
            if adobe_capture and adobe_capture.has_com_text_extraction:
                text = adobe_capture.extract_text_via_com(page_num)
                if text and text.strip():
                    return text.strip()

            # ── 优先级2: PyMuPDF 文本提取 ──
            if self._checker.is_text_based_pdf():
                # 优先用 blocks 模式提取，按坐标重建行结构（保留表格列对齐）
                try:
                    doc = self._checker._document_loader._doc
                    if doc and 0 <= page_num < doc.page_count:
                        text = self._extract_text_by_blocks(doc[page_num])
                        if text and text.strip():
                            return text.strip()
                except Exception:
                    pass
                # 兜底：用普通文本提取
                try:
                    doc = self._checker._document_loader._doc
                    if doc and 0 <= page_num < doc.page_count:
                        text = doc[page_num].get_text("text")
                        if text and text.strip():
                            return text.strip()
                except Exception:
                    pass
                # 兜底：用坐标提取
                blocks = self._checker._document_loader.extract_text_with_positions(page_num)
                if blocks:
                    return "\n".join(b['text'] for b in blocks if b.get('text'))
            # ── 优先级3: 高DPI渲染 + OCR ──
            render_result = self._checker.render_page(page_num, dpi=450)
            if render_result:
                img, _ = render_result
                text = self._checker.ocr_engine.recognize_region(img)
                return text or "（未识别到文字）"
        except Exception:
            pass
        return "（暂无识别内容）"

    @staticmethod
    def _extract_text_by_blocks(page) -> str:
        """用 PyMuPDF blocks 模式提取文本，按 y 坐标重建行结构

        blocks 模式返回 (x0, y0, x1, y1, text, block_no, block_type)
        按 y 坐标分组后，每行内按 x 坐标排序并用多空格分隔，
        保留表格的列对齐关系。
        """
        blocks = page.get_text("blocks")
        if not blocks:
            return ""

        # 过滤空块和图片块
        text_blocks = []
        for b in blocks:
            if len(b) >= 5 and isinstance(b[4], str) and b[4].strip():
                text_blocks.append((b[1], b[0], b[4].strip()))  # (y0, x0, text)

        if not text_blocks:
            return ""

        # 按 y 坐标排序
        text_blocks.sort(key=lambda t: (t[0], t[1]))

        # 按 y 坐标分组形成行
        lines = []
        current_row = []
        current_y = None
        y_threshold = 5  # y 坐标差小于5点视为同一行

        for y, x, text in text_blocks:
            if current_y is None or abs(y - current_y) <= y_threshold:
                current_row.append((x, text))
                current_y = y if current_y is None else min(current_y, y)
            else:
                if current_row:
                    current_row.sort(key=lambda t: t[0])
                    lines.append('  '.join(t[1] for t in current_row))
                current_row = [(x, text)]
                current_y = y

        if current_row:
            current_row.sort(key=lambda t: t[0])
            lines.append('  '.join(t[1] for t in current_row))

        return '\n'.join(lines)

    def _update_page_info(self):
        """更新页码信息（仅保留方法签名，不再显示页码控件）"""
        pass

    def closeEvent(self, event):
        self._checker.close_pdf()
        event.accept()


def run_app():
    """启动 GUI 应用"""
    app = QApplication(sys.argv)
    app.setWindowIcon(_create_tool_icon())

    # 显示闪屏
    splash = create_splash()
    splash.show()
    app.processEvents()

    app.processEvents()

    window = ReportCheckerApp()
    splash.finish(window)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
