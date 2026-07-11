#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : fds_preview.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : FDS code preview panel for building model visualization
'''
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QFont, QTextCursor

from ui.styles import apply_button_variant
from services.fds_naming import default_fds_filename


# ============================================================
# FDS代码预览面板
# ============================================================
class FDSPreviewPanel(QWidget):
    """FDS代码预览面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # 标题 + 操作区
        header = QHBoxLayout()
        title = QLabel("📄 FDS代码预览")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa;")
        header.addWidget(title)
        header.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索代码…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(180)
        self.search_edit.returnPressed.connect(self.find_next)
        header.addWidget(self.search_edit)

        find_btn = QPushButton("查找")
        apply_button_variant(find_btn, "primary", small=True)
        find_btn.clicked.connect(self.find_next)
        header.addWidget(find_btn)

        copy_btn = QPushButton("复制")
        apply_button_variant(copy_btn, "secondary", small=True)
        copy_btn.clicked.connect(self.copy_all)
        header.addWidget(copy_btn)

        save_btn = QPushButton("导出")
        apply_button_variant(save_btn, "success", small=True)
        save_btn.clicked.connect(self.save_code)
        header.addWidget(save_btn)
        layout.addLayout(header)

        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        self.warning_label.setStyleSheet(
            "color:#f9e2af;background:#313244;border:1px solid #45475a;"
            "border-radius:4px;padding:4px 6px;font-size:12px;"
        )
        layout.addWidget(self.warning_label)

        # 代码编辑器
        self.code_edit = QTextEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setFont(QFont("Consolas", 11))
        layout.addWidget(self.code_edit)

    def update_code(self, code: str):
        self.code_edit.setPlainText(code)

    def set_model(self, model):
        self._model = model

    def update_warnings(self, warnings: list[str] | None):
        """Display FDS validation warnings outside the status bar."""

        warnings = warnings or []
        if not warnings:
            self.warning_label.clear()
            self.warning_label.setVisible(False)
            return
        shown = " | ".join(warnings[:4])
        if len(warnings) > 4:
            shown += f" (+{len(warnings) - 4})"
        self.warning_label.setText(f"⚠ {shown}")
        self.warning_label.setVisible(True)

    def find_next(self):
        query = self.search_edit.text().strip()
        if not query:
            return
        if self.code_edit.find(query):
            return
        cursor = self.code_edit.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.code_edit.setTextCursor(cursor)
        self.code_edit.find(query)

    def copy_all(self):
        QApplication.clipboard().setText(self.code_edit.toPlainText())

    def save_code(self):
        default_filename = (
            default_fds_filename(self._model)
            if self._model is not None
            else "building_preview.fds"
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出FDS文件",
            default_filename,
            "FDS文件 (*.fds);;文本文件 (*.txt);;所有文件 (*)",
        )
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.code_edit.toPlainText())
