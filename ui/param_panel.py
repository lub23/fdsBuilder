#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : param_panel.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : Parameter configuration panel for building model
'''
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QGroupBox, QGridLayout, 
    QLineEdit, QDoubleSpinBox, QComboBox, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QHBoxLayout, QFormLayout, QCheckBox,
    QMessageBox, QDialog, QSpinBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal

from models.building import BuildingModel
from models.materials import MATERIAL_LIBRARY

from ui.dialogs import WallDialog, OpeningDialog, RampEditorDialog, CombustibleDialog

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


class ParameterPanel(QWidget):
    """参数配置面板"""

    parameters_changed = Signal()
    wall_selected = Signal(int)
    opening_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = BuildingModel()
        self._syncing = False
        self.setup_ui()

    # ================================================================
    #                          UI 构建
    # ================================================================
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部固定：项目名称
        top = QHBoxLayout()
        top.setContentsMargins(8, 6, 8, 2)
        lbl = QLabel("项目:")
        lbl.setFixedWidth(36)
        self.chid_edit = QLineEdit("building")
        self.chid_edit.setPlaceholderText("CHID")
        self.chid_edit.textChanged.connect(self.on_param_changed)
        top.addWidget(lbl)
        top.addWidget(self.chid_edit)
        root.addLayout(top)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)

        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(6, 4, 6, 6)
        self.body_layout.setSpacing(6)

        self._build_geometry_section()
        self._build_wall_section()
        self._build_opening_section()
        self._build_combustible_section()
        self._build_heat_section()
        self._build_simulation_section()

        self.body_layout.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll)

    # ── 几何 + 材料 ──────────────────────────────────────
    def _build_geometry_section(self):
        grp = CollapsibleGroup("📐 几何 / 材料")
        g = QGridLayout()
        g.setSpacing(4)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)

        # 尺寸 — 第0~2行
        def dim_spin(val, lo, hi, suffix=" m"):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setValue(val)
            s.setSuffix(suffix)
            s.setDecimals(2)
            s.valueChanged.connect(self.on_dimension_changed)
            return s

        g.addWidget(QLabel("长度X:"), 0, 0)
        self.length_spin = dim_spin(20, 1, 10000)
        g.addWidget(self.length_spin, 0, 1)

        g.addWidget(QLabel("宽度Y:"), 0, 2)
        self.width_spin = dim_spin(15, 1, 10000)
        g.addWidget(self.width_spin, 0, 3)

        g.addWidget(QLabel("高度Z:"), 1, 0)
        self.height_spin = dim_spin(6, 1, 500)
        g.addWidget(self.height_spin, 1, 1)

        g.addWidget(QLabel("墙厚:"), 1, 2)
        self.thickness_spin = dim_spin(0.25, 0.01, 2)
        g.addWidget(self.thickness_spin, 1, 3)

        # 材料 — 第2~3行
        materials = list(MATERIAL_LIBRARY.keys())

        def mat_combo():
            c = QComboBox()
            c.addItems(materials)
            c.currentTextChanged.connect(self.on_param_changed)
            c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            return c

        g.addWidget(QLabel("墙体:"), 2, 0)
        self.wall_mat_combo = mat_combo()
        g.addWidget(self.wall_mat_combo, 2, 1)

        g.addWidget(QLabel("地板:"), 2, 2)
        self.floor_mat_combo = mat_combo()
        g.addWidget(self.floor_mat_combo, 2, 3)

        g.addWidget(QLabel("屋顶:"), 3, 0)
        self.roof_mat_combo = mat_combo()
        g.addWidget(self.roof_mat_combo, 3, 1)

        grp.content_layout.addLayout(g)
        self.body_layout.addWidget(grp)

    # ── 墙体 ────────────────────────────────────────────
    def _build_wall_section(self):
        grp = CollapsibleGroup("🧱 墙体")

        # 工具栏
        tb = QHBoxLayout()
        tb.setSpacing(4)
        btn_add = self._tool_btn("➕ 添加内墙", self.add_wall)
        btn_edit = self._tool_btn("✏️ 编辑", self.edit_wall)
        btn_del = self._tool_btn("🗑️ 删除", self.delete_wall, danger=True)
        tb.addWidget(btn_add)
        tb.addWidget(btn_edit)
        tb.addWidget(btn_del)
        tb.addStretch()
        grp.content_layout.addLayout(tb)

        # 表格
        self.wall_table = self._make_table(
            ["类型", "名称", "起点", "终点", "厚度"],
            [50, 0, 110, 110, 55])   # 起点终点给110px
        self.wall_table.setMinimumHeight(100)
        self.wall_table.setMaximumHeight(200)
        self.wall_table.itemSelectionChanged.connect(self.on_wall_selected)
        grp.content_layout.addWidget(self.wall_table)

        self.body_layout.addWidget(grp)

    # ── 开口 ────────────────────────────────────────────
    def _build_opening_section(self):
        grp = CollapsibleGroup("🚪 开口（门/窗）")

        tb = QHBoxLayout()
        tb.setSpacing(4)
        tb.addWidget(self._tool_btn("➕ 添加", self.add_opening))
        tb.addWidget(self._tool_btn("✏️ 编辑", self.edit_opening))
        tb.addWidget(self._tool_btn("🗑️ 删除", self.delete_opening, danger=True))
        tb.addStretch()
        grp.content_layout.addLayout(tb)

        self.opening_table = self._make_table(
            ["类型", "所属墙", "位置", "宽×高", "底高"],
            [60, 0, 60, 80, 50])
        self.opening_table.setMinimumHeight(80)
        self.opening_table.setMaximumHeight(200)
        self.opening_table.itemSelectionChanged.connect(
            self.on_opening_selected)
        grp.content_layout.addWidget(self.opening_table)

        self.body_layout.addWidget(grp)

    # ── 可燃物 ──────────────────────────────────────────
    def _build_combustible_section(self):
        grp = CollapsibleGroup("🪵 可燃物")

        tb = QHBoxLayout()
        tb.setSpacing(4)
        manage_btn = self._tool_btn("🎲 管理/生成…", self.open_combustible_dialog)
        manage_btn.setStyleSheet(
            "QPushButton{background:#a6e3a1;color:#1e1e2e;font-weight:bold;"
            "padding:4px 12px;border-radius:4px}"
            "QPushButton:hover{background:#94e2d5}")
        clear_btn = self._tool_btn("🗑️ 全部清除",
                                    self.clear_combustibles, danger=True)
        tb.addWidget(manage_btn)
        tb.addWidget(clear_btn)
        tb.addStretch()
        self.combustible_count_label = QLabel("共 0 个")
        self.combustible_count_label.setStyleSheet("color:#a6adc8;")
        tb.addWidget(self.combustible_count_label)
        grp.content_layout.addLayout(tb)

        # 只读预览表格
        self.combustible_table = self._make_table(
            ["名称", "X", "Y", "Z", "尺寸", "kW/m²"],
            [0, 50, 50, 50, 90, 55])
        self.combustible_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.combustible_table.setMinimumHeight(60)
        self.combustible_table.setMaximumHeight(180)
        grp.content_layout.addWidget(self.combustible_table)

        self.body_layout.addWidget(grp)

    # ── 热源 ────────────────────────────────────────────
    def _build_heat_section(self):
        grp = CollapsibleGroup("☀️ 外部热源")

        self.heat_enabled_check = QCheckBox("启用外部热源（面源辐射）")
        self.heat_enabled_check.stateChanged.connect(self.on_param_changed)
        self.heat_enabled_check.stateChanged.connect(self._toggle_heat)
        grp.content_layout.addWidget(self.heat_enabled_check)

        self.heat_options = QWidget()
        form = QGridLayout(self.heat_options)
        form.setContentsMargins(0, 2, 0, 0)
        form.setSpacing(4)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)

        form.addWidget(QLabel("方位:"), 0, 0)
        self.heat_location_combo = QComboBox()
        self.heat_location_combo.addItems(["north", "south", "east", "west"])
        self.heat_location_combo.currentTextChanged.connect(
            self.on_param_changed)
        form.addWidget(self.heat_location_combo, 0, 1)

        form.addWidget(QLabel("距离:"), 0, 2)
        self.heat_distance_spin = QDoubleSpinBox()
        self.heat_distance_spin.setRange(0.1, 50)
        self.heat_distance_spin.setValue(3.0)
        self.heat_distance_spin.setSuffix(" m")
        self.heat_distance_spin.valueChanged.connect(self.on_param_changed)
        form.addWidget(self.heat_distance_spin, 0, 3)

        form.addWidget(QLabel("热通量:"), 1, 0)
        self.heat_flux_spin = QDoubleSpinBox()
        self.heat_flux_spin.setRange(1, 1000000)
        self.heat_flux_spin.setValue(50)
        self.heat_flux_spin.setSuffix(" kW/m²")
        self.heat_flux_spin.valueChanged.connect(self.on_param_changed)
        form.addWidget(self.heat_flux_spin, 1, 1)

        self.heat_use_ramp_check = QCheckBox("时间曲线")
        self.heat_use_ramp_check.setChecked(True)
        self.heat_use_ramp_check.stateChanged.connect(self.on_param_changed)
        form.addWidget(self.heat_use_ramp_check, 1, 2)

        ramp_btn = QPushButton("编辑曲线…")
        ramp_btn.clicked.connect(self.edit_ramp)
        form.addWidget(ramp_btn, 1, 3)

        self.heat_options.setVisible(False)
        grp.content_layout.addWidget(self.heat_options)

        self.body_layout.addWidget(grp)

    # ── 模拟 + 输出 ─────────────────────────────────────
    def _build_simulation_section(self):
        grp = CollapsibleGroup("⚙️ 模拟 / 输出")
        g = QGridLayout()
        g.setSpacing(4)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)

        # 时间 & 边距
        g.addWidget(QLabel("时间:"), 0, 0)
        self.sim_time_spin = QDoubleSpinBox()
        self.sim_time_spin.setRange(1, 36000)
        self.sim_time_spin.setValue(60)
        self.sim_time_spin.setSuffix(" s")
        self.sim_time_spin.valueChanged.connect(self.on_param_changed)
        g.addWidget(self.sim_time_spin, 0, 1)

        g.addWidget(QLabel("边距:"), 0, 2)
        self.padding_spin = QDoubleSpinBox()
        self.padding_spin.setRange(0, 50)
        self.padding_spin.setValue(5)
        self.padding_spin.setSuffix(" m")
        self.padding_spin.valueChanged.connect(self.on_param_changed)
        g.addWidget(self.padding_spin, 0, 3)

        # 网格
        g.addWidget(QLabel("网格:"), 1, 0)
        mesh_row = QHBoxLayout()
        mesh_row.setSpacing(2)
        self.mesh_x_spin = QSpinBox(); self.mesh_x_spin.setRange(10, 500); self.mesh_x_spin.setValue(80)
        self.mesh_y_spin = QSpinBox(); self.mesh_y_spin.setRange(10, 500); self.mesh_y_spin.setValue(60)
        self.mesh_z_spin = QSpinBox(); self.mesh_z_spin.setRange(10, 500); self.mesh_z_spin.setValue(40)
        for s in (self.mesh_x_spin, self.mesh_y_spin, self.mesh_z_spin):
            s.valueChanged.connect(self.on_param_changed)
        mesh_row.addWidget(self.mesh_x_spin)
        mesh_row.addWidget(QLabel("×"))
        mesh_row.addWidget(self.mesh_y_spin)
        mesh_row.addWidget(QLabel("×"))
        mesh_row.addWidget(self.mesh_z_spin)
        g.addLayout(mesh_row, 1, 1, 1, 3)

        # 输出选项
        self.output_slices_check = QCheckBox("切片输出")
        self.output_slices_check.setChecked(True)
        self.output_slices_check.stateChanged.connect(self.on_param_changed)
        g.addWidget(self.output_slices_check, 2, 0, 1, 2)

        self.output_devices_check = QCheckBox("测量点输出")
        self.output_devices_check.setChecked(True)
        self.output_devices_check.stateChanged.connect(self.on_param_changed)
        g.addWidget(self.output_devices_check, 2, 2, 1, 2)

        grp.content_layout.addLayout(g)
        self.body_layout.addWidget(grp)

    # ── 辅助：工具栏按钮 ────────────────────────────────
    @staticmethod
    def _tool_btn(text: str, slot, danger=False) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(26)
        btn.clicked.connect(slot)
        if danger:
            btn.setStyleSheet(
                "QPushButton{color:#f38ba8;border:1px solid #45475a;"
                "padding:2px 8px;border-radius:3px}"
                "QPushButton:hover{background:#f38ba8;color:#1e1e2e}")
        else:
            btn.setStyleSheet(
                "QPushButton{color:#cdd6f4;border:1px solid #45475a;"
                "padding:2px 8px;border-radius:3px}"
                "QPushButton:hover{background:#45475a}")
        return btn

    # 表格样式
    def _make_table(self, columns: list, col_widths: list = None) -> QTableWidget:
        """创建统一风格的表格"""
        t = QTableWidget()
        t.setColumnCount(len(columns))
        t.setHorizontalHeaderLabels(columns)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setSelectionMode(QTableWidget.SingleSelection)
        t.verticalHeader().setDefaultSectionSize(24)
        t.verticalHeader().setVisible(False)

        # 关键：设置列宽模式
        header = t.horizontalHeader()
        if col_widths:
            for i, w in enumerate(col_widths):
                if w == 0:
                    header.setSectionResizeMode(i, QHeaderView.Stretch)
                else:
                    header.setSectionResizeMode(i, QHeaderView.Fixed)
                    t.setColumnWidth(i, w)
        else:
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            header.setStretchLastSection(True)

        # 交替行颜色 — 加大对比度
        t.setAlternatingRowColors(True)
        t.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                gridline-color: #45475a;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 2px 6px;
            }
            QTableWidget::item:alternate {
                background-color: #313244;
            }
            QTableWidget::item:selected {
                background-color: #585b70;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #45475a;
                color: #cdd6f4;
                padding: 3px 6px;
                border: none;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        t.setMouseTracking(True)
        return t
    
    def _table_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setToolTip(text)  # 悬停显示完整内容
        return item

    # ================================================================
    #                         墙体操作
    # ================================================================
    def update_wall_list(self):
        self.wall_table.setRowCount(len(self.model.walls))
        for i, w in enumerate(self.model.walls):
            is_ext = "外墙" if w.get("is_external") else "内墙"
            name = w.get("name", "")
            start = f"({w['x1']:.1f}, {w['y1']:.1f})"
            end = f"({w['x2']:.1f}, {w['y2']:.1f})"
            thick = f"{w.get('thickness', 0.24):.2f}"
            for col, txt in enumerate([is_ext, name, start, end, thick]):
                self.wall_table.setItem(i, col, self._table_item(txt))

    def add_wall(self):
        dialog = WallDialog(self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            data["is_external"] = False
            self.model.walls.append(data)
            self.update_wall_list()
            self.on_param_changed()

    def edit_wall(self):
        row = self.wall_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        wall = self.model.walls[row]
        dialog = WallDialog(self, wall, wall.get("is_external", False))
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            data["is_external"] = wall.get("is_external", False)
            self.model.walls[row] = data
            self.update_wall_list()
            self.on_param_changed()

    def delete_wall(self):
        row = self.wall_table.currentRow()
        if row < 0:
            return
        wall = self.model.walls[row]
        if wall.get("is_external", False):
            QMessageBox.warning(self, "提示", "外墙不可删除，请修改建筑尺寸")
            return
        if QMessageBox.question(
                self, "确认", f"删除墙体「{wall.get('name', '')}」？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        # 联动删除该墙上的开口
        self.model.openings = [
            o for o in self.model.openings if o["wall_index"] != row]
        for o in self.model.openings:
            if o["wall_index"] > row:
                o["wall_index"] -= 1
        del self.model.walls[row]
        self.update_wall_list()
        self.update_opening_list()
        self.on_param_changed()

    def on_wall_selected(self):
        self.wall_selected.emit(self.wall_table.currentRow())

    # ================================================================
    #                         开口操作
    # ================================================================
    def update_opening_list(self):
        self.opening_table.setRowCount(len(self.model.openings))
        for i, o in enumerate(self.model.openings):
            wall_idx = o["wall_index"]
            if wall_idx < len(self.model.walls):
                wall_name = self.model.walls[wall_idx].get(
                    "name", f"墙{wall_idx}")
            else:
                wall_name = "?"
            for col, txt in enumerate([
                o["type"].upper(),
                wall_name,
                f"{o['position']:.2f}",
                f"{o['width']:.1f}×{o['height']:.1f}",
                f"{o.get('z_bottom', 0):.1f}",
            ]):
                self.opening_table.setItem(i, col, self._table_item(txt))

    def add_opening(self):
        if not self.model.walls:
            QMessageBox.warning(self, "提示", "请先添加墙体")
            return
        dialog = OpeningDialog(self, walls=self.model.walls)
        if dialog.exec() == QDialog.Accepted:
            self.model.openings.append(dialog.get_data())
            self.update_opening_list()
            self.on_param_changed()

    def edit_opening(self):
        row = self.opening_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        dialog = OpeningDialog(
            self, self.model.openings[row], self.model.walls)
        if dialog.exec() == QDialog.Accepted:
            self.model.openings[row] = dialog.get_data()
            self.update_opening_list()
            self.on_param_changed()

    def delete_opening(self):
        row = self.opening_table.currentRow()
        if row < 0:
            return
        if QMessageBox.question(
                self, "确认", "删除该开口？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        del self.model.openings[row]
        self.update_opening_list()
        self.on_param_changed()

    def on_opening_selected(self):
        self.opening_selected.emit(self.opening_table.currentRow())

    # ================================================================
    #                         可燃物操作
    # ================================================================
    def open_combustible_dialog(self):
        # 先同步最新尺寸
        self.sync_model_from_ui()
        dlg = CombustibleDialog(
            manager=self.model.combustible_mgr,
            room_length=self.model.length,
            room_width=self.model.width,
            wall_thickness=self.model.wall_thickness,
            parent=self)
        dlg.data_changed.connect(self.update_combustible_list)
        dlg.data_changed.connect(self.on_param_changed)
        dlg.exec()
        self.update_combustible_list()
        self.on_param_changed()

    def clear_combustibles(self):
        if not self.model.combustible_mgr.items:
            return
        if QMessageBox.question(
                self, "确认", "清除所有可燃物？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.model.combustible_mgr.clear()
        self.update_combustible_list()
        self.on_param_changed()

    def update_combustible_list(self):
        items = self.model.combustible_mgr.items
        self.combustible_table.setRowCount(len(items))
        for i, cb in enumerate(items):
            for col, txt in enumerate([
                cb.name,
                f"{cb.x:.1f}",
                f"{cb.y:.1f}",
                f"{cb.z:.1f}",
                f"{cb.length}×{cb.width}×{cb.height}",
                f"{cb.hrrpua}",
            ]):
                self.combustible_table.setItem(i, col, self._table_item(txt))
        self.combustible_count_label.setText(f"共 {len(items)} 个")

    # ================================================================
    #                         热源 / 其他
    # ================================================================
    def _toggle_heat(self, state):
        self.heat_options.setVisible(state == 2)

    def edit_ramp(self):
        dialog = RampEditorDialog(
            self, self.model.heat_source.get("ramp_points", []))
        if dialog.exec() == QDialog.Accepted:
            self.model.heat_source["ramp_points"] = dialog.get_data()
            self.on_param_changed()

    # ================================================================
    #                         尺寸变更
    # ================================================================
    def on_dimension_changed(self):
        if self._syncing:
            return
        self.model.length = self.length_spin.value()
        self.model.width = self.width_spin.value()
        self.model.height = self.height_spin.value()
        self.model.wall_thickness = self.thickness_spin.value()
        self.model.update_external_walls()
        self.update_wall_list()
        self.on_param_changed()

    # ================================================================
    #                      模型 ↔ UI 同步
    # ================================================================
    def on_param_changed(self):
        if self._syncing:
            return
        self.sync_model_from_ui()
        self.parameters_changed.emit()

    def sync_model_from_ui(self):
        m = self.model
        m.chid = self.chid_edit.text()
        m.length = self.length_spin.value()
        m.width = self.width_spin.value()
        m.height = self.height_spin.value()
        m.wall_thickness = self.thickness_spin.value()

        m.materials["walls"] = self.wall_mat_combo.currentText()
        m.materials["floor"] = self.floor_mat_combo.currentText()
        m.materials["roof"] = self.roof_mat_combo.currentText()

        m.heat_source["enabled"] = self.heat_enabled_check.isChecked()
        m.heat_source["location"] = self.heat_location_combo.currentText()
        m.heat_source["distance"] = self.heat_distance_spin.value()
        m.heat_source["radiation_flux"] = self.heat_flux_spin.value()
        m.heat_source["use_ramp"] = self.heat_use_ramp_check.isChecked()

        m.simulation_time = self.sim_time_spin.value()
        m.domain["padding"] = self.padding_spin.value()
        m.domain["mesh_cells"] = [
            self.mesh_x_spin.value(),
            self.mesh_y_spin.value(),
            self.mesh_z_spin.value(),
        ]
        m.output["slices"] = self.output_slices_check.isChecked()
        m.output["devices"] = self.output_devices_check.isChecked()

    def sync_ui_from_model(self):
        self._syncing = True
        try:
            m = self.model
            self.chid_edit.setText(m.chid)
            self.length_spin.setValue(m.length)
            self.width_spin.setValue(m.width)
            self.height_spin.setValue(m.height)
            self.thickness_spin.setValue(m.wall_thickness)

            self.wall_mat_combo.setCurrentText(
                m.materials.get("walls", "CONCRETE"))
            self.floor_mat_combo.setCurrentText(
                m.materials.get("floor", "CONCRETE"))
            self.roof_mat_combo.setCurrentText(
                m.materials.get("roof", "CONCRETE"))

            self.heat_enabled_check.setChecked(
                m.heat_source.get("enabled", False))
            self.heat_location_combo.setCurrentText(
                m.heat_source.get("location", "north"))
            self.heat_distance_spin.setValue(
                m.heat_source.get("distance", 3.0))
            self.heat_flux_spin.setValue(
                m.heat_source.get("radiation_flux", 50.0))
            self.heat_use_ramp_check.setChecked(
                m.heat_source.get("use_ramp", True))

            self.sim_time_spin.setValue(m.simulation_time)
            self.padding_spin.setValue(m.domain.get("padding", 5.0))
            mesh = m.domain.get("mesh_cells", [80, 60, 40])
            self.mesh_x_spin.setValue(mesh[0])
            self.mesh_y_spin.setValue(mesh[1])
            self.mesh_z_spin.setValue(mesh[2])

            self.output_slices_check.setChecked(
                m.output.get("slices", True))
            self.output_devices_check.setChecked(
                m.output.get("devices", True))

            self.update_wall_list()
            self.update_opening_list()
            self.update_combustible_list()
            self._toggle_heat(
                2 if m.heat_source.get("enabled") else 0)
        finally:
            self._syncing = False

    def get_model(self) -> BuildingModel:
        self.sync_model_from_ui()
        return self.model

    def set_model(self, model: BuildingModel):
        self.model = model
        self.sync_ui_from_model()