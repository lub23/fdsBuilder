#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dialog module extracted from ui.dialogs."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QHeaderView, QSpinBox, QWidget,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush,
)

class _CompartmentCanvas(QWidget):
    """Simple QPainter canvas showing fire compartment boundaries on a floor plan."""
        # ══ 可燃物 ══
    COLORS = [
        QColor("#a6e3a1"), QColor("#89b4fa"), QColor("#f9e2af"),
        QColor("#cba6f7"), QColor("#f38ba8"), QColor("#94e2d5"),
        QColor("#fab387"), QColor("#74c7ec"),
    ]

    def __init__(self, parent, length, width):
        super().__init__(parent)
        self._L = length
        self._W = width
        self._compartments = []
        self.setMinimumHeight(160)

    def set_compartments(self, compartments):
        self._compartments = compartments
        self.update()

    def paintEvent(self, event):
        if self._L <= 0 or self._W <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width() - 20, self.height() - 20
        scale = min(w / self._L, h / self._W)
        ox = (self.width() - self._L * scale) / 2
        oy = (self.height() - self._W * scale) / 2

        # Building outline
        p.setPen(QPen(QColor("#cdd6f4"), 2))
        p.setBrush(QBrush(QColor("#313244")))
        p.drawRect(int(ox), int(oy), int(self._L * scale), int(self._W * scale))

        # Compartments
        for i, fc in enumerate(self._compartments):
            color = self.COLORS[i % len(self.COLORS)]
            color.setAlpha(60)
            x1 = ox + fc.get("x_min", 0) * scale
            y1 = oy + fc.get("y_min", 0) * scale
            x2 = ox + fc.get("x_max", self._L) * scale
            y2 = oy + fc.get("y_max", self._W) * scale
            p.setBrush(QBrush(color))
            p.setPen(QPen(self.COLORS[i % len(self.COLORS)], 2))
            p.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
            # Label
            p.setPen(QColor("#cdd6f4"))
            p.drawText(int(x1 + 4), int(y1 + 14), fc.get("name", f"FC{i+1}"))
        p.end()


class FireCompartmentDialog(QDialog):
    """防火分区可视化编辑对话框"""
    def __init__(self, parent=None, compartments=None, building_length=20,
                 building_width=15, wall_thickness=0.5):
        super().__init__(parent)
        self.setWindowTitle("防火分区编辑")
        self.setMinimumSize(600, 450)
        self._L = building_length
        self._W = building_width
        self._t = wall_thickness
        self._compartments = list(compartments or [])
        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"建筑平面: {self._L:.1f} x {self._W:.1f} m — "
            "拖动分界线或直接编辑XY范围来划分防火分区"))
        # Floor plan canvas
        self._canvas = _CompartmentCanvas(self, self._L, self._W)
        layout.addWidget(self._canvas)
        # Table of compartments
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "名称", "X起", "X止", "Y起", "Y止", "防火墙厚度"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        # Buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("添加分区")
        add_btn.setStyleSheet(
            "QPushButton{background:#a6e3a1;color:#1e1e2e;font-weight:bold;"
            "padding:4px 10px;border-radius:3px}")
        add_btn.clicked.connect(self._add_compartment)
        btn_row.addWidget(add_btn)
        split_x_btn = QPushButton("沿X等分")
        split_x_btn.setStyleSheet(
            "QPushButton{background:#89b4fa;color:#1e1e2e;font-weight:bold;"
            "padding:4px 10px;border-radius:3px}")
        split_x_btn.clicked.connect(lambda: self._auto_split("x"))
        btn_row.addWidget(split_x_btn)

        split_y_btn = QPushButton("沿Y等分")
        split_y_btn.setStyleSheet(
            "QPushButton{background:#89b4fa;color:#1e1e2e;font-weight:bold;"
            "padding:4px 10px;border-radius:3px}")
        split_y_btn.clicked.connect(lambda: self._auto_split("y"))
        btn_row.addWidget(split_y_btn)

        del_btn = QPushButton("删除选中")
        del_btn.setStyleSheet(
            "QPushButton{background:#f38ba8;color:#1e1e2e;font-weight:bold;"
            "padding:4px 10px;border-radius:3px}")
        del_btn.clicked.connect(self._delete_compartment)
        btn_row.addWidget(del_btn)

        layout.addLayout(btn_row)

        # Split count
        split_row = QHBoxLayout()
        split_row.addWidget(QLabel("等分数量:"))
        self.split_count_spin = QSpinBox()
        self.split_count_spin.setRange(2, 10)
        self.split_count_spin.setValue(2)
        split_row.addWidget(self.split_count_spin)
        split_row.addStretch()
        layout.addLayout(split_row)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._save_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _refresh_table(self):
        self.table.setRowCount(len(self._compartments))
        for i, fc in enumerate(self._compartments):
            self.table.setItem(i, 0, QTableWidgetItem(fc.get("name", f"分区{i+1}")))
            self.table.setItem(i, 1, QTableWidgetItem(f"{fc.get('x_min', 0):.1f}"))
            self.table.setItem(i, 2, QTableWidgetItem(f"{fc.get('x_max', self._L):.1f}"))
            self.table.setItem(i, 3, QTableWidgetItem(f"{fc.get('y_min', 0):.1f}"))
            self.table.setItem(i, 4, QTableWidgetItem(f"{fc.get('y_max', self._W):.1f}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{fc.get('firewall_thickness', 0.5):.2f}"))
        self._canvas.set_compartments(self._compartments)

    def _add_compartment(self):
        idx = len(self._compartments)
        self._compartments.append({
            "id": f"FC_{idx}", "name": f"防火分区{idx+1}",
            "x_min": 0, "x_max": self._L,
            "y_min": 0, "y_max": self._W,
            "firewall_thickness": 0.5, "firewall_material": "CONCRETE",
        })
        self._refresh_table()

    def _auto_split(self, axis):
        n = self.split_count_spin.value()
        self._compartments.clear()
        for i in range(n):
            if axis == "x":
                fc = {
                    "id": f"FC_{i}", "name": f"防火分区{i+1}",
                    "x_min": round(i * self._L / n, 2),
                    "x_max": round((i + 1) * self._L / n, 2),
                    "y_min": 0, "y_max": self._W,
                    "firewall_thickness": 0.5, "firewall_material": "CONCRETE",
                }
            else:
                fc = {
                    "id": f"FC_{i}", "name": f"防火分区{i+1}",
                    "x_min": 0, "x_max": self._L,
                    "y_min": round(i * self._W / n, 2),
                    "y_max": round((i + 1) * self._W / n, 2),
                    "firewall_thickness": 0.5, "firewall_material": "CONCRETE",
                }
            self._compartments.append(fc)
        self._refresh_table()

    def _delete_compartment(self):
        row = self.table.currentRow()
        if 0 <= row < len(self._compartments):
            del self._compartments[row]
            self._refresh_table()

    def _save_and_accept(self):
        # Read back edited values from table
        for i in range(self.table.rowCount()):
            if i >= len(self._compartments):
                break
            fc = self._compartments[i]
            try:
                fc["name"] = self.table.item(i, 0).text()
                fc["x_min"] = float(self.table.item(i, 1).text())
                fc["x_max"] = float(self.table.item(i, 2).text())
                fc["y_min"] = float(self.table.item(i, 3).text())
                fc["y_max"] = float(self.table.item(i, 4).text())
                fc["firewall_thickness"] = float(self.table.item(i, 5).text())
            except (ValueError, AttributeError):
                pass
        self.accept()

    def get_compartments(self):
        from models.building import FireCompartment
        return [FireCompartment.from_dict(fc) for fc in self._compartments]
