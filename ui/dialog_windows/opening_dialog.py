#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Dialog module extracted from ui.dialogs."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDoubleSpinBox, QComboBox, QDialogButtonBox,
)

WALL_IDS = ["x_min", "x_max", "y_min", "y_max"]
WALL_LABELS = {"x_min": "X- (西墙)", "x_max": "X+ (东墙)", "y_min": "Y- (南墙)", "y_max": "Y+ (北墙)"}

class OpeningDialog(QDialog):
    """开口编辑对话框 — 使用 Opening(wall, type, boundary) 格式"""

    def __init__(self, parent=None, opening=None, walls=None):
        """
        Args:
            opening: Opening object or dict with {wall, type, boundary}.
            walls:   Ignored (kept for call-site compat); wall is now a string id.
        """
        super().__init__(parent)
        self.opening = opening
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        self.setWindowTitle("编辑开口")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 所属墙体 (string id)
        self.wall_combo = QComboBox()
        for wid in WALL_IDS:
            self.wall_combo.addItem(WALL_LABELS[wid], wid)
        form.addRow("所属墙:", self.wall_combo)

        # 类型
        self.type_combo = QComboBox()
        self.type_combo.addItems(["door", "window", "opening", "loading_dock", "ribbon_window"])
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        form.addRow("类型:", self.type_combo)

        # 偏移(m) — w_offset: boundary[0]
        self.w_offset_spin = QDoubleSpinBox()
        self.w_offset_spin.setRange(-500, 500)
        self.w_offset_spin.setDecimals(2)
        self.w_offset_spin.setSuffix(" m")
        self.w_offset_spin.setValue(0.0)
        form.addRow("偏移(m):", self.w_offset_spin)

        # 宽度 — boundary[1]
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.1, 50)
        self.width_spin.setDecimals(2)
        self.width_spin.setSuffix(" m")
        self.width_spin.setValue(2.0)
        form.addRow("宽度:", self.width_spin)

        # h_offset — boundary[2]
        self.h_offset_spin = QDoubleSpinBox()
        self.h_offset_spin.setRange(0, 20)
        self.h_offset_spin.setDecimals(2)
        self.h_offset_spin.setSuffix(" m")
        self.h_offset_spin.setValue(0)
        form.addRow("高度偏移(m):", self.h_offset_spin)

        # 高度 — boundary[3]
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.1, 20)
        self.height_spin.setDecimals(2)
        self.height_spin.setSuffix(" m")
        self.height_spin.setValue(2.0)
        form.addRow("高度:", self.height_spin)

        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def on_type_changed(self, type_name):
        is_window = type_name == "window"
        self.h_offset_spin.setValue(1.0 if is_window else 0)

    def load_data(self):
        from models.building import Opening
        o = self.opening
        if o is None:
            return
        if isinstance(o, Opening):
            wall, tp, bd = o.wall, o.type, o.boundary
        elif isinstance(o, dict):
            wall = o.get("wall", "x_min")
            tp = o.get("type", "door")
            bd = o.get("boundary", [0, 2, 0, 2])
        else:
            return
        idx = WALL_IDS.index(wall) if wall in WALL_IDS else 0
        self.wall_combo.setCurrentIndex(idx)
        self.type_combo.setCurrentText(tp)
        self.w_offset_spin.setValue(bd[0])
        self.width_spin.setValue(bd[1])
        self.h_offset_spin.setValue(bd[2])
        self.height_spin.setValue(bd[3])

    def get_data(self):
        """Return an Opening object."""
        from models.building import Opening
        return Opening(
            wall=self.wall_combo.currentData(),
            type=self.type_combo.currentText(),
            boundary=[
                self.w_offset_spin.value(),
                self.width_spin.value(),
                self.h_offset_spin.value(),
                self.height_spin.value(),
            ],
        )
