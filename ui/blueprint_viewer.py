
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
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QApplication
)
from PySide6.QtCore import Qt, Signal
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
    """图纸预览组件"""
    
    dimensions_extracted = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_path = None
        self.pixmap = None
        self.processor = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 图片显示区域
        self.image_label = QLabel("拖放图纸到此处\n或点击上传按钮")
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
        layout.addWidget(self.image_label)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        upload_btn = QPushButton("📁 上传图纸")
        upload_btn.clicked.connect(self.upload_image)
        btn_layout.addWidget(upload_btn)
        
        clear_btn = QPushButton("清除")
        clear_btn.setObjectName("secondaryBtn")
        clear_btn.clicked.connect(self.clear_image)
        btn_layout.addWidget(clear_btn)

        recognize_btn = QPushButton("🔍 识别图纸")
        recognize_btn.setObjectName("successBtn")
        recognize_btn.clicked.connect(self.recognize_blueprint)
        btn_layout.addWidget(recognize_btn)
        
        layout.addLayout(btn_layout)
        
        # 提示
        tip_label = QLabel("提示: 上传建筑平面图后，可参考图纸手动输入尺寸参数")
        tip_label.setStyleSheet("color: #6c7086; font-size: 12px;")
        tip_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(tip_label)


    
    def upload_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图纸",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*)"
        )
        if file_path:
            self.load_image(file_path)
    
    def load_image(self, path):
        self.image_path = path
        self.pixmap = QPixmap(path)
        if not self.pixmap.isNull():
            scaled = self.pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
    
    def clear_image(self):
        self.image_path = None
        self.pixmap = None
        self.image_label.clear()
        self.image_label.setText("拖放图纸到此处\n或点击上传按钮")
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pixmap and not self.pixmap.isNull():
            scaled = self.pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)

    def recognize_blueprint(self):
        if not self.image_path:
            QMessageBox.warning(self, "提示", "请先上传图纸")
            return
        
        try:
            
            self.statusBar = self.window().statusBar()
            self.statusBar.showMessage("正在识别...")
            QApplication.processEvents()
            
            recognizer = BlueprintRecognizer(API_KEY)
            result = recognizer.recognize(self.image_path)
            
            if result:
                self.dimensions_extracted.emit(recognizer.to_model_dict())
                QMessageBox.information(self, "成功", 
                    f"识别完成！\n尺寸: {result.length}m × {result.width}m × {result.height}m\n"
                    f"内墙: {len(result.walls)}面\n开口: {len(result.openings)}个")
            else:
                QMessageBox.warning(self, "失败", "识别失败")
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

