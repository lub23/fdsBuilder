
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : dialogs.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : Dialog windows for building model configuration
'''

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDoubleSpinBox, QComboBox,
    QLabel, QDialogButtonBox, QTableWidget, QTableWidgetItem, QPushButton,
    QHBoxLayout, QHeaderView, QGroupBox, QSpinBox, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from models.combustibles import (
    CombustibleManager, Combustible, DistributionMethod,
    COMBUSTIBLE_PRESETS
)

# ============================================================
# 开口编辑对话框
# ============================================================
class OpeningDialog(QDialog):
    """开口编辑对话框"""
    
    def __init__(self, parent=None, opening=None, walls=None):
        super().__init__(parent)
        self.opening = opening or {}
        self.walls = walls or []
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        self.setWindowTitle("编辑开口")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # 所属墙体
        self.wall_combo = QComboBox()
        for i, w in enumerate(self.walls):
            name = w.get("name", f"墙体{i}")
            is_ext = "外墙" if w.get("is_external") else "内墙"
            self.wall_combo.addItem(f"{i}: {name} ({is_ext})", i)
        form.addRow("所属墙体:", self.wall_combo)
        
        # 类型
        self.type_combo = QComboBox()
        self.type_combo.addItems(["door", "window"])
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        form.addRow("类型:", self.type_combo)
        
        # 沿墙位置 (0-1)
        self.position_spin = QDoubleSpinBox()
        self.position_spin.setRange(0, 1)
        self.position_spin.setDecimals(2)
        self.position_spin.setSingleStep(0.1)
        self.position_spin.setValue(0.5)
        form.addRow("沿墙位置 (0-1):", self.position_spin)
        
        # 宽度
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.1, 50)
        self.width_spin.setDecimals(2)
        self.width_spin.setSuffix(" m")
        self.width_spin.setValue(2.0)
        form.addRow("宽度:", self.width_spin)
        
        # 高度
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.1, 20)
        self.height_spin.setDecimals(2)
        self.height_spin.setSuffix(" m")
        self.height_spin.setValue(2.0)
        form.addRow("高度:", self.height_spin)
        
        # 底部高度
        self.z_bottom_label = QLabel("底部高度:")
        self.z_bottom_spin = QDoubleSpinBox()
        self.z_bottom_spin.setRange(0, 20)
        self.z_bottom_spin.setDecimals(2)
        self.z_bottom_spin.setSuffix(" m")
        self.z_bottom_spin.setValue(0)
        form.addRow(self.z_bottom_label, self.z_bottom_spin)
        
        layout.addLayout(form)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def on_type_changed(self, type_name):
        is_window = type_name == "window"
        self.z_bottom_spin.setValue(1.0 if is_window else 0)
    
    def load_data(self):
        if self.opening:
            idx = self.opening.get("wall_index", 0)
            self.wall_combo.setCurrentIndex(min(idx, self.wall_combo.count()-1))
            self.type_combo.setCurrentText(self.opening.get("type", "door"))
            self.position_spin.setValue(self.opening.get("position", 0.5))
            self.width_spin.setValue(self.opening.get("width", 2.0))
            self.height_spin.setValue(self.opening.get("height", 2.0))
            self.z_bottom_spin.setValue(self.opening.get("z_bottom", 0))
    
    def get_data(self) -> dict:
        return {
            "wall_index": self.wall_combo.currentData(),
            "type": self.type_combo.currentText(),
            "position": self.position_spin.value(),
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
            "z_bottom": self.z_bottom_spin.value()
        }


class WallDialog(QDialog):
    """墙体编辑对话框"""
    
    def __init__(self, parent=None, wall=None, is_external=False):
        super().__init__(parent)
        self.wall = wall or {}
        self.is_external = is_external
        self.setWindowTitle("编辑外墙" if is_external else "编辑内墙")
        self.setMinimumWidth(350)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # 名称
        self.name_edit = QLineEdit(self.wall.get('name', ''))
        form.addRow("名称:", self.name_edit)
        
        self.x1_spin = QDoubleSpinBox()
        self.x1_spin.setRange(0, 500)
        self.x1_spin.setDecimals(2)
        self.x1_spin.setValue(self.wall.get('x1', 0))
        self.x1_spin.setSuffix(" m")
        form.addRow("起点 X:", self.x1_spin)
        
        self.y1_spin = QDoubleSpinBox()
        self.y1_spin.setRange(0, 500)
        self.y1_spin.setDecimals(2)
        self.y1_spin.setValue(self.wall.get('y1', 0))
        self.y1_spin.setSuffix(" m")
        form.addRow("起点 Y:", self.y1_spin)
        
        self.x2_spin = QDoubleSpinBox()
        self.x2_spin.setRange(0, 500)
        self.x2_spin.setDecimals(2)
        self.x2_spin.setValue(self.wall.get('x2', 5))
        self.x2_spin.setSuffix(" m")
        form.addRow("终点 X:", self.x2_spin)
        
        self.y2_spin = QDoubleSpinBox()
        self.y2_spin.setRange(0, 500)
        self.y2_spin.setDecimals(2)
        self.y2_spin.setValue(self.wall.get('y2', 0))
        self.y2_spin.setSuffix(" m")
        form.addRow("终点 Y:", self.y2_spin)
        
        self.thick_spin = QDoubleSpinBox()
        self.thick_spin.setRange(0.05, 1.0)
        self.thick_spin.setDecimals(2)
        self.thick_spin.setValue(self.wall.get('thickness', 0.24))
        self.thick_spin.setSuffix(" m")
        form.addRow("墙厚:", self.thick_spin)
        
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.5, 20)
        self.height_spin.setDecimals(2)
        self.height_spin.setValue(self.wall.get('height', 3.0))
        self.height_spin.setSuffix(" m")
        form.addRow("高度:", self.height_spin)
        
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_data(self) -> dict:
        return {
            'name': self.name_edit.text(),
            'x1': self.x1_spin.value(),
            'y1': self.y1_spin.value(),
            'x2': self.x2_spin.value(),
            'y2': self.y2_spin.value(),
            'thickness': self.thick_spin.value(),
            'height': self.height_spin.value(),
            'is_external': self.is_external
        }

# ============================================================
# 热源时间曲线编辑对话框
# ============================================================
class RampEditorDialog(QDialog):
    """热源时间曲线编辑器"""
    
    def __init__(self, parent=None, points=None):
        super().__init__(parent)
        self.points = points or [(0, 0.0), (100, 1.0), (500, 1.0)]
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        self.setWindowTitle("编辑时间曲线")
        self.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(self)
        
        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["时间 (s)", "系数 (0-1)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton("添加点")
        add_btn.setObjectName("secondaryBtn")
        add_btn.clicked.connect(self.add_point)
        btn_layout.addWidget(add_btn)
        
        remove_btn = QPushButton("删除点")
        remove_btn.setObjectName("dangerBtn")
        remove_btn.clicked.connect(self.remove_point)
        btn_layout.addWidget(remove_btn)
        
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
        # 确认按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_data(self):
        self.table.setRowCount(len(self.points))
        for i, (t, f) in enumerate(self.points):
            self.table.setItem(i, 0, QTableWidgetItem(str(t)))
            self.table.setItem(i, 1, QTableWidgetItem(str(f)))
    
    def add_point(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem("0"))
        self.table.setItem(row, 1, QTableWidgetItem("1.0"))
    
    def remove_point(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)
    
    def get_data(self) -> list:
        points = []
        for i in range(self.table.rowCount()):
            try:
                t = float(self.table.item(i, 0).text())
                f = float(self.table.item(i, 1).text())
                points.append((t, f))
            except:
                pass
        return sorted(points, key=lambda x: x[0])



class CombustibleDialog(QDialog):
    """可燃物管理对话框"""
    data_changed = Signal()

    def __init__(self, manager: CombustibleManager,
                 room_length: float, room_width: float,
                 wall_thickness: float = 0.2, parent=None):
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
        for key, val in COMBUSTIBLE_PRESETS.items():
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
        msg = f"已生成 {len(new_items)} 个 {COMBUSTIBLE_PRESETS[key]['name']}"
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