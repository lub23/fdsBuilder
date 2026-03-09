#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : mainwindow.py
@Author: Lubber
@Date  : 2026-01-22
@Version : 1.0
@Desc  : Defining constants and configurations for the GUI
'''

import json

# Qt GUI
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QCheckBox, QPushButton, QTabWidget,
    QFileDialog, QMessageBox, QSplitter, QDialog,QToolBar, 
    QTableWidget, QTableWidgetItem, QHeaderView,QToolButton
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import (
    QAction, QKeySequence
)
from models.building import BuildingModel
from models.materials import MATERIAL_LIBRARY
from generators.fds_generator import FDSGenerator

from ui.viewer_3d import Viewer3D, HAS_PYVISTA
from ui.blueprint_viewer import BlueprintViewer
from ui.param_panel import ParameterPanel
from ui.fds_preview import FDSPreviewPanel
from ui.styles import *
from ocr.blueprint_ocr import *
from ui.dialogs import FacilityDialog

# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FDS建筑模型生成器")
        self.setMinimumSize(1400, 900)
        self.setup_ui()
        self.setup_menu()
        self.setup_toolbar()
        # 初始更新
        QTimer.singleShot(100, lambda: (self.refresh_3d(), self.update_preview()))
    
    def setup_ui(self):
        # 主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # ========== 左侧面板 ==========
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 5, 10)
        
        # 标签页
        self.left_tabs = QTabWidget()
        
        # 参数面板
        self.param_panel = ParameterPanel()
        self.param_panel.parameters_changed.connect(self._on_param_changed)
        self.param_panel.stories_changed.connect(self._rebuild_story_checks)
        
        self.left_tabs.addTab(self.param_panel, "⚙️ 参数设置")
        
        # 图纸面板
        self.blueprint_panel = BlueprintViewer()
        self.blueprint_panel.dimensions_extracted.connect(self._apply_ocr_result)
        self.left_tabs.addTab(self.blueprint_panel, "📐 图纸参考")
        
        left_layout.addWidget(self.left_tabs)

        left_panel.setMinimumWidth(400)
        left_panel.setMaximumWidth(500)
        splitter.addWidget(left_panel)
        
        # ========== 中间面板 - 3D预览 ==========
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(5, 5, 5, 5)
        center_layout.setSpacing(4)

        # 3D查看器
        self.viewer_3d = Viewer3D()
        # 顶部工具栏：标题 + 楼层选择 + 刷新
        # 顶部工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        # 刷新按钮放最左边
        refresh_btn = QPushButton("🔄 刷新模型")
        refresh_btn.setFixedHeight(26)
        refresh_btn.setStyleSheet(
            "QPushButton{background:#a6e3a1;color:#1e1e2e;font-weight:bold;"
            "padding:2px 10px;border-radius:3px}"
            "QPushButton:hover{background:#94e2d5;color:#1e1e2e}")
        refresh_btn.clicked.connect(self.refresh_3d)
        toolbar.addWidget(refresh_btn)
        reset_view_btn = QPushButton("🎯 重置视角")
        reset_view_btn.setFixedHeight(26)
        reset_view_btn.setStyleSheet(
            "QPushButton{color:#1e1e2e;background:#89b4fa;font-weight:bold;"
            "padding:2px 8px;border-radius:3px}"
            "QPushButton:hover{background:#74c7ec}")
        reset_view_btn.clicked.connect(self.viewer_3d.setup_camera)
        toolbar.addWidget(reset_view_btn)

        toolbar.addWidget(QLabel("│"))

        toolbar.addWidget(QLabel("楼层:"))
        self.story_checks_container = QHBoxLayout()
        self.story_checks_container.setSpacing(4)
        self.story_checks = []
        toolbar.addLayout(self.story_checks_container)

        # 屋顶控制
        self.roof_check = QCheckBox("屋顶")
        self.roof_check.setChecked(True)
        self.roof_check.setStyleSheet("color:#cdd6f4; font-size:12px;")
        self.roof_check.toggled.connect(self._toggle_roof)
        toolbar.addWidget(self.roof_check)

        toolbar.addStretch()
        center_layout.addLayout(toolbar)
        center_layout.addWidget(self.viewer_3d)
        splitter.addWidget(center_panel)

        self.param_panel.wall_selected.connect(self.viewer_3d.highlight_wall)
        self.param_panel.opening_selected.connect(self.viewer_3d.highlight_opening)

        # 初始化楼层选择
        self._rebuild_story_checks()
        
        # ========== 右侧面板 - FDS代码 ==========
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 10, 10, 10)
        
        self.fds_preview = FDSPreviewPanel()
        right_layout.addWidget(self.fds_preview)
        
        right_panel.setMinimumWidth(350)
        right_panel.setMaximumWidth(500)
        splitter.addWidget(right_panel)
        
        # 设置分割比例
        splitter.setSizes([400, 600, 400])
        
        main_layout.addWidget(splitter)
    
    def _apply_ocr_result(self, data: dict):
        """将OCR识别结果应用到模型"""
        try:
            from models.building import BuildingModel
            model = BuildingModel()
            model.from_dict(data)
            # 确保外墙生成
            model.update_z_offsets()
            model.update_external_walls()

            self.param_panel.set_model(model)
            self._rebuild_story_checks()
            self._on_param_changed()

            # 重置视角
            self.viewer_3d._first_render = True
            self.viewer_3d.update_model(model)

            # 切到参数面板
            self.left_tabs.setCurrentIndex(0)
        except Exception as e:
            QMessageBox.critical(self, "应用失败", f"无法应用识别结果：{str(e)}")

    def _rebuild_story_checks(self):
        for cb in self.story_checks:
            self.story_checks_container.removeWidget(cb)
            cb.deleteLater()
        self.story_checks.clear()

        model = self.param_panel.get_model()
        self.viewer_3d.visible_stories = set(range(len(model.stories)))

        for i, story in enumerate(model.stories):
            cb = QCheckBox(story.name)
            cb.setChecked(True)
            cb.setStyleSheet("color:#cdd6f4; font-size:12px;")
            cb.toggled.connect(lambda checked, idx=i: self._toggle_story(idx, checked))
            self.story_checks_container.addWidget(cb)
            self.story_checks.append(cb)

    def _toggle_story(self, index, visible):
        if visible:
            self.viewer_3d.visible_stories.add(index)
        else:
            self.viewer_3d.visible_stories.discard(index)
        self.refresh_3d()
    
    def _toggle_roof(self, visible):
        self.viewer_3d.show_roof = visible
        self.refresh_3d()

    def refresh_3d(self, first_render=False):
        """刷新3D视图"""
        try:
            model = self.param_panel.get_model()
            self.viewer_3d._first_render = first_render
            self.viewer_3d.update_model(model)
        except Exception as e:
            self.statusBar().showMessage(f"3D错误: {str(e)}")

    def setup_menu(self):
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        new_action = QAction("新建项目(&N)", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)

        act_facility = QAction("等效模型生成(&F)", self)
        act_facility.setShortcut("Ctrl+F")
        act_facility.triggered.connect(self._open_facility_dialog)
        file_menu.addAction(act_facility)
        
        open_action = QAction("打开配置(&O)", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.open_config)
        file_menu.addAction(open_action)
        
        save_action = QAction("保存配置(&S)", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_config)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        export_action = QAction("导出FDS文件(&E)", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self.export_fds)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出(&Q)", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        material_action = QAction("材料库", self)
        material_action.triggered.connect(self.show_materials)
        help_menu.addAction(material_action)
    
    def setup_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        
        # 新建
        new_btn = QToolButton()
        new_btn.setText("📄 新建")
        new_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        new_btn.clicked.connect(self.new_project)
        toolbar.addWidget(new_btn)

        act_btn = QToolButton()
        act_btn.setText("🏛️ 等效模型生成")
        act_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        act_btn.clicked.connect(self._open_facility_dialog)
        toolbar.addWidget(act_btn)

        # 打开
        open_btn = QToolButton()
        open_btn.setText("📂 打开")
        open_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        open_btn.clicked.connect(self.open_config)
        toolbar.addWidget(open_btn)
        
        # 保存
        save_btn = QToolButton()
        save_btn.setText("💾 保存")
        save_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        save_btn.clicked.connect(self.save_config)
        toolbar.addWidget(save_btn)
        
        toolbar.addSeparator()
        
        # 导出
        export_btn = QToolButton()
        export_btn.setText("📤 导出FDS")
        export_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        export_btn.setStyleSheet("QToolButton { color: #a6e3a1; font-weight: bold; }")
        export_btn.clicked.connect(self.export_fds)
        toolbar.addWidget(export_btn)
       
    def update_preview(self):
        """更新FDS代码和状态栏"""
        try:
            model = self.param_panel.get_model()

            generator = FDSGenerator(model)
            fds_code = generator.generate()
            self.fds_preview.update_code(fds_code)

            n_w = sum(len(s.walls) for s in model.stories)
            n_o = sum(len(s.openings) for s in model.stories)
            n_c = sum(len(s.combustibles.items) for s in model.stories)
            message = (f"楼层:{model.num_stories}  |  墙体:{n_w}  |  "
                    f"开口:{n_o}  |  可燃物:{n_c}  |  "
                    f"模型: {model.length:.1f}×{model.width:.1f}×{model.total_height:.1f}m")
            self.statusBar().showMessage(message)
        except Exception as e:
            self.statusBar().showMessage(f"错误: {str(e)}")
    
    def new_project(self):
        reply = QMessageBox.question(
            self, "新建项目",
            "是否创建新项目？当前未保存的修改将丢失。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.param_panel.set_model(BuildingModel())
            self.update_preview()
            self.refresh_3d()
            self.statusBar().showMessage("已创建新项目")

    def _open_facility_dialog(self):
        dlg = FacilityDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.result_model:
            self.param_panel.set_model(dlg.result_model)
            self._rebuild_story_checks()
            self.update_preview()
            self.refresh_3d(True)

    def open_config(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开配置文件", "", "JSON文件 (*.json);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                model = BuildingModel()
                model.from_dict(data)
                self.param_panel.set_model(model)
                self._rebuild_story_checks()
                self.update_preview()
                self.refresh_3d(True)
                self.statusBar().showMessage(f"已加载: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法加载配置文件:\n{str(e)}")
    
    def save_config(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存配置文件",
            "building_config.json",
            "JSON文件 (*.json)"
        )
        if file_path:
            try:
                model = self.param_panel.get_model()
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(model.to_dict(), f, indent=4, ensure_ascii=False)
                self.statusBar().showMessage(f"已保存: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法保存配置文件:\n{str(e)}")

    def export_fds(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出FDS文件",
            "building.fds",
            "FDS文件 (*.fds)"
        )
        if file_path:
            try:
                model = self.param_panel.get_model()
                generator = FDSGenerator(model)
                fds_code = generator.generate()
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(fds_code)
                
                QMessageBox.information(
                    self, "导出成功",
                    f"FDS文件已导出到:\n{file_path}\n\n"
                    f"可以使用FDS进行模拟计算。"
                )
                self.statusBar().showMessage(f"已导出: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法导出FDS文件:\n{str(e)}")
    
    def _on_param_changed(self):
        """参数变更：刷新3D（保持视角）+ 更新FDS"""
        try:
            self.update_preview()
            self.refresh_3d()
        except Exception as e:
            self.statusBar().showMessage(f"错误: {str(e)}")
    
    def show_about(self):
        QMessageBox.about(
            self, "关于",
            "<h2>FDS建筑模型生成器</h2>"
            "<p>版本: 1.0.0</p>"
            "<p>一个用于生成FDS（Fire Dynamics Simulator）"
            "建筑模型输入文件的可视化工具。</p>"
            "<p>特性:</p>"
            "<ul>"
            "<li>可视化参数配置</li>"
            "<li>3D模型预览</li>"
            "<li>自动生成FDS代码</li>"
            "<li>支持门窗开口</li>"
            "<li>支持热源配置</li>"
            "</ul>"
        )
    
    def show_materials(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("材料库")
        dialog.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["材料ID", "名称", "密度(kg/m³)", "导热系数(W/mK)", "比热(kJ/kgK)"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        table.setRowCount(len(MATERIAL_LIBRARY))
        for i, (mat_id, mat) in enumerate(MATERIAL_LIBRARY.items()):
            table.setItem(i, 0, QTableWidgetItem(mat_id))
            table.setItem(i, 1, QTableWidgetItem(mat["DESCRIPTION"]))
            table.setItem(i, 2, QTableWidgetItem(str(mat["DENSITY"])))
            table.setItem(i, 3, QTableWidgetItem(str(mat["CONDUCTIVITY"])))
            table.setItem(i, 4, QTableWidgetItem(str(mat["SPECIFIC_HEAT"])))
        
        layout.addWidget(table)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        if HAS_PYVISTA:
            self.viewer_3d.close()
        event.accept()




