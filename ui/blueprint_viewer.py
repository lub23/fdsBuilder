
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : blueprint_viewer.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : Blueprint viewer component for building model visualization and dimension extraction
'''
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QApplication, QLineEdit, QComboBox,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap
from ocr.blueprint_ocr import BlueprintRecognizer
from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)
API_KEY = os.getenv("API_KEY")
# ============================================================
# 图纸预览组件
# ============================================================
class BlueprintViewer(QWidget):
    """图纸预览+OCR识别"""

    # 识别完成后发射，携带BuildingModel.from_dict兼容的dict
    dimensions_extracted = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_path = None
        self.pixmap = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # 图片显示区
        self.image_label = QLabel("拖放图纸到此处\n或点击上传按钮\n\n支持 PNG/JPG/PDF")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #313244;
                border: 2px dashed #585b70;
                border-radius: 10px;
                color: #a6adc8;
                font-size: 14px;
            }
        """)
        self.image_label.setScaledContents(False)
        self.image_label.setAcceptDrops(True)
        layout.addWidget(self.image_label)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        upload_btn = QPushButton("📁 上传图纸")
        upload_btn.setStyleSheet(
            "QPushButton{background:#89b4fa;color:#1e1e2e;font-weight:bold;"
            "padding:4px 12px;border-radius:4px}"
            "QPushButton:hover{background:#74c7ec}")
        upload_btn.clicked.connect(self.upload_image)
        btn_layout.addWidget(upload_btn)

        self.recognize_btn = QPushButton("🔍 识别图纸")
        self.recognize_btn.setStyleSheet(
            "QPushButton{background:#a6e3a1;color:#1e1e2e;font-weight:bold;"
            "padding:4px 12px;border-radius:4px}"
            "QPushButton:hover{background:#94e2d5}")
        self.recognize_btn.clicked.connect(self.recognize_blueprint)
        btn_layout.addWidget(self.recognize_btn)

        clear_btn = QPushButton("🗑️ 清除")
        clear_btn.setStyleSheet(
            "QPushButton{background:#f38ba8;color:#1e1e2e;font-weight:bold;"
            "padding:4px 12px;border-radius:4px}"
            "QPushButton:hover{background:#e06080}")
        clear_btn.clicked.connect(self.clear_image)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 状态/结果标签
        self.status_label = QLabel("上传建筑平面图后点击「识别图纸」自动提取墙体和开口")
        self.status_label.setStyleSheet("color:#6c7086; font-size:12px;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def upload_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图纸", "",
            "图片/PDF (*.png *.jpg *.jpeg *.bmp *.pdf);;所有文件 (*)")
        if file_path:
            self.load_image(file_path)

    def load_image(self, path):
        self.image_path = path

        if path.lower().endswith('.pdf'):
            # PDF先转图片预览
            try:
                from ocr.blueprint_ocr import BlueprintRecognizer
                temp = BlueprintRecognizer("").pdf_to_image(path)
                self.pixmap = QPixmap(temp)
                import os
                os.remove(temp)
            except Exception:
                self.pixmap = None
                self.image_label.setText(f"PDF已加载: {Path(path).name}\n（预览需要pymupdf）")
                return
        else:
            self.pixmap = QPixmap(path)

        if self.pixmap and not self.pixmap.isNull():
            self._update_pixmap()
            self.status_label.setText(f"已加载: {Path(path).name}")
            self.status_label.setStyleSheet("color:#a6e3a1; font-size:12px;")

    def _update_pixmap(self):
        if self.pixmap and not self.pixmap.isNull():
            scaled = self.pixmap.scaled(
                self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)

    def clear_image(self):
        self.image_path = None
        self.pixmap = None
        self.image_label.clear()
        self.image_label.setText("拖放图纸到此处\n或点击上传按钮\n\n支持 PNG/JPG/PDF")
        self.status_label.setText("上传建筑平面图后点击「识别图纸」自动提取墙体和开口")
        self.status_label.setStyleSheet("color:#6c7086; font-size:12px;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_pixmap()

    def recognize_blueprint(self):
        if not self.image_path:
            QMessageBox.warning(self, "提示", "请先上传图纸")
            return
        # 禁用按钮，显示进度
        self.recognize_btn.setEnabled(False)
        self.recognize_btn.setText("🔄 识别中...")
        self.status_label.setText("正在调用大模型识别，请稍候...")
        self.status_label.setStyleSheet("color:#f9e2af; font-size:12px;")
        QApplication.processEvents()

        try:
            recognizer = BlueprintRecognizer(API_KEY)
            result = recognizer.recognize(self.image_path)

            if result:
                # 发射信号，MainWindow接收后应用到模型
                self.dimensions_extracted.emit(result)

                summary = recognizer.get_summary()
                self.status_label.setText(f"✅ 识别成功！\n{summary}")
                self.status_label.setStyleSheet("color:#a6e3a1; font-size:12px;")

                QMessageBox.information(self, "识别完成",
                    f"已识别并应用到模型：\n{summary}\n\n"
                    f"请在「参数设置」中检查并调整。")
            else:
                self.status_label.setText("❌ 识别失败，未返回有效数据")
                self.status_label.setStyleSheet("color:#f38ba8; font-size:12px;")
                QMessageBox.warning(self, "失败", "识别未返回有效数据")

        except Exception as e:
            self.status_label.setText(f"❌ 错误: {str(e)}")
            self.status_label.setStyleSheet("color:#f38ba8; font-size:12px;")
            QMessageBox.critical(self, "识别错误", str(e))

        finally:
            self.recognize_btn.setEnabled(True)
            self.recognize_btn.setText("🔍 识别图纸")