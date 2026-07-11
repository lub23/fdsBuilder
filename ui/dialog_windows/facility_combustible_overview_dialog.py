#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dialog module extracted from ui.dialogs."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QHeaderView,
)
from models.combustibles import SPECIALIZED_COMPONENTS
from models.materials import COMBUSTIBLE_LIBRARY

class FacilityCombustibleOverviewDialog(QDialog):
    """Read-only overview of all combustibles across an entire facility."""

    def __init__(self, parent=None, facility_manager=None,
                 facility_name="", size_idx=1):
        super().__init__(parent)
        self._mgr = facility_manager
        self._facility_name = facility_name
        self._size_idx = size_idx
        fac_data = facility_manager.facilities[facility_name]
        self.setWindowTitle(f"设施可燃物概览 — {fac_data['cn_name']}")
        self.setMinimumSize(700, 500)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Header
        fac_data = self._mgr.facilities[self._facility_name]
        header = QLabel(
            f"<b>{fac_data['cn_name']}</b> — 共 {len(fac_data['buildings'])} 个建筑"
        )
        header.setStyleSheet("font-size:16px; padding:8px;")
        layout.addWidget(header)

        # Read-only table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["名称", "类型", "总数量", "出现位置"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        # Summary
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(
            "font-size:13px; padding:4px; color:#a6adc8;"
        )
        layout.addWidget(self.summary_label)

        # Close
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedHeight(32)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load_data(self):
        """Generate buildings with current size class; collect & display combustibles."""
        from models.building import Building

        facility_name = self._facility_name
        ftype = self._mgr.get_type(facility_name)

        # Generate all buildings with the given size class
        all_buildings: list[Building] = []
        for bname in self._mgr.list_buildings(facility_name):
            if ftype == "specialized":
                b = self._mgr.load_specialized(facility_name, bname)
                all_buildings.append(b)
            else:
                bdata = self._mgr._find_building(facility_name, bname)
                params = {}
                for field, rkey in [
                    ("length", "length_range"),
                    ("width", "width_range"),
                    ("height", "height_range"),
                    ("stories", "stories_range"),
                ]:
                    r = bdata.get(rkey, [0, 0])
                    if not r:
                        vals = (0, 0, 0)
                    elif len(r) >= 3:
                        vals = (r[0], r[2], r[-1])
                    elif len(r) >= 2:
                        vals = (r[0], (r[0] + r[-1]) / 2, r[-1])
                    else:
                        vals = (r[0], r[0], r[0])
                    val = vals[self._size_idx]
                    if field == "stories":
                        val = int(round(val))
                    params[field] = val
                b = self._mgr.load_equivalent(
                    facility_name, bname, params
                )
                all_buildings.append(b)

        # Collect entries: (key, name, typ, count, loc)
        entries: list[dict] = []
        for b in all_buildings:
            bld_name = b.cn_name or b.name
            for story in b.stories:
                story_name = story.name
                # Fire-compartment-level combustibles
                for fc in story.fire_compartments:
                    loc = f"{bld_name}/{story_name}/{fc.name}"
                    for cb in fc.combustibles:
                        key = cb.get("key", "")
                        cb_def = COMBUSTIBLE_LIBRARY.get(key)
                        if cb_def is None:
                            continue
                        entries.append(dict(
                            key=key, name=cb_def.get("name", key),
                            typ="combustible", count=cb.get("count", 1), loc=loc,
                        ))
                    for sc in fc.specialized_components:
                        key = sc.get("key", "")
                        comp = SPECIALIZED_COMPONENTS.get(key)
                        if comp is None:
                            continue
                        entries.append(dict(
                            key=key, name=comp.name,
                            typ="specialized_component", count=sc.get("count", 1),
                            loc=loc,
                        ))
                # Story-level combustibles
                for cb in story.combustibles:
                    key = cb.get("key", "")
                    cb_def = COMBUSTIBLE_LIBRARY.get(key)
                    if cb_def is None:
                        continue
                    loc = f"{bld_name}/{story_name}/楼层级"
                    entries.append(dict(
                        key=key, name=cb_def.get("name", key),
                        typ="combustible", count=cb.get("count", 1), loc=loc,
                    ))
                for sc in story.specialized_components:
                    key = sc.get("key", "")
                    comp = SPECIALIZED_COMPONENTS.get(key)
                    if comp is None:
                        continue
                    loc = f"{bld_name}/{story_name}/楼层级"
                    entries.append(dict(
                        key=key, name=comp.name,
                        typ="specialized_component", count=sc.get("count", 1),
                        loc=loc,
                    ))

        # Group by (key, typ)
        groups: dict[tuple[str, str], dict] = {}
        for e in entries:
            gk = (e["key"], e["typ"])
            if gk not in groups:
                groups[gk] = dict(
                    name=e["name"], key=e["key"], typ=e["typ"],
                    total=0, locs=set(),
                )
            g = groups[gk]
            cnt = e["count"]
            g["total"] += cnt if isinstance(cnt, (int, float)) else 0
            g["locs"].add(e["loc"])

        # Sort: combustibles first, then SC
        sorted_groups = sorted(
            groups.values(),
            key=lambda g: (1 if g["typ"] == "specialized_component" else 0, g["key"]),
        )

        # Populate table
        self.table.setRowCount(len(sorted_groups))
        for i, g in enumerate(sorted_groups):
            self.table.setItem(i, 0, QTableWidgetItem(g["name"]))
            type_label = "可燃物" if g["typ"] == "combustible" else "组件"
            self.table.setItem(i, 1, QTableWidgetItem(type_label))
            self.table.setItem(i, 2, QTableWidgetItem(str(g["total"])))
            locs_str = "\n".join(sorted(g["locs"]))
            self.table.setItem(i, 3, QTableWidgetItem(locs_str))

        self.table.resizeColumnsToContents()

        # Summary
        n_comb = sum(1 for g in sorted_groups if g["typ"] == "combustible")
        n_sc = sum(1 for g in sorted_groups if g["typ"] == "specialized_component")
        total = sum(g["total"] for g in sorted_groups)
        self.summary_label.setText(
            f"合计：{n_comb} 种可燃物 + {n_sc} 种组件, 共 {total} 件"
        )
