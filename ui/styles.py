
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : styles.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : Defining configurations in applications
'''

# ============================================================
# 样式表定义 - 现代深色主题
# ============================================================
DARK_STYLE = """
QMainWindow {
    background-color: #1e1e2e;
}

QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    font-size: 13px;
}

QGroupBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 8px;
    margin-top: 12px;
    padding: 15px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 15px;
    padding: 0 8px;
    color: #89b4fa;
}

QLabel {
    color: #cdd6f4;
    background: transparent;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #45475a;
    border: 1px solid #585b70;
    border-radius: 6px;
    padding: 8px 12px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 2px solid #89b4fa;
}

QComboBox::drop-down {
    border: none;
    width: 30px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 8px solid #cdd6f4;
    margin-right: 10px;
}

QPushButton {
    background-color: #89b4fa;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    color: #1e1e2e;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #b4befe;
}

QPushButton:pressed {
    background-color: #74c7ec;
}

QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}


/* Shared button variants. Prefer setting objectName instead of per-widget style strings. */
QPushButton#primaryBtn {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
}

QPushButton#primaryBtn:hover {
    background-color: #74c7ec;
}

QPushButton#primaryBtn:disabled {
    background-color: #3a3d4e;
    color: #6c7086;
}

QPushButton#successBtn {
    background-color: #a6e3a1;
    color: #1e1e2e;
    font-weight: bold;
}

QPushButton#successBtn:hover {
    background-color: #94e2d5;
}

QPushButton#successBtn:disabled {
    background-color: #3a3d4e;
    color: #6c7086;
}

QPushButton#dangerBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    font-weight: bold;
}

QPushButton#dangerBtn:hover {
    background-color: #e06080;
}

QPushButton#dangerBtn:disabled {
    background-color: #3a3d4e;
    color: #6c7086;
}

QPushButton#warningBtn {
    background-color: #f9e2af;
    color: #1e1e2e;
    font-weight: bold;
}

QPushButton#warningBtn:hover {
    background-color: #fab387;
}

QPushButton#warningBtn:disabled {
    background-color: #3a3d4e;
    color: #6c7086;
}

QPushButton[compact="true"] {
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 12px;
}

QPushButton#secondaryBtn {
    background-color: #45475a;
    color: #cdd6f4;
}

QPushButton#secondaryBtn:hover {
    background-color: #585b70;
}

QPushButton#secondaryBtn:disabled {
    background-color: #313244;
    color: #6c7086;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 8px;
    background-color: #313244;
}

QTabBar::tab {
    background-color: #45475a;
    color: #cdd6f4;
    padding: 10px 20px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}

QTabBar::tab:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QTabBar::tab:hover:!selected {
    background-color: #585b70;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    background-color: #313244;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #585b70;
    border-radius: 6px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #6c7086;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QListWidget {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 5px;
}

QListWidget::item {
    padding: 8px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QListWidget::item:hover:!selected {
    background-color: #45475a;
}

QTableWidget {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    gridline-color: #45475a;
}

QTableWidget::item {
    padding: 8px;
}

QTableWidget::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QHeaderView::section {
    background-color: #45475a;
    color: #cdd6f4;
    padding: 10px;
    border: none;
    font-weight: bold;
}

QHeaderView::section:vertical {
    background-color: #45475a;
    color: #cdd6f4;
    padding: 0px 2px;
    border: none;
    font-weight: bold;
    min-width: 28px;
}

QTextEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 10px;
    color: #cdd6f4;
    font-family: 'Consolas', 'Courier New', monospace;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 4px;
    border: 2px solid #585b70;
    background-color: #45475a;
}

QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
}

QSlider::groove:horizontal {
    height: 6px;
    background-color: #45475a;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    width: 18px;
    height: 18px;
    margin: -6px 0;
    background-color: #89b4fa;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background-color: #b4befe;
}

QProgressBar {
    background-color: #45475a;
    border-radius: 6px;
    height: 20px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 6px;
}

QStatusBar {
    background-color: #313244;
    color: #a6adc8;
}

QMenuBar {
    background-color: #313244;
    color: #cdd6f4;
    padding: 5px;
}

QMenuBar::item {
    padding: 8px 15px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #45475a;
}

QMenu {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 5px;
}

QMenu::item {
    padding: 8px 30px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QToolBar {
    background-color: #313244;
    border: none;
    padding: 5px;
    spacing: 5px;
}

QToolButton {
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 8px;
    color: #cdd6f4;
}

QToolButton:hover {
    background-color: #45475a;
}

QToolButton:pressed {
    background-color: #585b70;
}

QSplitter::handle {
    background-color: #45475a;
}

QSplitter::handle:horizontal {
    width: 2px;
}

QSplitter::handle:vertical {
    height: 2px;
}

QFrame#card {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 10px;
    padding: 15px;
}

QFrame#separator {
    background-color: #45475a;
    max-height: 1px;
}
"""
# ============================================================
# 可折叠分组框
# ============================================================
from PySide6.QtWidgets import QGroupBox, QWidget, QVBoxLayout


class CollapsibleGroup(QGroupBox):
    """可折叠分组框"""
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)
        super_layout = QVBoxLayout(self)
        super_layout.setContentsMargins(6, 4, 6, 6)
        super_layout.setSpacing(2)
        super_layout.addWidget(self._content)
        self.toggled.connect(self._content.setVisible)

    @property
    def content_layout(self):
        return self._content_layout


def apply_button_variant(button, variant: str = "primary", small: bool = False):
    """Assign a shared style objectName to a QPushButton.

    Variants: primary, success, danger, warning, secondary.
    Set `small=True` for compact toolbar/table buttons.
    """

    object_names = {
        "primary": "primaryBtn",
        "success": "successBtn",
        "danger": "dangerBtn",
        "warning": "warningBtn",
        "secondary": "secondaryBtn",
    }
    button.setObjectName(object_names.get(variant, "primaryBtn"))
    if small:
        # Qt only supports one objectName, so keep compact sizing in properties.
        button.setProperty("compact", True)
        button.setFixedHeight(26)
    button.style().unpolish(button)
    button.style().polish(button)
    return button
