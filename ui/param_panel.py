#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : param_panel.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 2.0
@Desc  : Parameter configuration panel for building model (new schema)
'''
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QGroupBox, QGridLayout,
    QLineEdit, QDoubleSpinBox, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QHBoxLayout, QFormLayout, QCheckBox,
    QMessageBox, QDialog, QSpinBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal

from models.building import BuildingGroup, Building, Story, Opening, FireCompartment, Roof
from models.materials import MATERIAL_LIBRARY
from ui.styles import CollapsibleGroup
from ui.dialogs import (
    OpeningDialog, RampEditorDialog, CombustibleDialog,
    BatchOpeningDialog, WALL_LABELS
)


def _default_building_group():
    """Create a minimal BuildingGroup with one Building / one Story."""
    story = Story(name="1F", height=3.0)
    building = Building(
        name="building", cn_name="building",
        boundary=[0, 20, 0, 15],
        wall_thickness=0.24,
        height=3.0,
        stories=[story],
    )
    building.update_z_offsets()
    return BuildingGroup(buildings=[building])


class ParameterPanel(QWidget):
    """参数配置面板"""

    parameters_changed = Signal()
    opening_selected = Signal(int)
    stories_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = _default_building_group()
        self._syncing = False
        self._readonly = False
        self._current_building_index = 0
        self._current_story_index = 0
        self.setup_ui()

    # ── helpers to navigate the model hierarchy ───────────
    def _current_building(self) -> Building:
        idx = self._current_building_index
        if 0 <= idx < len(self.model.buildings):
            return self.model.buildings[idx]
        return self.model.buildings[0]

    def _current_story(self) -> Story:
        b = self._current_building()
        idx = self._current_story_index
        if 0 <= idx < len(b.stories):
            return b.stories[idx]
        return b.stories[0]

    # ================================================================
    #                          UI construction
    # ================================================================
    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # top: project name
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

        # scroll area
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
        self._build_opening_section()
        self._build_combustible_section()

        self.body_layout.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll)

    @staticmethod
    def _dark_btn(text, slot, danger=False):
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

    # ── geometry / material ───────────────────────────────
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

        g.addWidget(QLabel("长X:"), 0, 0)
        self.length_spin = dim_spin(20, 1, 10000)
        g.addWidget(self.length_spin, 0, 1)
        g.addWidget(QLabel("宽Y:"), 0, 2)
        self.width_spin = dim_spin(15, 1, 10000)
        g.addWidget(self.width_spin, 0, 3)
        g.addWidget(QLabel("墙厚:"), 0, 4)
        self.thickness_spin = dim_spin(0.25, 0.01, 2)
        g.addWidget(self.thickness_spin, 0, 5)

        # materials
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

    # ── story management ──────────────────────────────────
    def _build_story_section(self):
        grp = CollapsibleGroup("🏢 楼层管理")

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

        row2 = QHBoxLayout()
        row2.setSpacing(4)
        self._add_story_btn = self._dark_btn("➕ 添加层", self._add_story)
        self._copy_story_btn = self._dark_btn("📋 复制层", self._copy_story)
        self._del_story_btn = self._dark_btn("🗑️ 删除层", self._delete_story, danger=True)
        row2.addWidget(self._add_story_btn)
        row2.addWidget(self._copy_story_btn)
        row2.addWidget(self._del_story_btn)
        row2.addStretch()
        grp.content_layout.addLayout(row2)

        self.body_layout.addWidget(grp)
        self._refresh_story_combo()

    def _refresh_story_combo(self):
        self._syncing = True
        try:
            b = self._current_building()
            self.story_combo.clear()
            for i, s in enumerate(b.stories):
                self.story_combo.addItem(f"{s.name}", i)
            idx = min(self._current_story_index, len(b.stories) - 1)
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
        self._current_building().update_z_offsets()
        self._refresh_story_combo()
        self.on_param_changed()

    def _add_story(self):
        if self._readonly:
            return
        b = self._current_building()
        n = len(b.stories) + 1
        new_story = Story(name=f"{n}F", height=3.0)
        b.stories.append(new_story)
        b.update_z_offsets()
        self._current_story_index = len(b.stories) - 1
        self._refresh_story_combo()
        self._refresh_story_tables()
        self.stories_changed.emit()
        self.on_param_changed()

    def _copy_story(self):
        if self._readonly:
            return
        b = self._current_building()
        src = self._current_story()
        new_story = Story.from_dict(src.to_dict())
        n = len(b.stories) + 1
        new_story.name = f"{n}F"
        b.stories.append(new_story)
        b.update_z_offsets()
        self._current_story_index = len(b.stories) - 1
        self._refresh_story_combo()
        self._refresh_story_tables()
        self.stories_changed.emit()
        self.on_param_changed()

    def _delete_story(self):
        if self._readonly:
            return
        b = self._current_building()
        if len(b.stories) <= 1:
            QMessageBox.information(self, "提示", "至少保留一层")
            return
        name = self._current_story().name
        if QMessageBox.question(
                self, "确认", f"删除楼层「{name}」？",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        del b.stories[self._current_story_index]
        b.update_z_offsets()
        self._current_story_index = min(
            self._current_story_index, len(b.stories) - 1)
        self._refresh_story_combo()
        self._refresh_story_tables()
        self.stories_changed.emit()
        self.on_param_changed()

    def _refresh_story_tables(self):
        """Refresh openings / combustibles tables after story switch."""
        self.update_opening_list()
        self.update_combustible_list()

    # ── openings ─────────────────────────────────────────
    def _build_opening_section(self):
        grp = CollapsibleGroup("🚪 开口（门/窗/屋顶开口）")

        tb = QHBoxLayout()
        tb.setSpacing(4)
        self._batch_opening_btn = self._dark_btn("📦 生成", self.batch_add_openings)
        self._edit_opening_btn = self._dark_btn("✏️ 编辑", self.edit_opening)
        self._del_opening_btn = self._dark_btn("🗑️ 删除", self.delete_opening, danger=True)
        tb.addWidget(self._batch_opening_btn)
        tb.addWidget(self._edit_opening_btn)
        tb.addWidget(self._del_opening_btn)
        tb.addStretch()
        grp.content_layout.addLayout(tb)

        self.opening_table = self._make_table(
            ["类型", "所属墙", "偏移(m)", "宽x高", "h_offset"],
            [50, 60, 70, 70, 50])
        self.opening_table.itemSelectionChanged.connect(self.on_opening_selected)
        grp.content_layout.addWidget(self.opening_table)
        self.body_layout.addWidget(grp)

    def batch_add_openings(self):
        if self._readonly:
            return
        b = self._current_building()
        story = self._current_story()
        dlg = BatchOpeningDialog(self, walls=None, model=b)
        if dlg.exec() == QDialog.Accepted:
            for item in dlg.get_data():
                if isinstance(item, dict) and item.get("_kind") == "hole":
                    story.roof.openings.append({
                        "name": item.get("name", "屋顶开口"),
                        "boundary": item.get("boundary", [0, 2, 0, 2]),
                    })
                elif isinstance(item, Opening):
                    story.openings.append(item)
                elif isinstance(item, dict):
                    story.openings.append(Opening.from_dict(item))
            self.update_opening_list()
            self.on_param_changed()

    # ── combustibles ──────────────────────────────────────
    def _build_combustible_section(self):
        grp = CollapsibleGroup("🪵 可燃物")

        tb = QHBoxLayout()
        tb.setSpacing(4)
        manage_btn = self._dark_btn("🎲 管理/生成…", self.open_combustible_dialog)
        manage_btn.setStyleSheet(
            "QPushButton{background:#a6e3a1;color:#1e1e2e;font-weight:bold;"
            "padding:4px 12px;border-radius:4px}"
            "QPushButton:hover{background:#94e2d5}")
        self._clear_comb_btn = self._dark_btn("🗑️ 全部清除",
                                    self.clear_combustibles, danger=True)
        tb.addWidget(manage_btn)
        tb.addWidget(self._clear_comb_btn)
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

    # ── table helpers ─────────────────────────────────────
    def _make_table(self, columns, col_widths=None):
        t = QTableWidget()
        t.setColumnCount(len(columns))
        t.setHorizontalHeaderLabels(columns)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setSelectionMode(QTableWidget.SingleSelection)
        t.verticalHeader().setDefaultSectionSize(24)
        t.verticalHeader().setVisible(False)
        header = t.horizontalHeader()
        if col_widths:
            for i, w in enumerate(col_widths):
                if w == 0:
                    header.setSectionResizeMode(i, QHeaderView.Stretch)
                else:
                    header.setSectionResizeMode(i, QHeaderView.Stretch)
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
    #                         opening operations
    # ================================================================
    def update_opening_list(self):
        story = self._current_story()
        # Merge: wall openings + roof openings
        rows = []
        # Wall openings (Opening objects)
        for o in story.openings:
            wall_label = WALL_LABELS.get(o.wall, o.wall)
            bd = o.boundary
            rows.append((
                o.type.upper(),
                wall_label,
                f"{bd[0]:.2f}",
                f"{bd[1]:.1f}x{bd[3]:.1f}",
                f"{bd[2]:.1f}",
                "opening",
            ))
        # Roof openings
        for h in story.roof.openings:
            bd = h.get("boundary", [0, 0, 0, 0])
            rows.append((
                "屋顶开口",
                "屋顶",
                f"({bd[0]:.1f},{bd[2]:.1f})",
                f"{bd[1]:.1f}x{bd[3]:.1f}",
                "-",
                "hole",
            ))

        self._opening_rows = rows
        self.opening_table.setRowCount(len(rows))
        for i, (typ, parent, pos, size, zb, _) in enumerate(rows):
            for col, txt in enumerate([typ, parent, pos, size, zb]):
                self.opening_table.setItem(i, col, self._table_item(txt))
        self._auto_table_height(self.opening_table)

    def edit_opening(self):
        if self._readonly:
            return
        row = self.opening_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中一行")
            return
        if not hasattr(self, '_opening_rows') or row >= len(self._opening_rows):
            return
        story = self._current_story()
        kind = self._opening_rows[row][5]

        if kind == "opening":
            oi = self._get_opening_real_index(row)
            dialog = OpeningDialog(self, story.openings[oi])
            if dialog.exec() == QDialog.Accepted:
                story.openings[oi] = dialog.get_data()
                self.update_opening_list()
                self.on_param_changed()
        else:
            # Roof opening
            hi = self._get_hole_real_index(row)
            b = self._current_building()
            from ui.dialogs import RoofOpeningDialog
            dlg = RoofOpeningDialog(
                self, b.length, b.width,
                story.roof.openings[hi])
            if dlg.exec() == QDialog.Accepted:
                story.roof.openings[hi] = dlg.get_data()
                self.update_opening_list()
                self.on_param_changed()

    def delete_opening(self):
        if self._readonly:
            return
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
            del story.roof.openings[hi]
        self.update_opening_list()
        self.on_param_changed()

    def _get_opening_real_index(self, table_row):
        count = 0
        for i in range(table_row + 1):
            if self._opening_rows[i][5] == "opening":
                if i == table_row:
                    return count
                count += 1
        return 0

    def _get_hole_real_index(self, table_row):
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
    #                         combustible operations
    # ================================================================
    def open_combustible_dialog(self):
        if self._readonly:
            return
        self.sync_model_from_ui()
        b = self._current_building()
        story = self._current_story()
        # story.combustibles may not exist in new schema -- use FC combustibles
        # For backward compat, check if story has a .combustibles attribute
        if hasattr(story, 'combustibles'):
            dlg = CombustibleDialog(
                manager=story.combustibles,
                room_length=b.length,
                room_width=b.width,
                wall_thickness=b.wall_thickness,
                parent=self)
            dlg.data_changed.connect(self.update_combustible_list)
            dlg.data_changed.connect(self.on_param_changed)
            dlg.exec()
            self.update_combustible_list()
            self.on_param_changed()

    def clear_combustibles(self):
        if self._readonly:
            return
        story = self._current_story()
        if not hasattr(story, 'combustibles') or not story.combustibles.items:
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
        if not hasattr(story, 'combustibles'):
            self.combustible_table.setRowCount(0)
            self.combustible_count_label.setText("共 0 个")
            return
        items = story.combustibles.items
        self.combustible_table.setRowCount(len(items))
        for i, cb in enumerate(items):
            for col, txt in enumerate([
                cb.name,
                f"{cb.x:.1f}", f"{cb.y:.1f}", f"{cb.z:.1f}",
                f"{cb.length}x{cb.width}x{cb.height}",
                f"{cb.hrrpua}",
            ]):
                self.combustible_table.setItem(i, col, self._table_item(txt))
        self.combustible_count_label.setText(f"共 {len(items)} 个")
        self._auto_table_height(self.combustible_table)

    # ================================================================
    #                         dimension changes
    # ================================================================
    def on_dimension_changed(self):
        if self._syncing:
            return
        b = self._current_building()
        b.boundary[1] = self.length_spin.value()
        b.boundary[3] = self.width_spin.value()
        b.wall_thickness = self.thickness_spin.value()
        self.on_param_changed()

    # ================================================================
    #                      model <-> UI sync
    # ================================================================
    def on_param_changed(self):
        if self._syncing:
            return
        self.sync_model_from_ui()
        self.parameters_changed.emit()

    def sync_model_from_ui(self):
        b = self._current_building()
        b.name = self.chid_edit.text()
        b.cn_name = self.chid_edit.text()
        b.boundary[1] = self.length_spin.value()
        b.boundary[3] = self.width_spin.value()
        b.wall_thickness = self.thickness_spin.value()

    def sync_ui_from_model(self):
        self._syncing = True
        try:
            b = self._current_building()
            self.chid_edit.setText(b.name or b.cn_name or "building")
            self.length_spin.setValue(b.length)
            self.width_spin.setValue(b.width)
            self.thickness_spin.setValue(b.wall_thickness)

            # stories
            self._current_story_index = 0
            self._refresh_story_combo()
            if b.stories:
                self.story_height_spin.setValue(self._current_story().height)

            self._refresh_story_tables()
        finally:
            self._syncing = False

    def get_model(self):
        self.sync_model_from_ui()
        return self.model

    def set_model(self, model):
        """Accept a BuildingGroup (or legacy-compatible object)."""
        if isinstance(model, BuildingGroup):
            self.model = model
        elif isinstance(model, Building):
            self.model = BuildingGroup(buildings=[model])
        else:
            # Legacy fallback: try to wrap
            self.model = BuildingGroup(buildings=[model])
        self._current_building_index = 0
        self._current_story_index = 0
        self.sync_ui_from_model()

    # ── read-only mode ────────────────────────────────────
    def set_readonly(self, readonly: bool):
        self._readonly = readonly
        for btn in [
            self._add_story_btn, self._copy_story_btn, self._del_story_btn,
            self._batch_opening_btn, self._edit_opening_btn, self._del_opening_btn,
            self._clear_comb_btn,
        ]:
            btn.setEnabled(not readonly)
        self.length_spin.setReadOnly(readonly)
        self.width_spin.setReadOnly(readonly)
        self.thickness_spin.setReadOnly(readonly)
        self.story_height_spin.setReadOnly(readonly)
        self.chid_edit.setReadOnly(readonly)
