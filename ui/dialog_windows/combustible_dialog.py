#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dialog module extracted from ui.dialogs."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDoubleSpinBox, QComboBox, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QHeaderView, QGroupBox, QSpinBox, QCheckBox, QMessageBox,
)
from PySide6.QtCore import Signal
from models.combustibles import CombustibleManager, DistributionMethod
from models.materials import COMBUSTIBLE_LIBRARY

class CombustibleDialog(QDialog):
    """可燃物管理对话框"""
    data_changed = Signal()

    def __init__(self, manager: CombustibleManager,
                 room_length: float, room_width: float,
                 wall_thickness: float = 0.5, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.room_length = room_length
        self.room_width = room_width
        self.wall_thickness = wall_thickness
        self.setWindowTitle("🔥 可燃物管理")
        self.setMinimumSize(800, 600)
        self._build_ui()
        self._refresh_table()


    def _build_ui(self):
        root = QVBoxLayout(self)

        # ── 生成器区域 ───────────────────────────────────
        gen_group = QGroupBox("批量生成")
        gen_layout = QFormLayout(gen_group)

        self.preset_combo = QComboBox()
        for key, val in COMBUSTIBLE_LIBRARY.items():
            if key.startswith("_") or "name" not in val:
                continue
            self.preset_combo.addItem(
                f"{val['name']} ({val['length']}×{val['width']}×{val['height']}m, "
                f"{val['hrrpua']}kW/m²)", key)
        gen_layout.addRow("可燃物类型:", self.preset_combo)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 200)
        self.count_spin.setValue(5)
        gen_layout.addRow("数量:", self.count_spin)

        self.method_combo = QComboBox()
        for m in DistributionMethod:
            self.method_combo.addItem(m.value, m)
        gen_layout.addRow("分布方式:", self.method_combo)

        self.seed_check = QCheckBox("固定随机种子")
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 99999)
        self.seed_spin.setValue(42)
        self.seed_spin.setEnabled(False)
        self.seed_check.toggled.connect(self.seed_spin.setEnabled)
        seed_row = QHBoxLayout()
        seed_row.addWidget(self.seed_check)
        seed_row.addWidget(self.seed_spin)
        gen_layout.addRow("种子:", seed_row)

        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0.1, 5.0)
        self.margin_spin.setValue(0.3)
        self.margin_spin.setSuffix(" m")
        gen_layout.addRow("离墙间距:", self.margin_spin)

        btn_row = QHBoxLayout()
        gen_btn = QPushButton("🎲 生成")
        gen_btn.clicked.connect(self._generate)
        clear_btn = QPushButton("🗑 全部清除")
        clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(gen_btn)
        btn_row.addWidget(clear_btn)
        gen_layout.addRow(btn_row)

        root.addWidget(gen_group)

        # ── 列表区域 ────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "名称", "X", "Y", "Z", "尺寸", "HRRPUA", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        root.addWidget(self.table)

        # ── 底部 ────────────────────────────────────────
        info = QLabel(
            f"房间内部: {self.room_length:.1f} × {self.room_width:.1f} m  |  "
            f"当前 {len(self.manager.items)} 个可燃物")
        self.info_label = info
        root.addWidget(info)

        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        root.addWidget(ok_btn)

    def _generate(self):
        key = self.preset_combo.currentData()
        count = self.count_spin.value()
        method = self.method_combo.currentData()
        seed = self.seed_spin.value() if self.seed_check.isChecked() else None

        new_items = self.manager.generate(
            preset_key=key, count=count, method=method,
            room_length=self.room_length, room_width=self.room_width,
            wall_thickness=self.wall_thickness,
            margin=self.margin_spin.value(), seed=seed)

        overlaps = self.manager.check_overlaps()
        msg = f"已生成 {len(new_items)} 个 {COMBUSTIBLE_LIBRARY[key]['name']}"
        if overlaps:
            msg += f"\n⚠ 存在 {len(overlaps)} 对重叠"
        QMessageBox.information(self, "生成完成", msg)
        self._refresh_table()
        self.data_changed.emit()

    def _clear_all(self):
        self.manager.clear()
        self._refresh_table()
        self.data_changed.emit()

    def _remove_item(self, item_id):
        self.manager.remove(item_id)
        self._refresh_table()
        self.data_changed.emit()

    def _refresh_table(self):
        self.table.setRowCount(len(self.manager.items))
        for row, cb in enumerate(self.manager.items):
            self.table.setItem(row, 0, QTableWidgetItem(cb.id))
            self.table.setItem(row, 1, QTableWidgetItem(cb.name))
            self.table.setItem(row, 2, QTableWidgetItem(f"{cb.x:.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{cb.y:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{cb.z:.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem(
                f"{cb.length}×{cb.width}×{cb.height}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{cb.hrrpua}"))
            del_btn = QPushButton("删除")
            del_btn.clicked.connect(lambda _, cid=cb.id: self._remove_item(cid))
            self.table.setCellWidget(row, 7, del_btn)

        self.info_label.setText(
            f"房间内部: {self.room_length:.1f} × {self.room_width:.1f} m  |  "
            f"当前 {len(self.manager.items)} 个可燃物")
