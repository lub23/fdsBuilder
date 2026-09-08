#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dialog module extracted from ui.dialogs."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHBoxLayout, QHeaderView,
)


def _fmt(value, spec):
    if value is None:
        return "—"
    return format(value, spec)


class FdsCombustibleOverviewDialog(QDialog):
    """Read-only combustible overview parsed from a reference FDS file."""

    def __init__(self, parent=None, facility_cn="", rows=None, non_combustible_boxes=0):
        super().__init__(parent)
        self._facility_cn = facility_cn or "设施"
        self._rows = list(rows or [])
        self._non_comb = int(non_combustible_boxes)
        self.setWindowTitle(f"设施可燃物概览（FDS） — {self._facility_cn}")
        self.setMinimumSize(760, 460)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel(
            f"<b>{self._facility_cn}</b> — 参考FDS文件解析出的可燃材料"
        )
        header.setStyleSheet("font-size:16px; padding:8px;")
        layout.addWidget(header)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["材料", "燃料 (FUEL)", "燃烧热 HOC (MJ/kg)",
             "HRRPUV (kW/m²)", "障碍盒数", "体积 (m³)"]
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            "font-size:13px; padding:4px; color:#a6adc8;"
        )
        layout.addWidget(self.summary_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedHeight(32)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load_data(self):
        rows = self._rows
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(row.get("material", "")))
            self.table.setItem(i, 1, QTableWidgetItem(row.get("fuel") or "—"))
            # FDS stores HEAT_OF_COMBUSTION in kJ/kg; display as MJ/kg.
            hoc = row.get("heat_of_combustion")
            self.table.setItem(i, 2, QTableWidgetItem(_fmt(hoc / 1000.0 if hoc is not None else None, ".1f")))
            self.table.setItem(i, 3, QTableWidgetItem(_fmt(row.get("hrrpuv"), ".0f")))
            self.table.setItem(i, 4, QTableWidgetItem(str(row.get("boxes", 0))))
            self.table.setItem(i, 5, QTableWidgetItem(_fmt(row.get("volume"), ",.1f")))
        self.table.resizeColumnsToContents()

        if rows:
            total_boxes = sum(r.get("boxes", 0) for r in rows)
            total_volume = sum(r.get("volume", 0.0) for r in rows)
            self.summary_label.setText(
                f"合计：{len(rows)} 类可燃材料，{total_boxes} 个可燃障碍盒"
                f"（总体积 {total_volume:,.1f} m³），{self._non_comb} 个不可燃障碍盒"
            )
        else:
            self.summary_label.setText(
                f"该FDS文件未定义可燃材料（COMBUSTIBLE MATL），{self._non_comb} 个"
                "障碍盒均为不可燃，火源通过点热源/边界条件实现。"
            )
