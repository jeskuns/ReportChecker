"""
PDF 坐标测量工具
帮助用户测量 PDF 中字段的坐标位置，用于模板配置

使用方法：
    python coordinate_tool.py
    1. 打开 PDF 文件
    2. 在图像上拖动鼠标框选区域
    3. 查看状态栏显示的坐标
    4. 点击「复制坐标」按钮复制到剪贴板
"""

import sys
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QPushButton, QFileDialog, QMessageBox,
    QLineEdit, QStatusBar, QMenuBar, QMenu,
)
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QCursor, QColor, QAction
from PyQt6.QtCore import Qt, QPoint, QRect

import fitz
from PIL import Image
import numpy as np


class CoordinateTool(QMainWindow):
    """
    PDF 坐标测量工具主窗口
    """
    
    def __init__(self):
        """初始化工具"""
        super().__init__()
        self._doc = None
        self._current_page = 0
        self._page_height = 0
        self._image = None
        self._pixmap = None
        self._start_point = None
        self._end_point = None
        self._selection_rect = None
        self._scale = 1.0
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化界面"""
        self.setWindowTitle("PDF 坐标测量工具")
        self.setGeometry(100, 100, 1000, 700)
        
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()
    
    def _create_menu(self):
        """创建菜单栏"""
        menu_bar = self.menuBar()
        
        file_menu = QMenu("文件", self)
        
        open_action = QAction("打开 PDF", self)
        open_action.triggered.connect(self._open_pdf)
        file_menu.addAction(open_action)
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        menu_bar.addMenu(file_menu)
        
        help_menu = QMenu("帮助", self)
        about_action = QAction("使用说明", self)
        about_action.triggered.connect(self._show_help)
        help_menu.addAction(about_action)
        menu_bar.addMenu(help_menu)
    
    def _create_main_layout(self):
        """创建主布局"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        
        self._create_pdf_view(main_layout)
        self._create_control_panel(main_layout)
        
        central_widget.setLayout(main_layout)
    
    def _create_pdf_view(self, parent_layout):
        """创建 PDF 视图区域"""
        left_layout = QVBoxLayout()
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #f0f0f0;")
        self.image_label.setMouseTracking(True)
        self.image_label.mousePressEvent = self._on_mouse_press
        self.image_label.mouseMoveEvent = self._on_mouse_move
        self.image_label.mouseReleaseEvent = self._on_mouse_release
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(True)
        
        page_control_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("上一页")
        self.prev_button.clicked.connect(self._prev_page)
        self.prev_button.setEnabled(False)
        
        self.page_label = QLabel("第 0 / 0 页")
        
        self.next_button = QPushButton("下一页")
        self.next_button.clicked.connect(self._next_page)
        self.next_button.setEnabled(False)
        
        page_control_layout.addWidget(self.prev_button)
        page_control_layout.addWidget(self.page_label)
        page_control_layout.addWidget(self.next_button)
        
        left_layout.addWidget(self.scroll_area)
        left_layout.addLayout(page_control_layout)
        
        parent_layout.addLayout(left_layout, 2)
    
    def _create_control_panel(self, parent_layout):
        """创建控制面板"""
        right_layout = QVBoxLayout()
        
        self.field_name_input = QLineEdit()
        self.field_name_input.setPlaceholderText("字段名称（如：stator_hot）")
        
        self.field_type_input = QLineEdit()
        self.field_type_input.setPlaceholderText("字段类型（number/text）")
        self.field_type_input.setText("number")
        
        self.field_unit_input = QLineEdit()
        self.field_unit_input.setPlaceholderText("单位（如：°C/K/V）")
        
        self.field_desc_input = QLineEdit()
        self.field_desc_input.setPlaceholderText("字段描述")
        
        self.coord_display = QLabel("坐标: x0=0, y0=0, x1=0, y1=0")
        self.coord_display.setStyleSheet("font-family: monospace;")
        
        self.copy_button = QPushButton("复制坐标")
        self.copy_button.clicked.connect(self._copy_coordinates)
        self.copy_button.setEnabled(False)
        
        self.add_field_button = QPushButton("添加到模板")
        self.add_field_button.clicked.connect(self._add_to_template)
        self.add_field_button.setEnabled(False)
        
        self.clear_button = QPushButton("清空选择")
        self.clear_button.clicked.connect(self._clear_selection)
        
        right_layout.addWidget(QLabel("字段名称"))
        right_layout.addWidget(self.field_name_input)
        right_layout.addWidget(QLabel("字段类型"))
        right_layout.addWidget(self.field_type_input)
        right_layout.addWidget(QLabel("单位"))
        right_layout.addWidget(self.field_unit_input)
        right_layout.addWidget(QLabel("描述"))
        right_layout.addWidget(self.field_desc_input)
        right_layout.addWidget(self.coord_display)
        right_layout.addWidget(self.copy_button)
        right_layout.addWidget(self.add_field_button)
        right_layout.addWidget(self.clear_button)
        
        parent_layout.addLayout(right_layout, 1)
    
    def _create_status_bar(self):
        """创建状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 - 请先打开 PDF 文件")
    
    def _open_pdf(self):
        """打开 PDF 文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 PDF 文件",
            "",
            "PDF 文件 (*.pdf)"
        )
        
        if not file_path:
            return
        
        try:
            self._doc = fitz.open(file_path)
            self._current_page = 0
            self._render_page()
            
            page_count = self._doc.page_count
            self.page_label.setText(f"第 {self._current_page + 1} / {page_count} 页")
            
            self.prev_button.setEnabled(page_count > 1)
            self.next_button.setEnabled(page_count > 1)
            
            self.status_bar.showMessage(f"已打开: {os.path.basename(file_path)}")
            
        except Exception as e:
            QMessageBox.warning(self, "打开失败", f"无法打开 PDF: {str(e)}")
    
    def _render_page(self):
        """渲染当前页面"""
        if not self._doc:
            return
        
        page = self._doc[self._current_page]
        self._page_height = page.rect.height
        
        zoom = 200 / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        self._image = np.array(img)
        
        height, width, channel = self._image.shape
        bytes_per_line = channel * width
        
        q_image = QImage(
            self._image.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888
        )
        
        self._pixmap = QPixmap.fromImage(q_image)
        self._scale = self._pixmap.height() / self._page_height
        
        self.image_label.setPixmap(self._pixmap)
        self.image_label.adjustSize()
        
        self._clear_selection()
    
    def _prev_page(self):
        """上一页"""
        if self._current_page > 0:
            self._current_page -= 1
            self._render_page()
            self.page_label.setText(f"第 {self._current_page + 1} / {self._doc.page_count} 页")
    
    def _next_page(self):
        """下一页"""
        if self._current_page < self._doc.page_count - 1:
            self._current_page += 1
            self._render_page()
            self.page_label.setText(f"第 {self._current_page + 1} / {self._doc.page_count} 页")
    
    def _on_mouse_press(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap:
            self._start_point = event.pos()
            self._end_point = event.pos()
            self._selection_rect = None
    
    def _on_mouse_move(self, event):
        """鼠标移动事件"""
        if self._start_point and self._pixmap:
            self._end_point = event.pos()
            self._update_selection()
            
            cursor_pos = event.pos()
            pdf_x = cursor_pos.x() / self._scale
            pdf_y = self._page_height - (cursor_pos.y() / self._scale)
            self.status_bar.showMessage(f"鼠标位置: ({pdf_x:.1f}, {pdf_y:.1f})")
    
    def _on_mouse_release(self, event):
        """鼠标释放事件"""
        if event.button() == Qt.MouseButton.LeftButton and self._start_point and self._pixmap:
            self._end_point = event.pos()
            self._update_selection()
            
            if self._selection_rect:
                x0 = min(self._start_point.x(), self._end_point.x()) / self._scale
                y0 = self._page_height - (max(self._start_point.y(), self._end_point.y()) / self._scale)
                x1 = max(self._start_point.x(), self._end_point.x()) / self._scale
                y1 = self._page_height - (min(self._start_point.y(), self._end_point.y()) / self._scale)
                
                self.coord_display.setText(
                    f"坐标: x0={x0:.1f}, y0={y0:.1f}, x1={x1:.1f}, y1={y1:.1f}"
                )
                
                self.copy_button.setEnabled(True)
                self.add_field_button.setEnabled(True)
    
    def _update_selection(self):
        """更新选区显示"""
        if not self._pixmap:
            return
        
        temp_pixmap = self._pixmap.copy()
        painter = QPainter(temp_pixmap)
        
        pen = QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        
        rect = QRect(self._start_point, self._end_point)
        painter.drawRect(rect)
        
        self.image_label.setPixmap(temp_pixmap)
        painter.end()
    
    def _clear_selection(self):
        """清空选区"""
        self._start_point = None
        self._end_point = None
        self._selection_rect = None
        
        if self._pixmap:
            self.image_label.setPixmap(self._pixmap)
        
        self.coord_display.setText("坐标: x0=0, y0=0, x1=0, y1=0")
        self.copy_button.setEnabled(False)
        self.add_field_button.setEnabled(False)
    
    def _copy_coordinates(self):
        """复制坐标到剪贴板"""
        if not self._start_point or not self._end_point:
            return
        
        x0 = min(self._start_point.x(), self._end_point.x()) / self._scale
        y0 = self._page_height - (max(self._start_point.y(), self._end_point.y()) / self._scale)
        x1 = max(self._start_point.x(), self._end_point.x()) / self._scale
        y1 = self._page_height - (min(self._start_point.y(), self._end_point.y()) / self._scale)
        
        coord_text = f"[{x0:.1f}, {y0:.1f}, {x1:.1f}, {y1:.1f}]"
        
        clipboard = QApplication.clipboard()
        clipboard.setText(coord_text)
        
        self.status_bar.showMessage("坐标已复制到剪贴板")
    
    def _add_to_template(self):
        """生成模板字段配置并复制到剪贴板"""
        if not self._start_point or not self._end_point:
            return
        
        x0 = min(self._start_point.x(), self._end_point.x()) / self._scale
        y0 = self._page_height - (max(self._start_point.y(), self._end_point.y()) / self._scale)
        x1 = max(self._start_point.x(), self._end_point.x()) / self._scale
        y1 = self._page_height - (min(self._start_point.y(), self._end_point.y()) / self._scale)
        
        field_name = self.field_name_input.text() or "new_field"
        field_type = self.field_type_input.text() or "number"
        field_unit = self.field_unit_input.text() or ""
        field_desc = self.field_desc_input.text() or ""
        
        field_config = {
            "field_name": field_name,
            "page_num": self._current_page,
            "rect": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
            "type": field_type,
            "unit": field_unit,
            "description": field_desc
        }
        
        import json
        config_text = json.dumps(field_config, ensure_ascii=False, indent=2)
        
        clipboard = QApplication.clipboard()
        clipboard.setText(config_text)
        
        self.status_bar.showMessage(f"字段配置已复制: {field_name}")
    
    def _show_help(self):
        """显示使用说明"""
        help_text = (
            "PDF 坐标测量工具\n\n"
            "使用方法:\n"
            "1. 点击「文件」→「打开 PDF」选择要测量的报告\n"
            "2. 在左侧图像上用鼠标拖动框选字段区域\n"
            "3. 右侧会显示该区域的 PDF 坐标（x0, y0, x1, y1）\n"
            "4. 填写字段名称、类型、单位等信息\n"
            "5. 点击「复制坐标」复制纯坐标\n"
            "6. 点击「添加到模板」复制完整的字段配置\n\n"
            "坐标说明:\n"
            "- PDF 坐标原点在左下角\n"
            "- x0: 左边界, y0: 下边界\n"
            "- x1: 右边界, y1: 上边界\n"
            "- 单位为点（1点 = 1/72 英寸）"
        )
        QMessageBox.about(self, "使用说明", help_text)
    
    def closeEvent(self, event):
        """关闭事件"""
        if self._doc:
            self._doc.close()
        event.accept()


def main():
    """运行工具"""
    app = QApplication(sys.argv)
    window = CoordinateTool()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
