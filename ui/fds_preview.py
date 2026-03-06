#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : fds_preview.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : FDS code preview panel for building model visualization
'''
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout, QApplication
from PySide6.QtGui import QFont

# ============================================================
# FDS代码预览面板
# ============================================================
class FDSPreviewPanel(QWidget):
    """FDS代码预览面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 标题
        title = QLabel("📄 FDS代码预览")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(title)
        
        # 代码编辑器
        self.code_edit = QTextEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setFont(QFont("Consolas", 11))
        layout.addWidget(self.code_edit)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        copy_btn = QPushButton("📋 复制代码")
        copy_btn.clicked.connect(self.copy_code)
        btn_layout.addWidget(copy_btn)
        
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
    
    def update_code(self, code: str):
        self.code_edit.setPlainText(code)
    
    def copy_code(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.code_edit.toPlainText())

