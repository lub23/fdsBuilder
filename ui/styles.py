
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

QPushButton#dangerBtn {
    background-color: #f38ba8;
}

QPushButton#dangerBtn:hover {
    background-color: #eba0ac;
}

QPushButton#successBtn {
    background-color: #a6e3a1;
}

QPushButton#successBtn:hover {
    background-color: #94e2d5;
}

QPushButton#secondaryBtn {
    background-color: #45475a;
    color: #cdd6f4;
}

QPushButton#secondaryBtn:hover {
    background-color: #585b70;
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