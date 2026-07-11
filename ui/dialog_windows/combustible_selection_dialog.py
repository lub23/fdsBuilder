#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dialog module extracted from ui.dialogs."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QHBoxLayout, QSpinBox, QCheckBox, QGridLayout, QScrollArea, QWidget,
)
from models.materials import COMBUSTIBLE_LIBRARY

class CombustibleSelectionDialog(QDialog):
    """Combustible selection dialog showing only current sub-target's predefined items."""

    def __init__(self, parent=None, current_selections=None,
                 current_method=0, facility_combustibles=None,
                 fire_compartments=None):
        super().__init__(parent)
        self.setWindowTitle("可燃物管理")
        self.setMinimumWidth(520)
        self._selections = current_selections or {}
        self._fac_combs = facility_combustibles or []
        self._fire_compartments = fire_compartments or []

        # Collect compartment names for multi-select
        self._compartment_names = [fc["name"] for fc in self._fire_compartments]

        # Build item list: only items defined in fire_compartments
        self._items = []  # list of (key, name, default_count, default_compartments)
        seen_keys = set()
        for fi, fc in enumerate(self._fire_compartments):
            fc_name = fc["name"]
            for item in fc.get("combustibles", []) + fc.get("specialized_components", []):
                key = item["key"]
                count = item.get("count", 1)
                if key in seen_keys:
                    # Already added — just append this compartment
                    for existing in self._items:
                        if existing[0] == key:
                            existing[3].add(fc_name)
                            break
                else:
                    seen_keys.add(key)
                    name = COMBUSTIBLE_LIBRARY.get(key, {}).get("name", key)
                    self._items.append([key, name, count, {fc_name}])

        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("名称"))
        header.addWidget(QLabel("数量"))
        lbl_fc = QLabel("所属防火分区")
        lbl_fc.setMinimumWidth(180)
        header.addWidget(lbl_fc)
        layout.addLayout(header)

        # Rows
        self._rows = []  # list of {key, spin, compartment_checks}
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        container = QWidget()
        g = QGridLayout(container)
        g.setSpacing(4)

        for i, (key, name, default_count, default_fcs) in enumerate(self._items):
            # Name
            name_lbl = QLabel(name)
            name_lbl.setMinimumWidth(120)
            g.addWidget(name_lbl, i, 0)

            # Count spin
            sp = QSpinBox()
            sp.setRange(0, 200)
            sp.setValue(self._selections.get(key, default_count))
            sp.setFixedWidth(70)
            g.addWidget(sp, i, 1)

            # Compartment checkboxes (horizontal)
            fc_widget = QWidget()
            fc_layout = QHBoxLayout(fc_widget)
            fc_layout.setContentsMargins(0, 0, 0, 0)
            fc_layout.setSpacing(4)
            fc_checks = {}
            saved_fcs = self._selections.get(f"{key}__fcs", None)
            for fc_name in self._compartment_names:
                cb = QCheckBox(fc_name)
                if saved_fcs is not None:
                    cb.setChecked(fc_name in saved_fcs)
                else:
                    cb.setChecked(fc_name in default_fcs)
                fc_layout.addWidget(cb)
                fc_checks[fc_name] = cb
            g.addWidget(fc_widget, i, 2)

            self._rows.append({"key": key, "spin": sp, "fc_checks": fc_checks})

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_selections(self) -> dict:
        sel = {}
        for row in self._rows:
            key = row["key"]
            count = row["spin"].value()
            if count > 0:
                sel[key] = count
                # Save compartment assignments
                fcs = [name for name, cb in row["fc_checks"].items() if cb.isChecked()]
                sel[f"{key}__fcs"] = fcs
        return sel

    def get_method(self) -> int:
        return 0  # No distribution method selection
