#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File  : facility_panel.py
@Author: Lubber
@Date  : 2026-03-19
@Version : 3.0
@Desc  : Panel with inline parameter editing, facility selection, and scene management.
         Updated for new FacilityManager API with equivalent/specialized model types.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QHBoxLayout,
    QMessageBox,
    QDialog,
    QDoubleSpinBox,
    QSpinBox,
    QComboBox,
    QGridLayout,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QBrush
from models.facility import FacilityManager
from models.building import BuildingGroup
from ui.styles import CollapsibleGroup, apply_button_variant

# Alias for backwards compatibility within this file
CollapsibleSection = CollapsibleGroup


class FacilityListPanel(QWidget):
    """Left sidebar: facility tree + inline params + scene list."""

    facility_selected = Signal(dict)  # replace entire model (category generation)
    building_added = Signal(object)  # append one Building object
    scene_building_selected = Signal(int)  # select building for editing

    def __init__(self, parent=None):
        super().__init__(parent)
        self.facility_manager = FacilityManager()
        self.selected_facility_data = None
        self._params = None
        self._syncing = False
        font = self.font()
        font.setPointSize(font.pointSize() + 2)
        self.setFont(font)
        self.setStyleSheet(
            "QLabel{font-size:15px;} QGroupBox{font-size:15px;} "
            "QSpinBox{font-size:15px;} QDoubleSpinBox{font-size:15px;} "
            "QComboBox{font-size:15px;} QPushButton{font-size:15px;} "
            "QTreeWidget{font-size:15px;} QTableWidget{font-size:15px;}"
        )
        self.setup_ui()
        self._populate_tree()

    # ==================================================
    # UI Setup
    # ==================================================

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- 1. Facility tree --
        sec_tree = CollapsibleSection("设施类型")
        self.facility_tree = QTreeWidget()
        self.facility_tree.setHeaderHidden(True)
        self.facility_tree.setMinimumHeight(400)
        self.facility_tree.setStyleSheet(
            "QTreeWidget{font-size:13px;}"
            "QTreeWidget::item{padding:3px 0;min-height:22px;}"
        )
        self.facility_tree.itemClicked.connect(self._on_tree_clicked)
        sec_tree.content_layout.addWidget(self.facility_tree)

        # Description label
        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        self.desc_label.setMinimumHeight(42)
        self.desc_label.setStyleSheet("color:#a6adc8; font-size:12px;")
        sec_tree.content_layout.addWidget(self.desc_label)
        outer.addWidget(sec_tree)

        sec_bld = CollapsibleSection("建筑参数")
        g = QGridLayout()
        g.setSpacing(3)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)

        def _lbl(text):
            lbl = QLabel(text)
            lbl.setFixedWidth(lbl.sizeHint().width())
            return lbl

        def _range_label(width=None):
            lbl = QLabel("")
            lbl.setStyleSheet("color:#6c7086; font-size:11px;")
            if width:
                lbl.setMinimumWidth(width)
            return lbl

        # Size class combo (大/中/小) for equivalent models
        self.size_combo = QComboBox()
        self.size_combo.addItems(["小", "中", "大"])
        self.size_combo.setEnabled(False)
        self.size_combo.currentTextChanged.connect(self._on_size_class_changed)
        r = 0
        g.addWidget(_lbl("规模:"), r, 0)
        g.addWidget(self.size_combo, r, 1)
        self.rng_size = _range_label(width=200)
        g.addWidget(self.rng_size, r, 2, 1, 4)

        sec_bld.content_layout.addLayout(g)

        # Hidden stories widget: read-only display for specialized buildings.
        self.sp_N = QSpinBox()
        self.sp_N.setRange(1, 30)
        self.sp_N.setValue(1)
        self.sp_N.setMinimumHeight(28)
        self.sp_N.setStyleSheet("font-size:13px;")
        self.sp_N.setVisible(False)
        self.rng_N = _range_label(width=80)
        self.rng_N.setVisible(False)

        def _hidden_dspin() -> QDoubleSpinBox:
            sb = QDoubleSpinBox()
            sb.setRange(0, 99999)
            sb.setDecimals(1)
            sb.setVisible(False)
            return sb

        def _hidden_label() -> QLabel:
            lbl = QLabel("")
            lbl.setVisible(False)
            return lbl

        self._hidden_length = _hidden_dspin()
        self._hidden_width = _hidden_dspin()
        self._hidden_height = _hidden_dspin()
        self._rng_length = _hidden_label()
        self._rng_width = _hidden_label()
        self._rng_height = _hidden_label()

        self._param_spinboxes = {
            "length": self._hidden_length,
            "width": self._hidden_width,
            "height": self._hidden_height,
            "stories": self.sp_N,
        }
        self._range_labels = {
            "length": self._rng_length,
            "width": self._rng_width,
            "height": self._rng_height,
            "stories": self.rng_N,
        }
        self._param_ranges = {}  # raw [min, max, ...] per field
        self._param_scale_values = {}  # field -> (small, medium, large)

        outer.addWidget(sec_bld)

        # -- 7. Combustible button --
        self.combustible_btn = QPushButton("可燃物管理…")
        self.combustible_btn.setFixedHeight(34)
        apply_button_variant(self.combustible_btn, "primary")
        self.combustible_btn.setEnabled(False)
        self.combustible_btn.clicked.connect(self._on_combustible_clicked)
        outer.addWidget(self.combustible_btn)

        # -- Action buttons --
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self.generate_btn = QPushButton("生成建筑")
        self.generate_btn.setEnabled(False)
        self.generate_btn.setFixedHeight(34)
        apply_button_variant(self.generate_btn, "success")
        self.generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self.generate_btn)

        self.generate_category_btn = QPushButton("生成设施全部建筑")
        self.generate_category_btn.setEnabled(False)
        self.generate_category_btn.setFixedHeight(34)
        apply_button_variant(self.generate_category_btn, "primary")
        self.generate_category_btn.clicked.connect(self._on_generate_category)
        btn_layout.addWidget(self.generate_category_btn)

        outer.addLayout(btn_layout)

        # -- 8. Scene object list --
        sec_scene = CollapsibleSection("场景目标列表")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        self.scene_table = QTableWidget()
        self.scene_table.setColumnCount(3)
        self.scene_table.setHorizontalHeaderLabels(["名称", "尺寸", "位置"])
        self.scene_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.scene_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.scene_table.setColumnWidth(2, 160)  # position column fixed width
        self.scene_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.scene_table.setSelectionMode(QTableWidget.SingleSelection)
        self.scene_table.setMinimumHeight(100)
        self.scene_table.setStyleSheet(
            "QTableWidget{font-size:12px;}QTableWidget::item{padding:2px 0;}"
        )
        self.scene_table.cellClicked.connect(self._on_scene_table_clicked)
        scroll.setWidget(self.scene_table)
        sec_scene.content_layout.addWidget(scroll)


        outer.addWidget(sec_scene)

    # ==================================================
    # Facility tree
    # ==================================================

    def _populate_tree(self):
        """Populate the facility tree with two root groups: equivalent and specialized."""
        self.facility_tree.clear()

        # Create two root-level group nodes
        equiv_root = QTreeWidgetItem(["\u7b49\u6548\u6a21\u578b"])
        spec_root = QTreeWidgetItem(["\u7279\u5f02\u6a21\u578b"])

        # Style root nodes: bold font and distinct color
        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(bold_font.pointSize() + 1)
        equiv_color = QBrush(QColor("#a6e3a1"))  # green
        spec_color = QBrush(QColor("#f9e2af"))  # yellow

        for root_item, color in [(equiv_root, equiv_color), (spec_root, spec_color)]:
            root_item.setFont(0, bold_font)
            root_item.setForeground(0, color)
            # Root group nodes carry no actionable data
            root_item.setData(0, Qt.UserRole, {"node": "group"})

        for name, data in self.facility_manager.facilities.items():
            ftype = data["type"]  # "equivalent" / "specialized"
            parent_root = equiv_root if ftype == "equivalent" else spec_root

            # Facility-level node
            category_item = QTreeWidgetItem([data["cn_name"]])
            category_item.setData(
                0, Qt.UserRole, {"facility": name, "type": ftype, "node": "facility"}
            )

            # Building-level leaf nodes
            for building in data["buildings"]:
                child_label = building.get("cn_name", building["name"])
                child = QTreeWidgetItem([child_label])
                child.setData(
                    0,
                    Qt.UserRole,
                    {
                        "facility": name,
                        "building": building["name"],
                        "type": ftype,
                        "node": "building",
                    },
                )
                category_item.addChild(child)

            parent_root.addChild(category_item)

        self.facility_tree.addTopLevelItem(equiv_root)
        self.facility_tree.addTopLevelItem(spec_root)
        self.facility_tree.expandItem(equiv_root)
        self.facility_tree.expandItem(spec_root)

    # Alias for backward compatibility
    def load_facilities(self):
        self._populate_tree()

    def _on_tree_clicked(self, item, column):
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        node = data.get("node", "")

        # Group root nodes ("等效模型" / "特异模型") are not actionable
        if node == "group":
            return

        facility_name = data["facility"]
        ftype = data["type"]

        if node == "building":
            # A specific building was selected
            building_name = data["building"]
            self.selected_facility_data = data

            if ftype == "equivalent":
                self._show_equivalent_params(facility_name, building_name)
            else:
                self._show_specialized_params(facility_name, building_name)

            self.generate_btn.setEnabled(True)
            self.generate_category_btn.setEnabled(False)
            self.combustible_btn.setEnabled(True)

        elif node == "facility":
            self.selected_facility_data = data
            self._show_facility_params(facility_name)
            self.generate_btn.setEnabled(False)
            self.generate_category_btn.setEnabled(True)
            self.combustible_btn.setEnabled(True)

    # ==================================================
    # Parameter display for equivalent models
    # ==================================================

    def _show_equivalent_params(self, facility_name, building_name):
        """Fill inline param controls from equivalent model default params."""
        bdata = self.facility_manager.get_building_data(facility_name, building_name)
        params = self.facility_manager.default_params(facility_name, building_name)
        ranges = params.get("ranges", {})
        scale_values = params.get("scale_values", {})
        self._params = {
            "facility": facility_name,
            "building": building_name,
            "type": "equivalent",
        }
        self._syncing = True
        self._param_ranges = ranges
        self._param_scale_values = scale_values

        # Populate size class combo (大/中/小) from ranges
        size_hints = self._scale_hints_from_params(scale_values, ranges)

        l_s, l_m, l_l = size_hints["length"]
        w_s, w_m, w_l = size_hints["width"]
        self.rng_size.setText(
            f"小: {l_s:.0f}×{w_s:.0f} / "
            f"中: {l_m:.0f}×{w_m:.0f} / "
            f"大: {l_l:.0f}×{w_l:.0f}"
        )
        self.size_combo.setEnabled(True)
        self.size_combo.blockSignals(True)
        self.size_combo.setCurrentText("中")
        self.size_combo.blockSignals(False)

        self.sp_N.setVisible(False)
        self.rng_N.setVisible(False)

        # Description
        cn = bdata.get("cn_name", building_name)
        desc = bdata.get("description", "")
        self.desc_label.setText(f"{cn}\n{desc}" if desc else cn)
        self._syncing = False

    # ==================================================
    # Size class selection callback
    # ==================================================

    def _on_size_class_changed(self, text: str):
        if self._syncing or not (self._param_scale_values or self._param_ranges):
            return
        idx = {"小": 0, "中": 1, "大": 2}.get(text, 1)
        self._syncing = True
        try:
            for field_name, spinbox in self._param_spinboxes.items():
                hints = self._scale_hints_from_params(
                    self._param_scale_values, self._param_ranges
                )
                if field_name not in hints:
                    continue
                val = hints[field_name][idx]
                if field_name == "stories":
                    val = int(round(val))
                spinbox.setValue(val)
        finally:
            self._syncing = False

    @staticmethod
    def _scale_hints_from_params(scale_values: dict, ranges: dict) -> dict:
        """Return ``{field: (small, medium, large)}`` for display."""
        hints = {}
        for field_name in ["length", "width", "height", "stories"]:
            if field_name in scale_values:
                values = tuple(scale_values[field_name])
            else:
                r = ranges.get(field_name, [0, 0])
                if len(r) >= 3:
                    values = (r[0], r[2], r[1])
                elif len(r) >= 2:
                    values = (r[0], (r[0] + r[1]) / 2, r[1])
                elif r:
                    values = (r[0], r[0], r[0])
                else:
                    values = (0, 0, 0)
            hints[field_name] = values
        return hints

    # ==================================================
    # Parameter display for specialized models
    # ==================================================

    def _show_specialized_params(self, facility_name, building_name):
        """Show read-only values from specialized building data."""
        bdata = self.facility_manager.get_building_data(facility_name, building_name)
        boundary = bdata.get("boundary", [0, 20, 0, 10])
        values = {
            "length": boundary[1],
            "width": boundary[3],
            "height": bdata.get("height", 3.0),
            "stories": len(bdata.get("stories", [])),
        }
        self._params = {
            "facility": facility_name,
            "building": building_name,
            "type": "specialized",
        }
        self._syncing = True
        self._param_scale_values = {}
        try:
            for field_name, val in values.items():
                spinbox = self._param_spinboxes[field_name]
                # Temporarily widen range so setValue doesn't clamp
                spinbox.setMinimum(0)
                spinbox.setMaximum(99999)
                spinbox.setValue(val)
                spinbox.setEnabled(False)
                self._range_labels[field_name].setVisible(False)

            # Size combo disabled for specialized models
            self.size_combo.setEnabled(False)

            # Description
            cn = bdata.get("cn_name", building_name)
            self.desc_label.setText(f"{cn} (特异模型 - 参数只读)")
        finally:
            self._syncing = False

    # ==================================================
    # Parameter display for facility-level (aggregated)
    # ==================================================

    def _show_facility_params(self, facility_name: str):
        """Fill inline param controls with aggregated ranges across all buildings."""
        fac_data = self.facility_manager.facilities[facility_name]
        buildings = fac_data["buildings"]
        ftype = fac_data["type"]
        cn_name = fac_data["cn_name"]

        self._params = {
            "facility": facility_name,
            "building": None,
            "type": ftype,
        }
        self._syncing = True
        try:
            if ftype == "specialized":
                self._param_scale_values = {}
                self.size_combo.setEnabled(False)
                self.rng_size.setText("")
                spinbox = self._param_spinboxes["stories"]
                spinbox.setEnabled(False)
                self._range_labels["stories"].setVisible(False)
                self.desc_label.setText(
                    f"{cn_name} (特异模型) — 共 {len(buildings)} 个建筑"
                )
                return

            # --- Equivalent: aggregate ranges across all buildings ---
            # Collect per-building ranges
            all_ranges: dict[str, dict] = {}  # bname -> {field: [min, max, ...]}
            all_scale_values: dict[str, dict] = {}
            for b in buildings:
                bname = b["name"]
                all_ranges[bname] = {
                    "length": b.get("length_range", [0, 0]),
                    "width": b.get("width_range", [0, 0]),
                    "height": b.get("height_range", [0, 0]),
                    "stories": b.get("stories_range", [0, 0]),
                }
                all_scale_values[bname] = self.facility_manager.scale_dimension_options(
                    facility_name, bname
                )

            # Compute overall span for description
            span = {}
            for field in ["length", "width", "height", "stories"]:
                mins = [all_scale_values[b][field][0] for b in all_scale_values]
                maxs = [all_scale_values[b][field][2] for b in all_scale_values]
                span[field] = (min(mins), max(maxs))

            # Use first building's ranges for preview & _param_ranges
            first_bname = buildings[0]["name"]
            first_ranges = all_ranges[first_bname]
            first_scale_values = all_scale_values[first_bname]
            self._param_ranges = first_ranges  # so _on_size_class_changed works
            self._param_scale_values = first_scale_values

            # Size hints from first building (reference display)
            first_hints = self._scale_hints_from_params(first_scale_values, first_ranges)
            l_s, l_m, l_l = first_hints["length"]
            w_s, w_m, w_l = first_hints["width"]
            h_s, h_m, h_l = first_hints["height"]
            n_s, n_m, n_l = first_hints["stories"]

            self.rng_size.setText(
                f"小: {l_s:.0f}×{w_s:.0f}×{h_s:.0f} / "
                f"中: {l_m:.0f}×{w_m:.0f}×{h_m:.0f} / "
                f"大: {l_l:.0f}×{w_l:.0f}×{h_l:.0f}"
            )
            self.size_combo.setEnabled(True)
            self.size_combo.blockSignals(True)
            self.size_combo.setCurrentText("中")
            self.size_combo.blockSignals(False)

            # Description: show facility name + overall range span
            sl, lmin, lmax = "长", span["length"][0], span["length"][1]
            sw, wmin, wmax = "宽", span["width"][0], span["width"][1]
            sh, hmin, hmax = "高", span["height"][0], span["height"][1]
            sn, nmin, nmax = "层", int(span["stories"][0]), int(span["stories"][1])
            range_str = f"{sl}: {lmin:.0f}~{lmax:.0f}  {sw}: {wmin:.0f}~{wmax:.0f}  {sh}: {hmin:.0f}~{hmax:.0f}  {sn}: {nmin}~{nmax}"
            self.desc_label.setText(
                f"{cn_name} (等效模型) — 共 {len(buildings)} 个建筑\n"
                f"尺寸 {range_str}"
            )
            self.sp_N.setVisible(False)
            self.rng_N.setVisible(False)
        finally:
            self._syncing = False

    # ==================================================
    # Size-class helper (for facility-level generation)
    # ==================================================

    def _build_params_for_size_class(
        self, facility_name: str, building_name: str, size_idx: int
    ) -> dict:
        """Build params dict from building's own ranges at the given size index.
        size_idx: 0=小, 1=中, -1=大
        """
        scale_idx = self._size_idx_to_scale_idx(size_idx)
        return self.facility_manager.params_for_scale(
            facility_name, building_name, scale_idx=scale_idx
        )

    @staticmethod
    def _size_idx_to_scale_idx(size_idx: int) -> int:
        if size_idx == 0:
            return 0
        if size_idx == 1:
            return 1
        return 2

    # ==================================================
    # Scene building lookup (for offset preservation)
    # ==================================================

    def _get_scene_building_offset(self, facility: str, building_name: str) -> tuple[float, float] | None:
        """Look up offset of an existing building with matching name in the scene."""
        buildings = getattr(self, "_scene_buildings", [])
        for b in buildings:
            if b.name == building_name or getattr(b, "cn_name", "") == building_name:
                return (b.offset_x, b.offset_y)
        return None

    # ==================================================
    # Generate actions
    # ==================================================

    @staticmethod
    def _auto_arrange_buildings(buildings, gap=15.0):
        x = 0.0
        for b in buildings:
            b.boundary[0] = x
            b.boundary[2] = 0.0
            x += b.length + gap

    def _on_generate(self):
        if not self.selected_facility_data:
            QMessageBox.warning(self.window(), "提示", "请先从设施类型中选择一个建筑")
            return

        data = self.selected_facility_data
        facility = data.get("facility")
        building_name = data.get("building")
        ftype = data.get("type")

        if not facility or not building_name:
            QMessageBox.warning(self.window(), "提示", "请先从设施类型中选择一个具体建筑")
            return

        if ftype == "specialized":
            building = self.facility_manager.load_specialized(facility, building_name)
        else:
            size_text = self.size_combo.currentText() if self.size_combo.isEnabled() else "中"
            size_idx = {"小": 0, "中": 1, "大": -1}.get(size_text, 1)
            params = self._build_params_for_size_class(
                facility, building_name, size_idx
            )
            existing_offset = self._get_scene_building_offset(facility, building_name)
            building = self.facility_manager.load_equivalent(
                facility, building_name, params,
                current_offset=existing_offset,
            )

        self.building_added.emit(building)

    def _on_generate_category(self):
        """Generate all buildings in the selected facility."""
        if not self.selected_facility_data:
            return

        facility_name = self.selected_facility_data.get("facility")
        if not facility_name:
            return

        ftype = self.facility_manager.get_type(facility_name)
        size_text = self.size_combo.currentText() if self.size_combo.isEnabled() else "中"
        size_idx = {"小": 0, "中": 1, "大": -1}.get(size_text, 1)

        # Internal arrange policy (decided once, in code, no UI opt-out):
        # - "specialized" facilities ship their own authoritative bounds.
        #   We never repack; doing so would silently overwrite curated data.
        # - "equivalent" facilities use a facility-level layout when present,
        #   so small / medium / large scenes keep the same inter-building gap.
        #   Legacy templates without layout still fall back to overlap cleanup.
        from models.build_arranger import arrange_buildings, has_overlap

        buildings = []

        if ftype == "specialized":
            for bname in self.facility_manager.list_buildings(facility_name):
                buildings.append(
                    self.facility_manager.load_specialized(facility_name, bname)
                )
        else:
            for bname in self.facility_manager.list_buildings(facility_name):
                params = self._build_params_for_size_class(
                    facility_name, bname, size_idx
                )
                buildings.append(
                    self.facility_manager.load_equivalent(
                        facility_name, bname, params
                    )
                )
            layout_applied = self.facility_manager.arrange_buildings_by_layout(
                facility_name, buildings
            )
            if not layout_applied and len(buildings) > 1 and has_overlap(buildings):
                arrange_buildings(buildings, gap=20.0)

        if not buildings:
            return

        group = BuildingGroup(name=facility_name, buildings=buildings)
        self.facility_selected.emit(group.to_dict())

    def _on_combustible_clicked(self):
        """Route combustible button to building-level or facility-level dialog."""
        if not self.selected_facility_data:
            return
        node = self.selected_facility_data.get("node")
        if node == "facility":
            self._open_facility_combustible_dialog()
        else:
            self._open_combustible_dialog()

    def _open_combustible_dialog(self):
        """Open combustible management with the current building's FC list."""
        if not self._params:
            return

        facility = self._params.get("facility")
        building_name = self._params.get("building")
        ftype = self._params.get("type")
        if not facility or not building_name:
            return

        # Collect fire_compartments as plain dicts for the dialog.
        fcs: list[dict] = []
        if ftype == "specialized":
            bdata = self.facility_manager.get_building_data(facility, building_name)
            for story in bdata.get("stories", []):
                for fc in story.get("fire_compartments", []):
                    fcs.append(fc)
        else:
            params_full = self.facility_manager.default_params(facility, building_name)
            bld = self.facility_manager.load_equivalent(facility, building_name, params_full)
            for story in bld.stories:
                for fc in story.fire_compartments:
                    fcs.append(fc.to_dict())

        from ui.dialogs import CombustibleSelectionDialog

        current_sel = self._params.get("combustible_selections", {})
        dlg = CombustibleSelectionDialog(
            self,
            current_sel,
            fire_compartments=fcs,
        )
        if dlg.exec() == QDialog.Accepted:
            self._params["combustible_selections"] = dlg.get_selections()

    def _open_facility_combustible_dialog(self):
        """Open facility-level combustible overview dialog (read-only)."""
        if not self.selected_facility_data:
            return
        facility_name = self.selected_facility_data.get("facility")
        if not facility_name:
            return

        size_text = self.size_combo.currentText() if self.size_combo.isEnabled() else "中"
        size_idx = {"小": 0, "中": 1, "大": -1}.get(size_text, 1)

        from ui.dialogs import FacilityCombustibleOverviewDialog

        dlg = FacilityCombustibleOverviewDialog(
            self,
            facility_manager=self.facility_manager,
            facility_name=facility_name,
            size_idx=size_idx,
        )
        dlg.exec()

    # ==================================================
    # Compatibility stubs (for FacilityDialog path)
    # ==================================================

    def generate_equivalent_model(self):
        self._on_generate()

    def generate_category_model(self):
        self._on_generate_category()

    # ==================================================
    # Scene object list
    # ==================================================

    def update_scene_list(self, buildings):
        """Update scene table from list of Building objects."""
        self.scene_table.setRowCount(len(buildings))
        self._scene_buildings = buildings  # keep reference for selection

        for i, b in enumerate(buildings):
            name_item = QTableWidgetItem(b.cn_name or b.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.scene_table.setItem(i, 0, name_item)

            size_item = QTableWidgetItem(f"{b.length:.1f}x{b.width:.1f}x{b.height:.1f}")
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)
            self.scene_table.setItem(i, 1, size_item)

            pos_item = QTableWidgetItem(f"({b.offset_x:.1f}, {b.offset_y:.1f})")
            pos_item.setFlags(pos_item.flags() & ~Qt.ItemIsEditable)
            self.scene_table.setItem(i, 2, pos_item)

        self.scene_table.resizeColumnsToContents()

    def _on_scene_table_clicked(self, row, col):
        """Handle scene table click - select building."""
        if 0 <= row < len(getattr(self, "_scene_buildings", [])):
            self._selected_scene_idx = row
            self.scene_building_selected.emit(row)
