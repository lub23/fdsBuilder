#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File  : mainwindow.py
@Author: Lubber
@Date  : 2026-01-22
@Version : 1.0
@Desc  : Defining constants and configurations for the GUI
"""

import json

# Qt GUI
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QCheckBox,
    QPushButton,
    QTabWidget,
    QFileDialog,
    QMessageBox,
    QSplitter,
    QDialog,
    QToolBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QToolButton,
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QKeySequence
from models.building import BuildingModel
from models.materials import MATERIAL_LIBRARY
from generators.fds_generator import FDSGenerator, validate_fds

from ui.viewer_3d import Viewer3D, HAS_PYVISTA
from ui.blueprint_viewer import BlueprintViewer
from ui.fds_preview import FDSPreviewPanel
from ui.simulation_control_panel import SimulationControlPanel
from ui.styles import *
from ocr.blueprint_ocr import *
from ui.facility_panel import FacilityListPanel


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FDS建筑模型生成器")
        self.setMinimumSize(1400, 900)
        self.model = BuildingModel()
        self.setup_ui()
        self.setup_menu()
        self.setup_toolbar()
        self._refresh_scene_list()
        self.refresh_3d()
        self.update_preview()
        # 同步模拟控制面板
        self.simulation_control.set_model(self.model)


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

        # 等效模型生成面板
        self.facility_panel = FacilityListPanel()
        self.facility_panel.facility_selected.connect(self._on_facility_selected)
        self.facility_panel.building_added.connect(self._on_building_added)
        self.facility_panel.scene_building_removed.connect(
            self._on_scene_building_removed
        )
        self.facility_panel.scene_building_selected.connect(
            self._on_scene_building_selected
        )
        self.facility_panel.scene_building_offset_changed.connect(
            self._on_scene_building_offset_changed
        )
        left_layout.addWidget(self.facility_panel)

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
            "QPushButton:hover{background:#94e2d5;color:#1e1e2e}"
        )
        refresh_btn.clicked.connect(self.refresh_3d)
        toolbar.addWidget(refresh_btn)
        reset_view_btn = QPushButton("🎯 重置视角")
        reset_view_btn.setFixedHeight(26)
        reset_view_btn.setStyleSheet(
            "QPushButton{color:#1e1e2e;background:#89b4fa;font-weight:bold;"
            "padding:2px 8px;border-radius:3px}"
            "QPushButton:hover{background:#74c7ec}"
        )
        reset_view_btn.clicked.connect(self.viewer_3d.setup_camera)
        toolbar.addWidget(reset_view_btn)

        toolbar.addStretch()
        center_layout.addLayout(toolbar)
        center_layout.addWidget(self.viewer_3d)

        splitter.addWidget(center_panel)

        # ========== 右侧面板 - FDS代码 ==========
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 10, 10, 10)

        self.simulation_control = SimulationControlPanel()
        self.simulation_control.parameters_changed.connect(self._on_sim_param_changed)
        right_layout.addWidget(self.simulation_control)

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
            self.model.from_dict(data)
            # 确保外墙生成
            self.model.update_z_offsets()
            self.model.update_external_walls()
            self.update_preview()
            self.refresh_3d()

            # 重置视角
            self.viewer_3d._first_render = True
            self.viewer_3d.update_model(self.model)
        except Exception as e:
            QMessageBox.critical(self, "应用失败", f"无法应用识别结果：{str(e)}")

    def refresh_3d(self, first_render=False):
        """刷新3D视图"""
        try:
            model = self.model
            self.viewer_3d._first_render = first_render
            self.viewer_3d.update_model(model)
        except Exception as e:
            self.statusBar().showMessage(f"3D错误: {str(e)}")
    
    def _on_sim_param_changed(self):
        """模拟参数变化时更新FDS文本和3D视图"""
        self.update_preview()
        self.refresh_3d()

    def setup_menu(self):
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件")

        new_action = QAction("新建项目(&N)", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)

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

        # 设置菜单
        settings_menu = menubar.addMenu("设置")

        fds_path_action = QAction("设置FDS程序路径", self)
        fds_path_action.triggered.connect(self.set_fds_path)
        settings_menu.addAction(fds_path_action)

        smv_path_action = QAction("设置Smokeview程序路径", self)
        smv_path_action.triggered.connect(self.set_smv_path)
        settings_menu.addAction(smv_path_action)

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
            model = self.model

            generator = FDSGenerator(model)
            fds_code = generator.generate()
            self.fds_preview.update_code(fds_code)

            # Validate FDS output
            warnings = validate_fds(fds_code)
            if warnings:
                warn_text = " | ".join(warnings[:3])
                if len(warnings) > 3:
                    warn_text += f" (+{len(warnings) - 3})"
            else:
                warn_text = ""

            n_bld = len(model.building_group.buildings)
            n_w = n_o = n_c = 0
            for b in model.building_group.buildings:
                for s in b.stories:
                    n_w += len(s.walls)
                    n_o += len(s.openings)
                    n_c += len(s.combustibles.items)
            if n_bld > 1:
                message = f"建筑:{n_bld}  |  墙体:{n_w}  |  开口:{n_o}  |  可燃物:{n_c}"
            else:
                message = (
                    f"楼层:{model.num_stories}  |  墙体:{n_w}  |  "
                    f"开口:{n_o}  |  可燃物:{n_c}  |  "
                    f"模型: {model.length:.1f}×{model.width:.1f}×{model.total_height:.1f}m"
                )
            if warn_text:
                message += f"  ⚠ {warn_text}"
            self.statusBar().showMessage(message)
        except Exception as e:
            self.statusBar().showMessage(f"错误: {str(e)}")

    def new_project(self):
        reply = QMessageBox.question(
            self,
            "新建项目",
            "是否创建新项目？当前未保存的修改将丢失。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.model = BuildingModel()
            self.simulation_control.set_model(self.model)
            self._refresh_scene_list()
            self.update_preview()
            self.refresh_3d()
            self.statusBar().showMessage("已创建新项目")

    def open_config(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开配置文件", "", "JSON文件 (*.json);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.model = BuildingModel()
                self.model.from_dict(data)
                self.simulation_control.set_model(self.model)
                self._refresh_scene_list()
                self.update_preview()
                self.refresh_3d(True)
                self.statusBar().showMessage(f"已加载: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法加载配置文件:\n{str(e)}")

    def save_config(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存配置文件", "building_config.json", "JSON文件 (*.json)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(self.model.to_dict(), f, indent=4, ensure_ascii=False)
                self.statusBar().showMessage(f"已保存: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法保存配置文件:\n{str(e)}")

    def export_fds(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出FDS文件", "building.fds", "FDS文件 (*.fds)"
        )
        if file_path:
            try:
                generator = FDSGenerator(self.model)
                fds_code = generator.generate()
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(fds_code)

                QMessageBox.information(
                    self,
                    "导出成功",
                    f"FDS文件已导出到:\n{file_path}\n\n可以使用FDS进行模拟计算。",
                )
                self.statusBar().showMessage(f"已导出: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法导出FDS文件:\n{str(e)}")

    def _on_facility_selected(self, model_dict):
        """处理从设施面板选择的等效模型（替换整个模型，用于一级目标）"""
        try:
            self.model = BuildingModel()
            self.model.from_dict(model_dict)
            self.simulation_control.set_model(self.model)
            self.model.update_z_offsets()
            self.model.update_external_walls()
            self._refresh_scene_list()
            self.update_preview()
            self.refresh_3d(True)
            self.statusBar().showMessage(
                f"模型已生成 ({len(self.model.building_group.buildings)} 栋建筑)"
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法应用等效模型: {str(e)}")

    def _on_building_added(self, model_dict):
        """追加或替换一栋子目标建筑到现有模型"""
        try:
            from models.building import Building, BuildingGroup
            bg_data = model_dict.get("building_group", {})
            new_buildings = bg_data.get("buildings", [])
            if not new_buildings:
                return
            new_bld = Building.from_dict(new_buildings[0])
            existing = self.model.building_group.buildings
            if self._is_default_building(existing):
                existing[0] = new_bld
            else:
                if existing:
                    max_x_end = max(b.x_offset + b.length / 2 for b in existing)
                    new_bld.x_offset = max_x_end + 5.0 + new_bld.length / 2
                else:
                    new_bld.x_offset = 0.0
                new_bld.y_offset = 0.0
                for b in existing:
                    if self._buildings_overlap(b, new_bld):
                        new_bld.x_offset = (
                            b.x_offset + b.length / 2 + 5.0 + new_bld.length / 2
                        )
                self.model.building_group.add_building(new_bld)
            self.model.update_z_offsets()
            self.model.update_external_walls()
            self.simulation_control.set_model(self.model)
            self._refresh_scene_list()
            self.update_preview()
            self.refresh_3d(True)
            self.statusBar().showMessage(
                f"模型已生成 ({len(self.model.building_group.buildings)} 栋建筑)"
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法追加建筑: {str(e)}")

        
    def _is_default_building(self, buildings):
        """检测是否为默认空建筑（无故事数、无墙）"""
        if len(buildings) != 1:
            return False
        b = buildings[0]
        return len(b.stories) == 1 and len(b.stories[0].walls) == 0

    @staticmethod
    def _buildings_overlap(a, b, margin=1.0):
        """Check if two buildings overlap in XY plane (with margin)."""
        a_xmin = a.x_offset - a.length / 2 - margin
        a_xmax = a.x_offset + a.length / 2 + margin
        a_ymin = a.y_offset - a.width / 2 - margin
        a_ymax = a.y_offset + a.width / 2 + margin
        b_xmin = b.x_offset - b.length / 2
        b_xmax = b.x_offset + b.length / 2
        b_ymin = b.y_offset - b.width / 2
        b_ymax = b.y_offset + b.width / 2
        return not (
            b_xmin >= a_xmax or b_xmax <= a_xmin or b_ymin >= a_ymax or b_ymax <= a_ymin
        )

    def _refresh_scene_list(self):
        """Sync the scene list widget with current model buildings."""
        self.facility_panel.update_scene_list(self.model.building_group.buildings)

    def _on_scene_building_removed(self, index):
        """Remove a building from the scene by index."""
        buildings = self.model.building_group.buildings
        if index < 0 or index >= len(buildings):
            return
        if len(buildings) <= 1:
            QMessageBox.warning(self, "提示", "至少保留一栋建筑")
            return
        name = buildings[index].name
        del buildings[index]

        # Re-sync compat properties from first remaining building
        if buildings:
            b0 = buildings[0]
            self.model.length = b0.length
            self.model.width = b0.width
            self.model.wall_thickness = b0.wall_thickness
            self.model.stories = b0.stories
            self.model.roof = b0.roof
            self.model.materials = b0.materials

        self.model.update_z_offsets()
        self.simulation_control.set_model(self.model)
        self._refresh_scene_list()
        self.update_preview()
        self.refresh_3d(True)
        self.statusBar().showMessage(f"已删除建筑「{name}」")

    def _on_scene_building_selected(self, index):
        """Select a building in the scene and highlight in 3D."""
        buildings = self.model.building_group.buildings
        if 0 <= index < len(buildings):
            b = buildings[index]
            self.statusBar().showMessage(f"已选中建筑 #{index + 1}: {b.name}")
            # Highlight in 3D
            self.viewer_3d.highlight_building(index)

    def _on_scene_building_offset_changed(self, index, x_off, y_off):
        """Handle building offset change from scene panel."""
        buildings = self.model.building_group.buildings
        if 0 <= index < len(buildings):
            buildings[index].x_offset = x_off
            buildings[index].y_offset = y_off
            self._refresh_scene_list()
            self.update_preview()
            self.refresh_3d()

    def show_about(self):
        QMessageBox.about(
            self,
            "关于",
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
            "</ul>",
        )

    def show_materials(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("材料库")
        dialog.setMinimumSize(600, 400)

        layout = QVBoxLayout(dialog)

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(
            ["材料ID", "名称", "密度(kg/m³)", "导热系数(W/mK)", "比热(kJ/kgK)"]
        )
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
    
    def set_fds_path(self):
        """设置FDS程序路径"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择FDS可执行文件", "", "可执行文件 (*.exe);;所有文件 (*)"
        )
        if file_path:
            # 保存到配置文件
            self._save_program_path("fds", file_path)
            QMessageBox.information(self, "设置成功", f"FDS路径已设置为:\n{file_path}")

    def set_smv_path(self):
        """设置Smokeview程序路径"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Smokeview可执行文件", "", "可执行文件 (*.exe);;所有文件 (*)"
        )
        if file_path:
            self._save_program_path("smokeview", file_path)
            QMessageBox.information(
                self, "设置成功", f"Smokeview路径已设置为:\n{file_path}"
            )

    def _save_program_path(self, program: str, path: str):
        """保存程序路径到配置文件"""
        import json
        import os

        config_dir = os.path.join(os.path.dirname(__file__), "..")
        config_file = os.path.join(config_dir, "program_paths.json")

        paths = {}
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                paths = json.load(f)

        paths[program] = path

        with open(config_file, "w") as f:
            json.dump(paths, f, indent=2)

    @staticmethod
    def _load_program_path(program: str) -> str:
        """加载程序路径"""
        import json
        import os

        config_dir = os.path.join(os.path.dirname(__file__), "..")
        config_file = os.path.join(config_dir, "program_paths.json")

        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                paths = json.load(f)
                return paths.get(program, "")
        return ""

    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        if HAS_PYVISTA:
            self.viewer_3d.close()
        event.accept()
