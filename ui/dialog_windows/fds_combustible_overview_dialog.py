#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only combustible overview for an FDS facility model."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHBoxLayout, QHeaderView,
)
from models.materials import material_display_name


def _fmt(value, spec):
    if value is None:
        return "—"
    return format(value, spec)


class FdsCombustibleOverviewDialog(QDialog):
    """Read-only combustible overview parsed from a reference FDS file."""

    def __init__(self, parent=None, facility_cn="", rows=None):
        super().__init__(parent)
        self._facility_cn = facility_cn or "设施"
        self._rows = list(rows or [])
        self.setWindowTitle(f"设施可燃物概览（FDS） — {self._facility_cn}")
        self.setMinimumSize(1120, 560)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel(f"<b>{self._facility_cn}</b>")
        header.setStyleSheet("font-size:16px; padding:8px;")
        layout.addWidget(header)

        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels(
            [
                "材料名称",
                "燃料",
                "密度(kg/m³)",
                "导热系数(W/m·K)",
                "比热(kJ/kg·K)",
                "发射率",
                "燃烧热(MJ/kg)",
                "单位面积热释放(kW/m²)",
                "点燃温度(°C)",
                "厚度(m)",
                "构件数量",
                "体积(m³)",
            ]
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
            self.table.setItem(
                i, 0, QTableWidgetItem(material_display_name(row.get("material")))
            )
            hoc = row.get("heat_of_combustion")
            values = [
                row.get("fuel") or "—",
                row.get("density"),
                row.get("conductivity"),
                row.get("specific_heat"),
                row.get("emissivity"),
                hoc / 1000.0 if hoc is not None else None,
                row.get("hrrpuv"),
                row.get("ignition_temperature"),
                row.get("thickness"),
                row.get("boxes", 0),
                row.get("volume"),
            ]
            for column, value in enumerate(values, start=1):
                if value is None:
                    text = "—"
                elif isinstance(value, str):
                    text = value or "—"
                elif column in (10,):
                    text = str(value)
                elif column == 11:
                    text = f"{float(value):,.1f}"
                elif column in (7,):
                    text = f"{float(value):,.1f}"
                else:
                    text = f"{float(value):g}"
                self.table.setItem(i, column, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()

        if rows:
            total_boxes = sum(r.get("boxes", 0) for r in rows)
            total_volume = sum(r.get("volume", 0.0) for r in rows)
            self.summary_label.setText(
                f"合计：{len(rows)} 类可燃材料，{total_boxes} 个可燃障碍盒"
                f"（总体积 {total_volume:,.1f} m³）"
            )
        else:
            self.summary_label.setText("未定义可燃物。")
