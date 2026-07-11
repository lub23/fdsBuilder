#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dialog module extracted from ui.dialogs."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QDoubleSpinBox, QLabel, QDialogButtonBox, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QHeaderView,
)
from models.facility import FacilityManager

class CategoryGenerateDialog(QDialog):
    """设施级别生成对话框 - 生成某设施下所有建筑群

    Updated for new FacilityManager API (facilities dict, list_buildings,
    load_equivalent, load_specialized, default_params).
    """

    def __init__(self, parent=None, facility_manager=None, facility_key: str = ""):
        super().__init__(parent)
        self.setWindowTitle("生成设施全部建筑")
        self.resize(750, 500)
        self.result_model = None
        self._mgr = facility_manager or FacilityManager()
        self._facility_key = facility_key
        self._building_params = []  # list of dicts with building info
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        fac_data = self._mgr.facilities.get(self._facility_key, {})
        cn_name = fac_data.get("cn_name", self._facility_key)
        ftype = fac_data.get("type", "equivalent")
        type_label = "等效模型" if ftype == "equivalent" else "特异模型"
        layout.addWidget(QLabel(
            f"<b>设施: {cn_name}</b> ({type_label}) — 调整各建筑偏移后生成建筑群"))

        # Table: Name, Length, Width, Height, X Offset, Y Offset
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["名称", "长度(m)", "宽度(m)", "高度(m)", "X偏移(m)", "Y偏移(m)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Spacing helper
        spacing_layout = QHBoxLayout()
        spacing_layout.addWidget(QLabel("自动间距:"))
        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(0, 100)
        self.spacing_spin.setValue(5.0)
        self.spacing_spin.setSuffix(" m")
        spacing_layout.addWidget(self.spacing_spin)

        auto_btn = QPushButton("重新排列")
        auto_btn.clicked.connect(self._auto_arrange)
        spacing_layout.addWidget(auto_btn)
        spacing_layout.addStretch()
        layout.addLayout(spacing_layout)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_generate)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _load_data(self):
        ftype = self._mgr.get_type(self._facility_key)
        building_names = self._mgr.list_buildings(self._facility_key)

        self._building_params = []
        for bname in building_names:
            bdata = self._mgr.get_building_data(self._facility_key, bname)
            if ftype == "equivalent":
                params = self._mgr.default_params(self._facility_key, bname)
                entry = {
                    "name": bdata.get("cn_name", bname),
                    "building_name": bname,
                    "length": params["length"],
                    "width": params["width"],
                    "height": params["height"],
                    "stories": params["stories"],
                    "_x_offset": 0.0,
                    "_y_offset": 0.0,
                }
            else:
                boundary = bdata.get("boundary", [0, 20, 0, 10])
                entry = {
                    "name": bdata.get("cn_name", bname),
                    "building_name": bname,
                    "length": boundary[1],
                    "width": boundary[3],
                    "height": bdata.get("height", 3.0),
                    "stories": len(bdata.get("stories", [])),
                    "_x_offset": boundary[0],
                    "_y_offset": boundary[2],
                }
            self._building_params.append(entry)

        if ftype == "equivalent":
            self._auto_arrange()
        self._fill_table()

    def _fill_table(self):
        self.table.setRowCount(len(self._building_params))
        for i, p in enumerate(self._building_params):
            self.table.setItem(i, 0, QTableWidgetItem(p.get("name", "")))
            self.table.setItem(i, 1, QTableWidgetItem(f"{p['length']:.1f}"))
            self.table.setItem(i, 2, QTableWidgetItem(f"{p['width']:.1f}"))
            self.table.setItem(i, 3, QTableWidgetItem(f"{p['height']:.1f}"))

            x_spin = QDoubleSpinBox()
            x_spin.setRange(-1000, 10000)
            x_spin.setDecimals(1)
            x_spin.setValue(p.get("_x_offset", 0.0))
            self.table.setCellWidget(i, 4, x_spin)

            y_spin = QDoubleSpinBox()
            y_spin.setRange(-1000, 10000)
            y_spin.setDecimals(1)
            y_spin.setValue(p.get("_y_offset", 0.0))
            self.table.setCellWidget(i, 5, y_spin)

    def _auto_arrange(self):
        """Auto-arrange buildings in a simple row layout with spacing."""
        spacing = self.spacing_spin.value()

        x_cursor = 0.0
        for i, p in enumerate(self._building_params):
            p["_x_offset"] = x_cursor
            p["_y_offset"] = 0.0
            x_cursor += p["length"] + spacing

            x_spin = self.table.cellWidget(i, 4)
            y_spin = self.table.cellWidget(i, 5)
            if x_spin:
                x_spin.setValue(p["_x_offset"])
            if y_spin:
                y_spin.setValue(p["_y_offset"])

    def _on_generate(self):
        from models.building import BuildingGroup

        ftype = self._mgr.get_type(self._facility_key)
        buildings = []

        for i, p in enumerate(self._building_params):
            x_spin = self.table.cellWidget(i, 4)
            y_spin = self.table.cellWidget(i, 5)
            x_off = x_spin.value() if x_spin else 0.0
            y_off = y_spin.value() if y_spin else 0.0
            bname = p["building_name"]

            if ftype == "specialized":
                b = self._mgr.load_specialized(self._facility_key, bname)
            else:
                params = self._mgr.default_params(self._facility_key, bname)
                b = self._mgr.load_equivalent(self._facility_key, bname, params)

            b.boundary[0] = x_off
            b.boundary[2] = y_off
            buildings.append(b)

        self.result_model = BuildingGroup(name=bname, buildings=buildings)
        self.accept()
