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
    QGroupBox,
    QFormLayout,
    QDialog,
    QDoubleSpinBox,
    QSpinBox,
    QComboBox,
    QGridLayout,
    QCheckBox,
    QScrollArea,
    QTabWidget,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QBrush
from models.facility import FacilityManager
from models.building import Building, BuildingGroup, Story
from ui.styles import CollapsibleGroup

# Wall name choices for door/window distribution (kept locally)
WALL_NAMES = ["南墙", "北墙", "东墙", "西墙", "均匀分布"]

# Alias for backwards compatibility within this file
CollapsibleSection = CollapsibleGroup


class FacilityListPanel(QWidget):
    """Left sidebar: facility tree + inline params + scene list."""

    facility_selected = Signal(dict)  # replace entire model (category generation)
    building_added = Signal(object)  # append one Building object
    scene_building_removed = Signal(int)  # remove building by index
    scene_building_selected = Signal(int)  # select building for editing
    scene_building_offset_changed = Signal(int, float, float)  # index, x, y

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
        self.desc_label.setStyleSheet("color:#a6adc8; font-size:11px;")
        sec_tree.content_layout.addWidget(self.desc_label)
        outer.addWidget(sec_tree)

        # -- 2. Building params --
        sec_bld = CollapsibleSection("建筑参数")
        g = QGridLayout()
        g.setSpacing(3)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)

        def _dsp(lo, hi, val, sfx=" m", width=None):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(1)
            s.setSuffix(sfx)
            s.setValue(val)
            s.setFixedHeight(26)
            s.setStyleSheet("font-size:13px;")
            if width:
                s.setFixedWidth(width)
            return s

        def _isp(lo, hi, val, width=None):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setValue(val)
            s.setFixedHeight(26)
            s.setStyleSheet("font-size:13px;")
            if width:
                s.setFixedWidth(width)
            return s

        def _lbl(text):
            lbl = QLabel(text)
            lbl.setFixedWidth(lbl.sizeHint().width())
            return lbl

        def _range_label(width=None):
            lbl = QLabel("")
            lbl.setStyleSheet("color:#6c7086; font-size:10px;")
            if width:
                lbl.setFixedWidth(width)
            return lbl

        r = 0
        g.addWidget(_lbl("长:"), r, 0)
        self.sp_L = _dsp(1, 2000, 20, width=80)
        g.addWidget(self.sp_L, r, 1)
        self.rng_L = _range_label(width=80)
        g.addWidget(self.rng_L, r, 2)
        g.addWidget(_lbl("宽:"), r, 3)
        self.sp_W = _dsp(1, 2000, 15, width=80)
        g.addWidget(self.sp_W, r, 4)
        self.rng_W = _range_label(width=80)
        g.addWidget(self.rng_W, r, 5)

        r += 1
        g.addWidget(_lbl("高:"), r, 0)
        self.sp_H = _dsp(1, 300, 12, width=80)
        g.addWidget(self.sp_H, r, 1)
        self.rng_H = _range_label(width=80)
        g.addWidget(self.rng_H, r, 2)
        g.addWidget(_lbl("层:"), r, 3)
        self.sp_N = _isp(1, 30, 1, width=80)
        g.addWidget(self.sp_N, r, 4)
        self.rng_N = _range_label(width=80)
        g.addWidget(self.rng_N, r, 5)

        r += 1
        g.addWidget(_lbl("墙厚:"), r, 0)
        self.sp_T = _dsp(0.05, 5, 0.24, width=80)
        self.sp_T.setDecimals(2)
        g.addWidget(self.sp_T, r, 1)
        g.addWidget(_lbl("位置X:"), r, 2)
        self.sp_X_offset = _dsp(-1000, 1000, 0, width=80)
        g.addWidget(self.sp_X_offset, r, 3)
        g.addWidget(_lbl("位置Y:"), r, 4)
        self.sp_Y_offset = _dsp(-1000, 1000, 0, width=80)
        g.addWidget(self.sp_Y_offset, r, 5)

        sec_bld.content_layout.addLayout(g)

        # Collect param spinboxes and range labels into dicts for easy access
        self._param_spinboxes = {
            "length": self.sp_L,
            "width": self.sp_W,
            "height": self.sp_H,
            "stories": self.sp_N,
        }
        self._range_labels = {
            "length": self.rng_L,
            "width": self.rng_W,
            "height": self.rng_H,
            "stories": self.rng_N,
        }

        outer.addWidget(sec_bld)

        # -- 3. Door+Window merged with QTabWidget --
        sec_door_win = CollapsibleSection("门窗设置")

        self._door_win_tabs = QTabWidget()
        self._door_win_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #45475a; }"
        )
        self._door_win_tabs.setMaximumHeight(130)

        # Door tab
        door_tab = QWidget()
        dg = QGridLayout(door_tab)
        dg.setSpacing(2)
        dg.setContentsMargins(2, 2, 2, 2)
        dg.setColumnStretch(1, 1)
        dg.setColumnStretch(3, 1)
        dg.addWidget(_lbl("分布:"), 0, 0)
        self.cb_dwall = QComboBox()
        self.cb_dwall.addItems(WALL_NAMES)
        self.cb_dwall.setCurrentIndex(4)
        self.cb_dwall.setFixedHeight(26)
        self.cb_dwall.setStyleSheet("font-size:13px;")
        dg.addWidget(self.cb_dwall, 0, 1)
        self.rng_dwall = _range_label(width=80)
        dg.addWidget(self.rng_dwall, 0, 2)
        dg.addWidget(_lbl("数量:"), 0, 3)
        self.sp_dc = _isp(0, 500, 0, width=80)
        dg.addWidget(self.sp_dc, 0, 4)
        self.rng_dc = _range_label(width=80)
        dg.addWidget(self.rng_dc, 0, 5)
        dg.addWidget(_lbl("宽:"), 1, 0)
        self.sp_dw = _dsp(0.3, 20, 1.5, width=80)
        dg.addWidget(self.sp_dw, 1, 1)
        self.rng_dw = _range_label(width=80)
        dg.addWidget(self.rng_dw, 1, 2)
        dg.addWidget(_lbl("高:"), 1, 3)
        self.sp_dh = _dsp(0.3, 20, 2.1, width=80)
        dg.addWidget(self.sp_dh, 1, 4)
        self.rng_dh = _range_label(width=80)
        dg.addWidget(self.rng_dh, 1, 5)

        # Window tab
        win_tab = QWidget()
        wg = QGridLayout(win_tab)
        wg.setSpacing(2)
        wg.setContentsMargins(2, 2, 2, 2)
        wg.setColumnStretch(1, 1)
        wg.setColumnStretch(3, 1)
        wg.addWidget(_lbl("分布:"), 0, 0)
        self.cb_wwall = QComboBox()
        self.cb_wwall.addItems(WALL_NAMES)
        self.cb_wwall.setCurrentIndex(4)
        self.cb_wwall.setFixedHeight(26)
        self.cb_wwall.setStyleSheet("font-size:13px;")
        wg.addWidget(self.cb_wwall, 0, 1)
        self.rng_wwall = _range_label(width=80)
        wg.addWidget(self.rng_wwall, 0, 2)
        wg.addWidget(_lbl("数量:"), 0, 3)
        self.sp_wc = _isp(0, 500, 0, width=80)
        wg.addWidget(self.sp_wc, 0, 4)
        self.rng_wc = _range_label(width=80)
        wg.addWidget(self.rng_wc, 0, 5)
        wg.addWidget(_lbl("宽:"), 1, 0)
        self.sp_ww = _dsp(0.3, 20, 1.5, width=80)
        wg.addWidget(self.sp_ww, 1, 1)
        self.rng_ww = _range_label(width=80)
        wg.addWidget(self.rng_ww, 1, 2)
        wg.addWidget(_lbl("高:"), 1, 3)
        self.sp_wh = _dsp(0.3, 20, 1.5, width=80)
        wg.addWidget(self.sp_wh, 1, 4)
        self.rng_wh = _range_label(width=80)
        wg.addWidget(self.rng_wh, 1, 5)

        self._door_win_tabs.addTab(door_tab, "门")
        self._door_win_tabs.addTab(win_tab, "窗")
        sec_door_win.content_layout.addWidget(self._door_win_tabs)
        outer.addWidget(sec_door_win)

        # -- 7. Combustible button --
        self.combustible_btn = QPushButton("可燃物管理…")
        self.combustible_btn.setFixedHeight(34)
        self.combustible_btn.setStyleSheet(
            "QPushButton{background:#89b4fa;color:#1e1e2e;font-weight:bold;"
            "padding:4px 10px;border-radius:3px;font-size:13px}"
            "QPushButton:hover{background:#74c7ec}"
        )
        self.combustible_btn.setEnabled(False)
        self.combustible_btn.clicked.connect(self._open_combustible_dialog)
        outer.addWidget(self.combustible_btn)

        # -- Action buttons --
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self.generate_btn = QPushButton("生成建筑")
        self.generate_btn.setEnabled(False)
        self.generate_btn.setFixedHeight(34)
        self.generate_btn.setStyleSheet(
            "QPushButton{background:#a6e3a1;color:#1e1e2e;font-weight:bold;"
            "border-radius:3px;font-size:13px;padding:4px 10px}"
            "QPushButton:hover{background:#94e2d5}"
            "QPushButton:disabled{background:#45475a;color:#6c7086}"
        )
        self.generate_btn.clicked.connect(self._on_generate)
        btn_layout.addWidget(self.generate_btn)

        self.generate_category_btn = QPushButton("生成设施全部建筑")
        self.generate_category_btn.setEnabled(False)
        self.generate_category_btn.setFixedHeight(34)
        self.generate_category_btn.setStyleSheet(
            "QPushButton{background:#89b4fa;color:#1e1e2e;font-weight:bold;"
            "border-radius:3px;font-size:13px;padding:4px 10px}"
            "QPushButton:hover{background:#74c7ec}"
            "QPushButton:disabled{background:#45475a;color:#6c7086}"
        )
        self.generate_category_btn.clicked.connect(self._on_generate_category)
        btn_layout.addWidget(self.generate_category_btn)

        outer.addLayout(btn_layout)

        # -- 8. Scene object list --
        sec_scene = CollapsibleSection("场景目标列表")
        self.scene_table = QTableWidget()
        self.scene_table.setColumnCount(5)
        self.scene_table.setHorizontalHeaderLabels(["名称", "尺寸", "位置", "操作", ""])
        self.scene_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.scene_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.scene_table.setColumnWidth(2, 180)  # position column fixed 180px
        self.scene_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.scene_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.scene_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.scene_table.setSelectionMode(QTableWidget.SingleSelection)
        self.scene_table.setMinimumHeight(100)
        self.scene_table.setStyleSheet(
            "QTableWidget{font-size:12px;}QTableWidget::item{padding:2px 0;}"
        )
        self.scene_table.cellClicked.connect(self._on_scene_table_clicked)
        sec_scene.content_layout.addWidget(self.scene_table)

        # Track editing state
        self._editing_row = -1
        self._editing_widgets = {}  # row -> {x_spin, y_spin}

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

        for i in range(equiv_root.childCount()):
            self.facility_tree.expandItem(equiv_root.child(i))
        for i in range(spec_root.childCount()):
            self.facility_tree.expandItem(spec_root.child(i))

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
            # A facility-level node was selected
            cn_name = self.facility_manager.facilities[facility_name]["cn_name"]
            buildings = self.facility_manager.facilities[facility_name]["buildings"]
            type_label = "等效模型" if ftype == "equivalent" else "特异模型"
            self.desc_label.setText(
                f"{cn_name} ({type_label}) — 共 {len(buildings)} 个建筑\n"
                "点击「生成设施全部建筑」可生成该设施下所有建筑"
            )
            self.generate_btn.setEnabled(False)
            self.generate_category_btn.setEnabled(True)
            self.combustible_btn.setEnabled(False)
            self.selected_facility_data = data

    # ==================================================
    # Parameter display for equivalent models
    # ==================================================

    def _show_equivalent_params(self, facility_name, building_name):
        """Fill inline param controls from equivalent model default params."""
        params = self.facility_manager.default_params(facility_name, building_name)
        ranges = params.get("ranges", {})
        self._params = {
            "facility": facility_name,
            "building": building_name,
            "type": "equivalent",
        }
        self._syncing = True
        try:
            for field_name in ["length", "width", "height", "stories"]:
                spinbox = self._param_spinboxes[field_name]
                spinbox.setEnabled(True)
                r = ranges.get(field_name, [0, 0])
                spinbox.setMinimum(r[0])
                spinbox.setMaximum(r[1])
                spinbox.setValue(params[field_name])
                lo, hi = r[0], r[1]
                if lo == hi:
                    self._range_labels[field_name].setText("")
                elif field_name == "stories":
                    self._range_labels[field_name].setText(f"({int(lo)}~{int(hi)})")
                else:
                    self._range_labels[field_name].setText(f"({lo:.1f}~{hi:.1f})")
                self._range_labels[field_name].setVisible(True)

            # Wall thickness and offsets remain editable
            self.sp_T.setEnabled(True)
            bdata = self.facility_manager.get_building_data(
                facility_name, building_name
            )
            self.sp_T.setValue(bdata.get("wall_thickness", 0.24))
            self.sp_X_offset.setValue(0.0)
            self.sp_Y_offset.setValue(0.0)

            # Description
            cn = bdata.get("cn_name", building_name)
            desc = bdata.get("description", "")
            self.desc_label.setText(f"{cn}\n{desc}" if desc else cn)
        finally:
            self._syncing = False

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
        try:
            for field_name, val in values.items():
                spinbox = self._param_spinboxes[field_name]
                # Temporarily widen range so setValue doesn't clamp
                spinbox.setMinimum(0)
                spinbox.setMaximum(99999)
                spinbox.setValue(val)
                spinbox.setEnabled(False)
                self._range_labels[field_name].setVisible(False)

            # Wall thickness read-only
            self.sp_T.setValue(bdata.get("wall_thickness", 0.24))
            self.sp_T.setEnabled(False)
            # Offsets: allow editing position
            self.sp_X_offset.setValue(boundary[0])
            self.sp_Y_offset.setValue(boundary[2])

            # Description
            cn = bdata.get("cn_name", building_name)
            self.desc_label.setText(f"{cn} (特异模型 - 参数只读)")
        finally:
            self._syncing = False

    # ==================================================
    # Read params -> dict (for equivalent models)
    # ==================================================

    def _read_params(self) -> dict:
        p = dict(self._params) if self._params else {}
        p.update(
            length=self.sp_L.value(),
            width=self.sp_W.value(),
            height=self.sp_H.value(),
            stories=self.sp_N.value(),
            wall_thickness=self.sp_T.value(),
            x_offset=self.sp_X_offset.value(),
            y_offset=self.sp_Y_offset.value(),
            door_width=self.sp_dw.value(),
            door_height=self.sp_dh.value(),
            door_count=self.sp_dc.value(),
            door_wall=self.cb_dwall.currentIndex(),
            window_width=self.sp_ww.value(),
            window_height=self.sp_wh.value(),
            window_count=self.sp_wc.value(),
            window_wall=self.cb_wwall.currentIndex(),
        )

        # Combustible selections from stored params (set via dialog)
        if "combustible_selections" not in p:
            p["combustible_selections"] = {}
        if "combustible_method" not in p:
            p["combustible_method"] = 0
        if "combustible_floor" not in p:
            p["combustible_floor"] = -1
        return p

    # ==================================================
    # Generate actions
    # ==================================================

    def _on_generate(self):
        if not self.selected_facility_data:
            QMessageBox.warning(self, "提示", "请先从设施类型中选择一个建筑")
            return

        data = self.selected_facility_data
        facility = data.get("facility")
        building_name = data.get("building")
        ftype = data.get("type")

        if not facility or not building_name:
            QMessageBox.warning(self, "提示", "请先从设施类型中选择一个具体建筑")
            return

        if ftype == "specialized":
            building = self.facility_manager.load_specialized(facility, building_name)
            # Apply user-specified offsets
            building.boundary[0] = self.sp_X_offset.value()
            building.boundary[2] = self.sp_Y_offset.value()
        else:
            params = {
                field: self._param_spinboxes[field].value()
                for field in ["length", "width", "height", "stories"]
            }
            building = self.facility_manager.load_equivalent(
                facility, building_name, params
            )
            # Apply user-specified offsets
            building.boundary[0] = self.sp_X_offset.value()
            building.boundary[2] = self.sp_Y_offset.value()

        self.building_added.emit(building)

    def _on_generate_category(self):
        """Generate all buildings in the selected facility."""
        if not self.selected_facility_data:
            return

        facility_name = self.selected_facility_data.get("facility")
        if not facility_name:
            return

        ftype = self.facility_manager.get_type(facility_name)
        buildings = []

        if ftype == "specialized":
            # Load all specialized buildings
            for bname in self.facility_manager.list_buildings(facility_name):
                b = self.facility_manager.load_specialized(facility_name, bname)
                buildings.append(b)
        else:
            # Load all equivalent buildings with default params
            for bname in self.facility_manager.list_buildings(facility_name):
                params = self.facility_manager.default_params(facility_name, bname)
                b = self.facility_manager.load_equivalent(facility_name, bname, params)
                buildings.append(b)

        if buildings:
            group = BuildingGroup(buildings=buildings)
            self.facility_selected.emit(group.to_dict())

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
        self._editing_row = -1
        self._editing_widgets = {}
        self.scene_table.setRowCount(len(buildings))
        self._scene_buildings = buildings  # keep reference for editing

        btn_style_edit = (
            "QPushButton{background:#89b4fa;color:#1e1e2e;font-weight:bold;"
            "padding:2px 6px;border-radius:3px;font-size:11px}"
            "QPushButton:hover{background:#74c7ec}"
        )
        btn_style_del = (
            "QPushButton{background:#f38ba8;color:#1e1e2e;font-weight:bold;"
            "padding:2px 6px;border-radius:3px;font-size:11px}"
            "QPushButton:hover{background:#e06080}"
        )

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

            edit_btn = QPushButton("编辑")
            edit_btn.setFixedHeight(24)
            edit_btn.setStyleSheet(btn_style_edit)
            edit_btn.clicked.connect(lambda _, idx=i: self._toggle_edit(idx))
            self.scene_table.setCellWidget(i, 3, edit_btn)

            del_btn = QPushButton("删除")
            del_btn.setFixedHeight(24)
            del_btn.setStyleSheet(btn_style_del)
            del_btn.setEnabled(len(buildings) > 1)  # single building: disable delete
            del_btn.clicked.connect(lambda _, idx=i: self._on_scene_delete_row(idx))
            self.scene_table.setCellWidget(i, 4, del_btn)

        self.scene_table.resizeColumnsToContents()

    def _on_scene_table_clicked(self, row, col):
        """Handle scene table click - select building."""
        if 0 <= row < len(getattr(self, "_scene_buildings", [])):
            self._selected_scene_idx = row
            self.scene_building_selected.emit(row)

    def _toggle_edit(self, row):
        """Toggle inline editing for a scene building row."""
        if self._editing_row == row:
            # Finish editing: read values, emit changes, restore display
            self._finish_edit(row)
            return

        # If editing another row, finish that first
        if self._editing_row >= 0:
            self._finish_edit(self._editing_row)

        buildings = getattr(self, "_scene_buildings", [])
        if row >= len(buildings):
            return
        b = buildings[row]

        # Replace position cell with spinboxes
        widget = QWidget()
        hl = QHBoxLayout(widget)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(2)
        x_spin = QDoubleSpinBox()
        x_spin.setRange(-1000, 10000)
        x_spin.setDecimals(1)
        x_spin.setValue(b.offset_x)
        x_spin.setFixedHeight(24)
        x_spin.setMinimumWidth(80)
        x_spin.setPrefix("X:")
        hl.addWidget(x_spin)

        y_spin = QDoubleSpinBox()
        y_spin.setRange(-1000, 10000)
        y_spin.setDecimals(1)
        y_spin.setValue(b.offset_y)
        y_spin.setFixedHeight(24)
        y_spin.setMinimumWidth(80)
        y_spin.setPrefix("Y:")
        hl.addWidget(y_spin)

        self.scene_table.setCellWidget(row, 2, widget)

        # Change edit button to "完成"
        btn = self.scene_table.cellWidget(row, 3)
        if btn:
            btn.setText("完成")

        self._editing_row = row
        self._editing_widgets[row] = {"x_spin": x_spin, "y_spin": y_spin}

    def _finish_edit(self, row):
        """Complete inline editing and apply changes."""
        widgets = self._editing_widgets.get(row)
        if not widgets:
            self._editing_row = -1
            return

        buildings = getattr(self, "_scene_buildings", [])
        if row < len(buildings):
            x_val = widgets["x_spin"].value()
            y_val = widgets["y_spin"].value()
            self.scene_building_offset_changed.emit(row, x_val, y_val)

        # Restore button text
        btn = self.scene_table.cellWidget(row, 3)
        if btn:
            btn.setText("编辑")

        # Restore position cell as text (will be refreshed by update_scene_list)
        self.scene_table.removeCellWidget(row, 2)
        if row < len(buildings):
            b = buildings[row]
            pos_item = QTableWidgetItem(f"({b.offset_x:.1f}, {b.offset_y:.1f})")
            pos_item.setFlags(pos_item.flags() & ~Qt.ItemIsEditable)
            self.scene_table.setItem(row, 2, pos_item)

        self._editing_row = -1
        if row in self._editing_widgets:
            del self._editing_widgets[row]

    def _on_scene_delete_row(self, row):
        """Delete a building with confirmation."""
        buildings = getattr(self, "_scene_buildings", [])
        if row < 0 or row >= len(buildings):
            return
        name = buildings[row].cn_name or buildings[row].name
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除建筑「{name}」吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.scene_building_removed.emit(row)

    def _on_scene_offset_changed(self):
        if self._syncing:
            return
        idx = getattr(self, "_selected_scene_idx", None)
        if idx is not None:
            widgets = self._editing_widgets.get(idx)
            if widgets:
                self.scene_building_offset_changed.emit(
                    idx, widgets["x_spin"].value(), widgets["y_spin"].value()
                )

    def _on_scene_delete(self):
        row = self.scene_table.currentRow()
        if row >= 0:
            self._on_scene_delete_row(row)
