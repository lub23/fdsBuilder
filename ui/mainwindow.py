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
    QPushButton,
    QFileDialog,
    QMessageBox,
    QSplitter,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QAction, QKeySequence
from models.building import BuildingGroup, Building
from models.materials import MATERIAL_LIBRARY
from models.geometry import clear_layout_cache
from generators.fds_generator import FDSGenerator, validate_fds

from ui.viewer_3d import Viewer3D, HAS_PYVISTA
from ui.fds_preview import FDSPreviewPanel
from ui.simulation_control_panel import SimulationControlPanel
from ui.styles import apply_button_variant
from ui.facility_panel import FacilityListPanel
from services.fds_naming import default_fds_filename


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FDS建筑模型生成器")
        self.setMinimumSize(1400, 900)
        self.showMaximized()
        self._settings = QSettings("fdsBuilder", "fdsBuilder")
        self.model = BuildingGroup(buildings=[Building()])

        # FDS preview debounce timer — prevents regeneration on rapid slider changes
        self._fds_preview_timer = QTimer(self)
        self._fds_preview_timer.setSingleShot(True)
        self._fds_preview_timer.timeout.connect(self._do_update_preview)

        self.setup_ui()
        self.setup_menu()
        self._refresh_scene_list()
        self.refresh_3d()
        self.update_preview()
        # 同步模拟控制面板
        self.simulation_control.set_model(self.model)
        self.fds_preview.set_model(self.model)


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
        self.facility_panel.facility_predict_requested.connect(
            self._on_facility_predict_requested
        )
        self.facility_panel.scene_building_selected.connect(
            self._on_scene_building_selected
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
        apply_button_variant(refresh_btn, "success", small=True)
        refresh_btn.clicked.connect(self.refresh_3d)
        toolbar.addWidget(refresh_btn)
        reset_view_btn = QPushButton("🎯 重置视角")
        reset_view_btn.setFixedHeight(26)
        apply_button_variant(reset_view_btn, "primary", small=True)
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
        right_layout.setSpacing(6)

        self.simulation_control = SimulationControlPanel()
        self.simulation_control.parameters_changed.connect(self._on_sim_param_changed)
        # Stretch 0: simulation control (heat + sim + run buttons) takes only
        # the height its content needs; no slack beneath it.
        right_layout.addWidget(self.simulation_control, 0)

        self.fds_preview = FDSPreviewPanel()
        # Stretch 1: FDS code preview fills whatever vertical space remains so
        # there is no visible gap between the run buttons and the preview.
        right_layout.addWidget(self.fds_preview, 1)

        right_panel.setMinimumWidth(350)
        right_panel.setMaximumWidth(500)
        splitter.addWidget(right_panel)

        # 设置/恢复分割比例
        self.splitter = splitter
        saved_state = self._settings.value("main_window/splitter_state")
        if saved_state:
            splitter.restoreState(saved_state)
        else:
            splitter.setSizes([400, 600, 400])

        main_layout.addWidget(splitter)

    def refresh_3d(self, first_render=False):
        """刷新3D视图"""
        try:
            model = self.model
            self.viewer_3d._first_render = first_render
            self.viewer_3d.update_model(model)
        except Exception as e:
            self.statusBar().showMessage(f"3D错误: {str(e)}")

    def _on_sim_param_changed(self, kind: str = "sim"):
        """Dispatch 3D update by event kind; FDS text always refreshes."""
        self.update_preview()
        if kind == "heat_geom":
            self.viewer_3d.update_heat_source(self.model)
        elif kind == "slice_device":
            self.viewer_3d.update_slices_devices(self.model)
        # "heat_flux" and "sim" do not touch 3D

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

        # 帮助菜单
        help_menu = menubar.addMenu("帮助")

        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        material_action = QAction("材料库", self)
        material_action.triggered.connect(self.show_materials)
        help_menu.addAction(material_action)

    def update_preview(self, debounce=True):
        """更新FDS代码和状态栏。debounce=True delays FDS generation to avoid blocking on rapid parameter changes."""
        if debounce and self._fds_preview_timer.isActive():
            self._fds_preview_timer.stop()
        if debounce:
            self._fds_preview_timer.start(500)
        else:
            self._do_update_preview()

    def _do_update_preview(self):
        try:
            model = self.model

            # Invalidate layout cache on every full preview generation —
            # the cache is only useful across multiple rapid calls within
            # the same model state (e.g. 3D viewer + FDS generator sharing
            # results).  When a new model is set, stale cache entries must
            # be evicted so the new geometry is placed correctly.
            clear_layout_cache()

            # FDS preview
            generator = FDSGenerator(model)
            fds_code = generator.generate()
            self.fds_preview.update_code(fds_code)

            # Validate FDS output
            warnings = validate_fds(fds_code)
            self.fds_preview.update_warnings(warnings)
            if warnings:
                warn_text = " | ".join(warnings[:3])
                if len(warnings) > 3:
                    warn_text += f" (+{len(warnings) - 3})"
            else:
                warn_text = ""

            n_bld = len(model.buildings)
            n_o = n_c = 0
            for b in model.buildings:
                for s in b.stories:
                    n_o += len(s.openings)
                    for fc in s.fire_compartments:
                        n_c += len(fc.combustibles)
            if n_bld > 1:
                message = f"建筑:{n_bld}  |  开口:{n_o}  |  可燃物:{n_c}"
            else:
                message = (
                    f"楼层:{model.num_stories}  |  "
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
            self.viewer_3d.clear_cache()
            self.model = BuildingGroup(buildings=[Building()])
            self.simulation_control.set_model(self.model)
            self.fds_preview.set_model(self.model)
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
                self.model = BuildingGroup.from_dict(data)
                self.simulation_control.set_model(self.model)
                self.fds_preview.set_model(self.model)
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
                data = {"building_group": self.model.to_dict()}
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                self.statusBar().showMessage(f"已保存: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法保存配置文件:\n{str(e)}")

    def export_fds(self):
        default_filename = default_fds_filename(self.model)

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出FDS文件", default_filename, "FDS文件 (*.fds)"
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
            self.model = BuildingGroup.from_dict(model_dict)
            self.simulation_control.set_model(self.model)
            self.fds_preview.set_model(self.model)
            self.model.update_z_offsets()
            self._refresh_scene_list()
            self.viewer_3d._first_render = True
            self.update_preview()
            self.refresh_3d(first_render=True)
            self.statusBar().showMessage(
                f"模型已生成 ({len(self.model.buildings)} 栋建筑)"
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法应用等效模型: {str(e)}")

    def _on_facility_predict_requested(self, facility_name: str):
        """记录当前选中的训练设施（无三维模型），供右侧预测按钮使用。"""
        self.simulation_control.set_pending_trained_facility(facility_name)

    def _on_building_added(self, building_obj):
        """追加或替换一栋子目标建筑到现有模型"""
        try:
            # building_obj is a Building instance emitted by FacilityPanel
            if isinstance(building_obj, Building):
                new_bld = building_obj
            elif isinstance(building_obj, dict):
                # Legacy dict format fallback
                bg_data = building_obj.get("building_group", building_obj)
                new_buildings = bg_data.get("buildings", [])
                if not new_buildings:
                    return
                new_bld = Building.from_dict(new_buildings[0])
            else:
                return

            existing = self.model.buildings
            if self._is_default_building(existing):
                existing[0] = new_bld
            else:
                self.model.add_building(new_bld)
            self.model.update_z_offsets()
            self.simulation_control.set_model(self.model)
            self.fds_preview.set_model(self.model)
            self._refresh_scene_list()
            self.viewer_3d._first_render = True
            self.update_preview()
            self.refresh_3d(first_render=True)
            self.statusBar().showMessage(
                f"模型已生成 ({len(self.model.buildings)} 栋建筑)"
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法追加建筑: {str(e)}")


    def _is_default_building(self, buildings):
        """检测是否为默认空建筑（无楼层或仅一个空楼层）"""
        if len(buildings) != 1:
            return False
        b = buildings[0]
        if not b.stories:
            return True
        return len(b.stories) == 1 and len(b.stories[0].openings) == 0 and len(b.stories[0].fire_compartments) == 0

    def _refresh_scene_list(self):
        """Sync the scene list widget with current model buildings."""
        self.facility_panel.update_scene_list(self.model.buildings)

    def _on_scene_building_selected(self, index):
        """Select a building in the scene and highlight in 3D."""
        buildings = self.model.buildings
        if 0 <= index < len(buildings):
            b = buildings[index]
            self.statusBar().showMessage(f"已选中建筑 #{index + 1}: {b.name}")
            # Highlight in 3D
            self.viewer_3d.highlight_building(index)

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

    def closeEvent(self, event):
        """关闭窗口时清理资源"""
        if hasattr(self, "splitter"):
            self._settings.setValue("main_window/splitter_state", self.splitter.saveState())
        if HAS_PYVISTA:
            self.viewer_3d.close()
        event.accept()
