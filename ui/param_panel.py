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

from models.building import BuildingModel, Story, FloorSlab
from models.materials import MATERIAL_LIBRARY
from ui.dialogs import (
    WallDialog, OpeningDialog, RampEditorDialog, CombustibleDialog, 
    BatchOpeningDialog, BatchWallDialog
)
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
    stories_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = BuildingModel()
        self._syncing = False
        self._current_story_index = 0
        self.setup_ui()

    # ── 当前编辑的层 ─────────────────────────────────
    def _current_story(self) -> Story:
        idx = self._current_story_index
        if 0 <= idx < len(self.model.stories):
            return self.model.stories[idx]
        return self.model.stories[0]

    # ================================================================
    #                          UI 构建
    # ================================================================
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部：项目名称
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
        self._build_story_section()
        self._build_wall_section()
        self._build_opening_section()
        self._build_combustible_section()
        self._build_heat_section()
        self._build_simulation_section()

        self.body_layout.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll)
    
    @staticmethod
    def _dark_btn(text, slot, danger=False):
        """深色背景、深色字体的按钮"""
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(26)
        btn.clicked.connect(slot)
        if danger:
            btn.setStyleSheet(
                "QPushButton{background:#f38ba8;color:#1e1e2e;font-weight:bold;"
                "padding:2px 8px;border-radius:3px}"
                "QPushButton:hover{background:#e06080;color:#1e1e2e}")
        else:
            btn.setStyleSheet(
                "QPushButton{background:#89b4fa;color:#1e1e2e;font-weight:bold;"
                "padding:2px 8px;border-radius:3px}"
                "QPushButton:hover{background:#74c7ec;color:#1e1e2e}")
        return btn

    # ── 几何 + 材料 ──────────────────────────────────
    def _build_geometry_section(self):
        grp = CollapsibleGroup("📐 几何 / 材料")
        g = QGridLayout()
        g.setSpacing(4)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        g.setColumnStretch(5, 1)

        def dim_spin(val, lo, hi, suffix=" m"):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setValue(val)
            s.setSuffix(suffix)
            s.setDecimals(2)
            s.setMaximumWidth(90)
            s.valueChanged.connect(self.on_dimension_changed)
            return s

        # 第0行：长 宽 墙厚
        g.addWidget(QLabel("长X:"), 0, 0)
        self.length_spin = dim_spin(20, 1, 10000)
        g.addWidget(self.length_spin, 0, 1)
        g.addWidget(QLabel("宽Y:"), 0, 2)
        self.width_spin = dim_spin(15, 1, 10000)
        g.addWidget(self.width_spin, 0, 3)
        g.addWidget(QLabel("墙厚:"), 0, 4)
        self.thickness_spin = dim_spin(0.25, 0.01, 2)
        g.addWidget(self.thickness_spin, 0, 5)

        # 第1行：材料
        materials = list(MATERIAL_LIBRARY.keys())
        def mat_combo():
            c = QComboBox()
            c.addItems(materials)
            c.currentTextChanged.connect(self.on_param_changed)
            c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            c.setMaximumWidth(90)
            return c

        g.addWidget(QLabel("墙:"), 1, 0)
        self.wall_mat_combo = mat_combo()
        g.addWidget(self.wall_mat_combo, 1, 1)
        g.addWidget(QLabel("底:"), 1, 2)
        self.floor_mat_combo = mat_combo()
        g.addWidget(self.floor_mat_combo, 1, 3)
        g.addWidget(QLabel("顶:"), 1, 4)
        self.roof_mat_combo = mat_combo()
        g.addWidget(self.roof_mat_combo, 1, 5)

        grp.content_layout.addLayout(g)
        self.body_layout.addWidget(grp)

    # ── 楼层管理 ─────────────────────────────
    def _build_story_section(self):
        grp = CollapsibleGroup("🏢 楼层管理")

        # 一行：当前层 + 层高
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        row1.addWidget(QLabel("当前层:"))
        self.story_combo = QComboBox()
        self.story_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.story_combo.currentIndexChanged.connect(self._on_story_switched)
        row1.addWidget(self.story_combo)
        row1.addWidget(QLabel("层高:"))
        self.story_height_spin = QDoubleSpinBox()
        self.story_height_spin.setRange(0.5, 50)
        self.story_height_spin.setDecimals(2)
        self.story_height_spin.setSuffix(" m")
        self.story_height_spin.setValue(3.0)
        self.story_height_spin.valueChanged.connect(self._on_story_height_changed)
        row1.addWidget(self.story_height_spin)
        grp.content_layout.addLayout(row1)

        # 按钮行
        row2 = QHBoxLayout()
        row2.setSpacing(4)
        row2.addWidget(self._dark_btn("➕ 添加层", self._add_story))
        row2.addWidget(self._dark_btn("📋 复制层", self._copy_story))
        row2.addWidget(self._dark_btn("🗑️ 删除层", self._delete_story, danger=True))
        row2.addStretch()
        grp.content_layout.addLayout(row2)

        self.body_layout.addWidget(grp)
        self._refresh_story_combo()

    def _refresh_story_combo(self):
        self._syncing = True
        try:
            self.story_combo.clear()
            for i, s in enumerate(self.model.stories):
                self.story_combo.addItem(f"{s.name}", i)
            idx = min(self._current_story_index, len(self.model.stories) - 1)
            idx = max(0, idx)
            self._current_story_index = idx
            self.story_combo.setCurrentIndex(idx)
        finally:
            self._syncing = False

    def _on_story_switched(self, index):
        if self._syncing or index < 0:
            return
        self._current_story_index = index
        self._syncing = True
        try:
            story = self._current_story()
            self.story_height_spin.setValue(story.height)
        finally:
            self._syncing = False
        self._refresh_story_tables()

    def _on_story_height_changed(self, val):
        if self._syncing:
            return
        story = self._current_story()
        story.height = val
        self.model.update_z_offsets()
        self.model.update_external_walls()
        self._refresh_story_combo()
        self.on_param_changed()

    def _add_story(self):
        self.model.add_story()
        self._current_story_index = len(self.model.stories) - 1
        self._refresh_story_combo()
        self._refresh_story_tables()
        self.stories_changed.emit()
        self.on_param_changed()

    def _copy_story(self):
        self.model.add_story(copy_from=self._current_story_index)
        self._current_story_index = len(self.model.stories) - 1
        self._refresh_story_combo()
        self._refresh_story_tables()
        self.stories_changed.emit()
        self.on_param_changed()

    def _delete_story(self):
        if len(self.model.stories) <= 1:
            QMessageBox.information(self, "提示", "至少保留一层")
            return
        name = self._current_story().name
        if QMessageBox.question(
                self, "确认", f"删除楼层「{name}」？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.model.remove_story(self._current_story_index)
        self.model.update_external_walls()
        self._current_story_index = min(
            self._current_story_index, len(self.model.stories) - 1)
        self._refresh_story_combo()
        self._refresh_story_tables()
        self.stories_changed.emit()
        self.on_param_changed()

    def _refresh_story_tables(self):
        """切换层后刷新墙体/开口/可燃物/楼板开洞表格"""
        self.update_wall_list()
        self.update_opening_list()
        self.update_combustible_list()

    # ── 墙体 ────────────────────────────────────────
    def _build_wall_section(self):
        grp = CollapsibleGroup("🧱 墙体")

        tb = QHBoxLayout()
        tb.setSpacing(4)
        tb.addWidget(self._dark_btn("📦 生成", self.batch_add_walls))
        tb.addWidget(self._dark_btn("✏️ 编辑", self.edit_wall))
        tb.addWidget(self._dark_btn("🗑️ 删除", self.delete_wall, danger=True))
        tb.addStretch()
        grp.content_layout.addLayout(tb)

        self.wall_table = self._make_table(
            ["类型", "名称", "起点", "终点", "厚度"],
            [40, 50, 90, 90, 50])
        self.wall_table.itemSelectionChanged.connect(self.on_wall_selected)
        grp.content_layout.addWidget(self.wall_table)
        self.body_layout.addWidget(grp)
    
    def batch_add_walls(self):
        dlg = BatchWallDialog(self, self.model)
        if dlg.exec() == QDialog.Accepted:
            story = self._current_story()
            for w in dlg.get_data():
                w["is_external"] = False
                w["height"] = story.height
                story.walls.append(w)
            self.update_wall_list()
            self.on_param_changed()

    # ── 开口 ────────────────────────────────────────
    def _build_opening_section(self):
        grp = CollapsibleGroup("🚪 开口（门/窗/楼梯口）")

        tb = QHBoxLayout()
        tb.setSpacing(4)
        tb.addWidget(self._dark_btn("📦 生成", self.batch_add_openings))
        tb.addWidget(self._dark_btn("✏️ 编辑", self.edit_opening))
        tb.addWidget(self._dark_btn("🗑️ 删除", self.delete_opening, danger=True))
        tb.addStretch()
        grp.content_layout.addLayout(tb)

        self.opening_table = self._make_table(
            ["类型", "所属", "位置/XY", "长×宽", "底高"],
            [50, 60, 80, 70, 45])
        self.opening_table.itemSelectionChanged.connect(self.on_opening_selected)
        grp.content_layout.addWidget(self.opening_table)
        self.body_layout.addWidget(grp)

    def batch_add_openings(self):
        story = self._current_story()
        if not story.walls:
            QMessageBox.warning(self, "提示", "请先有墙体")
            return
        dlg = BatchOpeningDialog(self, story.walls, self.model)
        if dlg.exec() == QDialog.Accepted:
            for item in dlg.get_data():
                if item.get("_kind") == "hole":
                    story.floor_slab.openings.append({
                        "name": item.get("name", "楼梯口"),
                        "x": item["x"], "y": item["y"],
                        "length": item["length"], "width": item["width"],
                    })
                else:
                    story.openings.append(item)
            self.update_opening_list()
            self.on_param_changed()

    # ── 可燃物 ──────────────────────────────────────
    def _build_combustible_section(self):
        grp = CollapsibleGroup("🪵 可燃物")

        tb = QHBoxLayout()
        tb.setSpacing(4)
        manage_btn = self._dark_btn("🎲 管理/生成…", self.open_combustible_dialog)
        manage_btn.setStyleSheet(
            "QPushButton{background:#a6e3a1;color:#1e1e2e;font-weight:bold;"
            "padding:4px 12px;border-radius:4px}"
            "QPushButton:hover{background:#94e2d5}")
        clear_btn = self._dark_btn("🗑️ 全部清除",
                                    self.clear_combustibles, danger=True)
        tb.addWidget(manage_btn)
        tb.addWidget(clear_btn)
        tb.addStretch()
        self.combustible_count_label = QLabel("共 0 个")
        self.combustible_count_label.setStyleSheet("color:#a6adc8;")
        tb.addWidget(self.combustible_count_label)
        grp.content_layout.addLayout(tb)

        self.combustible_table = self._make_table(
            ["名称", "X", "Y", "Z", "尺寸", "kW/m²"],
            [0, 50, 50, 50, 90, 55])
        self.combustible_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.combustible_table.setMinimumHeight(60)
        self.combustible_table.setMaximumHeight(180)
        grp.content_layout.addWidget(self.combustible_table)
        self.body_layout.addWidget(grp)

    # ── 热源 ────────────────────────────────────────
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
        self.heat_location_combo.currentTextChanged.connect(self.on_param_changed)
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

    # ── 模拟 + 输出 ─────────────────────────────────
    def _build_simulation_section(self):
        grp = CollapsibleGroup("⚙️ 模拟 / 输出")
        g = QGridLayout()
        g.setSpacing(4)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)

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

    # ── 辅助 ────────────────────────────────────────
    def _make_table(self, columns, col_widths=None):
        t = QTableWidget()
        t.setColumnCount(len(columns))
        t.setHorizontalHeaderLabels(columns)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setSelectionMode(QTableWidget.SingleSelection)
        t.verticalHeader().setDefaultSectionSize(24)
        t.verticalHeader().setVisible(False)
        header = t.horizontalHeader()
        # 所有列都 Stretch，按比例填满
        if col_widths:
            for i, w in enumerate(col_widths):
                if w == 0:
                    header.setSectionResizeMode(i, QHeaderView.Stretch)
                else:
                    header.setSectionResizeMode(i, QHeaderView.Stretch)
                    # 用 resizeSection 设初始比例参考
                    t.setColumnWidth(i, w)
        else:
            header.setSectionResizeMode(QHeaderView.Stretch)
        t.setAlternatingRowColors(True)
        t.setStyleSheet("""
            QTableWidget { background-color:#1e1e2e; color:#cdd6f4; gridline-color:#45475a; font-size:12px; }
            QTableWidget::item { padding:2px 6px; }
            QTableWidget::item:alternate { background-color:#313244; }
            QTableWidget::item:selected { background-color:#585b70; color:#ffffff; }
            QHeaderView::section { background-color:#45475a; color:#cdd6f4; padding:3px 6px; border:none; font-weight:bold; font-size:11px; }
        """)
        t.setMouseTracking(True)
        t.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return t
    
    def _auto_table_height(self, table, min_rows=2, max_rows=8):
        """根据行数自动调整表格高度"""
        row_h = table.verticalHeader().defaultSectionSize()
        header_h = table.horizontalHeader().height() if table.horizontalHeader().isVisible() else 0
        n = max(min_rows, min(table.rowCount(), max_rows))
        table.setFixedHeight(header_h + row_h * n + 4)

    def _table_item(self, text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setToolTip(text)
        return item

    # ================================================================
    #                         墙体操作
    # ================================================================
    def update_wall_list(self):
        story = self._current_story()
        self.wall_table.setRowCount(len(story.walls))
        for i, w in enumerate(story.walls):
            is_ext = "外墙" if w.get("is_external") else "内墙"
            name = w.get("name", "")
            start = f"({w['x1']:.1f}, {w['y1']:.1f})"
            end = f"({w['x2']:.1f}, {w['y2']:.1f})"
            thick = f"{w.get('thickness', 0.24):.2f}"
            for col, txt in enumerate([is_ext, name, start, end, thick]):
                self.wall_table.setItem(i, col, self._table_item(txt))
        self._auto_table_height(self.wall_table)

    def add_wall(self):
        dialog = WallDialog(self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            data["is_external"] = False
            story = self._current_story()
            story.walls.append(data)
            self.update_wall_list()
            self.on_param_changed()

    def edit_wall(self):
        row = self.wall_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        story = self._current_story()
        wall = story.walls[row]
        dialog = WallDialog(self, wall, wall.get("is_external", False))
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            data["is_external"] = wall.get("is_external", False)
            story.walls[row] = data
            self.update_wall_list()
            self.on_param_changed()

    def delete_wall(self):
        row = self.wall_table.currentRow()
        if row < 0:
            return
        story = self._current_story()
        wall = story.walls[row]
        if wall.get("is_external", False):
            QMessageBox.warning(self, "提示", "外墙不可删除，请修改建筑尺寸")
            return
        if QMessageBox.question(
                self, "确认", f"删除墙体「{wall.get('name', '')}」？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        story.openings = [
            o for o in story.openings if o["wall_index"] != row]
        for o in story.openings:
            if o["wall_index"] > row:
                o["wall_index"] -= 1
        del story.walls[row]
        self.update_wall_list()
        self.update_opening_list()
        self.on_param_changed()

    def on_wall_selected(self):
        self.wall_selected.emit(self.wall_table.currentRow())

    # ================================================================
    #                         开口操作
    # ================================================================
    def update_opening_list(self):
        story = self._current_story()
        # 合并：门窗 + 楼板开洞
        rows = []
        # 门窗
        for o in story.openings:
            wall_idx = o["wall_index"]
            if wall_idx < len(story.walls):
                wall_name = story.walls[wall_idx].get("name", f"墙{wall_idx}")
            else:
                wall_name = "?"
            rows.append((
                o["type"].upper(),
                wall_name,
                f"{o['position']:.2f}",
                f"{o['width']:.1f}×{o['height']:.1f}",
                f"{o.get('z_bottom', 0):.1f}",
                "opening",
            ))
        # 楼板开洞
        for h in story.floor_slab.openings:
            rows.append((
                "楼梯口",
                "楼板",
                f"({h['x']:.1f},{h['y']:.1f})",
                f"{h['length']:.1f}×{h['width']:.1f}",
                "-",
                "hole",
            ))

        self._opening_rows = rows  # 缓存用于编辑/删除
        self.opening_table.setRowCount(len(rows))
        for i, (typ, parent, pos, size, zb, _) in enumerate(rows):
            for col, txt in enumerate([typ, parent, pos, size, zb]):
                self.opening_table.setItem(i, col, self._table_item(txt))
        self._auto_table_height(self.wall_table)

    def edit_opening(self):
        row = self.opening_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        if not hasattr(self, '_opening_rows') or row >= len(self._opening_rows):
            return
        story = self._current_story()
        kind = self._opening_rows[row][5]

        if kind == "opening":
            # 门窗：计算在openings中的真实索引
            oi = self._get_opening_real_index(row)
            dialog = OpeningDialog(self, story.openings[oi], story.walls)
            if dialog.exec() == QDialog.Accepted:
                story.openings[oi] = dialog.get_data()
                self.update_opening_list()
                self.on_param_changed()
        else:
            # 楼板开洞
            hi = self._get_hole_real_index(row)
            from ui.dialogs import FloorSlabHoleDialog
            dlg = FloorSlabHoleDialog(
                self, self.model.length, self.model.width,
                story.floor_slab.openings[hi])
            if dlg.exec() == QDialog.Accepted:
                story.floor_slab.openings[hi] = dlg.get_data()
                self.update_opening_list()
                self.on_param_changed()

    def delete_opening(self):
        row = self.opening_table.currentRow()
        if row < 0:
            return
        if not hasattr(self, '_opening_rows') or row >= len(self._opening_rows):
            return
        if QMessageBox.question(
                self, "确认", "删除该项？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        story = self._current_story()
        kind = self._opening_rows[row][5]
        if kind == "opening":
            oi = self._get_opening_real_index(row)
            del story.openings[oi]
        else:
            hi = self._get_hole_real_index(row)
            del story.floor_slab.openings[hi]
        self.update_opening_list()
        self.on_param_changed()

    def _get_opening_real_index(self, table_row):
        """表格行号 → openings列表真实索引"""
        count = 0
        for i in range(table_row + 1):
            if self._opening_rows[i][5] == "opening":
                if i == table_row:
                    return count
                count += 1
        return 0

    def _get_hole_real_index(self, table_row):
        """表格行号 → floor_slab.openings真实索引"""
        count = 0
        for i in range(table_row + 1):
            if self._opening_rows[i][5] == "hole":
                if i == table_row:
                    return count
                count += 1
        return 0

    def on_opening_selected(self):
        self.opening_selected.emit(self.opening_table.currentRow())

    # ================================================================
    #                         可燃物操作
    # ================================================================
    def open_combustible_dialog(self):
        self.sync_model_from_ui()
        story = self._current_story()
        dlg = CombustibleDialog(
            manager=story.combustibles,
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
        story = self._current_story()
        if not story.combustibles.items:
            return
        if QMessageBox.question(
                self, "确认", f"清除 {story.name} 所有可燃物？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        story.combustibles.clear()
        self.update_combustible_list()
        self.on_param_changed()

    def update_combustible_list(self):
        story = self._current_story()
        items = story.combustibles.items
        self.combustible_table.setRowCount(len(items))
        for i, cb in enumerate(items):
            for col, txt in enumerate([
                cb.name,
                f"{cb.x:.1f}", f"{cb.y:.1f}", f"{cb.z:.1f}",
                f"{cb.length}×{cb.width}×{cb.height}",
                f"{cb.hrrpua}",
            ]):
                self.combustible_table.setItem(i, col, self._table_item(txt))
        self.combustible_count_label.setText(f"共 {len(items)} 个")
        self._auto_table_height(self.wall_table)

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
            self.thickness_spin.setValue(m.wall_thickness)

            self.wall_mat_combo.setCurrentText(m.materials.get("walls", "CONCRETE"))
            self.floor_mat_combo.setCurrentText(m.materials.get("floor", "CONCRETE"))
            self.roof_mat_combo.setCurrentText(m.materials.get("roof", "CONCRETE"))

            self.heat_enabled_check.setChecked(m.heat_source.get("enabled", False))
            self.heat_location_combo.setCurrentText(m.heat_source.get("location", "north"))
            self.heat_distance_spin.setValue(m.heat_source.get("distance", 3.0))
            self.heat_flux_spin.setValue(m.heat_source.get("radiation_flux", 50.0))
            self.heat_use_ramp_check.setChecked(m.heat_source.get("use_ramp", True))

            self.sim_time_spin.setValue(m.simulation_time)
            self.padding_spin.setValue(m.domain.get("padding", 5.0))
            mesh = m.domain.get("mesh_cells", [80, 60, 40])
            self.mesh_x_spin.setValue(mesh[0])
            self.mesh_y_spin.setValue(mesh[1])
            self.mesh_z_spin.setValue(mesh[2])

            self.output_slices_check.setChecked(m.output.get("slices", True))
            self.output_devices_check.setChecked(m.output.get("devices", True))

            # 楼层
            self._current_story_index = 0
            self._refresh_story_combo()
            self.story_height_spin.setValue(self._current_story().height)

            self._refresh_story_tables()
            self._toggle_heat(2 if m.heat_source.get("enabled") else 0)
        finally:
            self._syncing = False

    def get_model(self):
        self.sync_model_from_ui()
        return self.model

    def set_model(self, model):
        self.model = model
        self.sync_ui_from_model()