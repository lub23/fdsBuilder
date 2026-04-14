
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : dialogs.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 1.0
@Desc  : Dialog windows for building model configuration
'''
from typing import Tuple, Dict
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDoubleSpinBox, QComboBox,
    QLabel, QDialogButtonBox, QTableWidget, QTableWidgetItem, QPushButton,
    QHBoxLayout, QHeaderView, QGroupBox, QSpinBox, QCheckBox, QMessageBox,
    QGridLayout, QTreeWidget, QTreeWidgetItem, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from models.combustibles import (
    CombustibleManager, Combustible, DistributionMethod
)
from models.materials import COMBUSTIBLE_LIBRARY
from models.facility import FacilityManager

# Wall name choices (previously in models.facility, now defined locally)
WALL_NAMES = ["南墙", "北墙", "东墙", "西墙", "均匀分布"]

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
        for key, val in COMBUSTIBLE_LIBRARY.items():
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
        

class FloorSlabHoleDialog(QDialog):
    """楼梯口编辑对话框"""

    def __init__(self, parent=None, max_length=20.0, max_width=15.0, hole=None):
        super().__init__(parent)
        self.setWindowTitle("编辑楼梯口")
        self.setMinimumWidth(350)
        self.hole = hole or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(self.hole.get("name", "楼梯间"))
        form.addRow("名称:", self.name_edit)

        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(0, max_length)
        self.x_spin.setDecimals(2)
        self.x_spin.setSuffix(" m")
        self.x_spin.setValue(self.hole.get("x", 1.0))
        form.addRow("X 位置:", self.x_spin)

        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0, max_width)
        self.y_spin.setDecimals(2)
        self.y_spin.setSuffix(" m")
        self.y_spin.setValue(self.hole.get("y", 1.0))
        form.addRow("Y 位置:", self.y_spin)

        self.len_spin = QDoubleSpinBox()
        self.len_spin.setRange(0.1, max_length)
        self.len_spin.setDecimals(2)
        self.len_spin.setSuffix(" m")
        self.len_spin.setValue(self.hole.get("length", 2.0))
        form.addRow("长度:", self.len_spin)

        self.wid_spin = QDoubleSpinBox()
        self.wid_spin.setRange(0.1, max_width)
        self.wid_spin.setDecimals(2)
        self.wid_spin.setSuffix(" m")
        self.wid_spin.setValue(self.hole.get("width", 2.0))
        form.addRow("宽度:", self.wid_spin)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text(),
            "x": self.x_spin.value(),
            "y": self.y_spin.value(),
            "length": self.len_spin.value(),
            "width": self.wid_spin.value(),
        }
    

class BatchOpeningDialog(QDialog):
    """批量生成开口（门/窗/楼梯口）"""

    def __init__(self, parent=None, walls=None, model=None, viewer=None):
        super().__init__(parent)
        self.walls = walls or []
        self.model = model
        self._result = []
        self.setWindowTitle("批量生成开口")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QGridLayout()
        form.setSpacing(4)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)

        # 类型
        form.addWidget(QLabel("类型:"), 0, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["door", "window", "楼梯口"])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        form.addWidget(self.type_combo, 0, 1)

        # 所属
        form.addWidget(QLabel("所属:"), 0, 2)
        self.wall_combo = QComboBox()
        self._fill_wall_combo()
        form.addWidget(self.wall_combo, 0, 3)

        # 数量
        form.addWidget(QLabel("数量:"), 1, 0)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(3)
        self.count_spin.valueChanged.connect(self._update_preview)
        form.addWidget(self.count_spin, 1, 1)

        # 边距
        form.addWidget(QLabel("端距:"), 1, 2)
        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0, 20)
        self.margin_spin.setValue(0.5)
        self.margin_spin.setSuffix(" m")
        self.margin_spin.valueChanged.connect(self._update_preview)
        form.addWidget(self.margin_spin, 1, 3)

        # 宽高
        form.addWidget(QLabel("宽:"), 2, 0)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.1, 50)
        self.width_spin.setValue(1.5)
        self.width_spin.setSuffix(" m")
        self.width_spin.valueChanged.connect(self._update_preview)
        form.addWidget(self.width_spin, 2, 1)

        form.addWidget(QLabel("高:"), 2, 2)
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(0.1, 20)
        self.height_spin.setValue(2.0)
        self.height_spin.setSuffix(" m")
        self.height_spin.valueChanged.connect(self._update_preview)
        form.addWidget(self.height_spin, 2, 3)

        # 底高
        form.addWidget(QLabel("底高:"), 3, 0)
        self.z_spin = QDoubleSpinBox()
        self.z_spin.setRange(0, 20)
        self.z_spin.setValue(0)
        self.z_spin.setSuffix(" m")
        self.z_spin.valueChanged.connect(self._update_preview)
        form.addWidget(self.z_spin, 3, 1)

        # 楼梯口的名称
        form.addWidget(QLabel("名称:"), 3, 2)
        self.name_edit = QLineEdit("楼梯口")
        form.addWidget(self.name_edit, 3, 3)

        layout.addLayout(form)

        # 状态
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#a6adc8; font-size:12px;")
        layout.addWidget(self.status_label)

        # 预览表
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(4)
        self.preview_table.setHorizontalHeaderLabels(
            ["序号", "位置/XY", "长×宽", "底高"])
        self.preview_table.setMaximumHeight(150)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.preview_table)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.name_edit.setStyleSheet("QLineEdit{background:#313244;color:#6c7086;}")
        self._on_type_changed(self.type_combo.currentText())
        self._update_preview()

    def _fill_wall_combo(self):
        self.wall_combo.clear()
        for i, w in enumerate(self.walls):
            name = w.get("name", f"墙{i}")
            tag = "外" if w.get("is_external") else "内"
            self.wall_combo.addItem(f"{name}({tag})", i)
        self.wall_combo.currentIndexChanged.connect(self._update_preview)

    def _on_type_changed(self, t):
        is_hole = (t == "楼梯口")
        # 所属：禁用+灰色
        self.wall_combo.setEnabled(not is_hole)
        if is_hole:
            self.wall_combo.setStyleSheet("QComboBox{background:#313244;color:#6c7086;}")
        else:
            self.wall_combo.setStyleSheet("")
        # 底高：禁用+灰色
        self.z_spin.setEnabled(not is_hole)
        if is_hole:
            self.z_spin.setStyleSheet("QDoubleSpinBox{background:#313244;color:#6c7086;}")
        else:
            self.z_spin.setStyleSheet("")
        # 名称：启用+正常
        self.name_edit.setEnabled(is_hole)
        if is_hole:
            self.name_edit.setStyleSheet("")
        else:
            self.name_edit.setStyleSheet("QLineEdit{background:#313244;color:#6c7086;}")
        
        if t == "window":
            self.z_spin.setValue(1.0)
        elif t == "door":
            self.z_spin.setValue(0.0)
        self._update_preview()

    def _get_wall_length(self):
        idx = self.wall_combo.currentData()
        if idx is None or idx >= len(self.walls):
            return 0
        w = self.walls[idx]
        return ((w["x2"] - w["x1"])**2 + (w["y2"] - w["y1"])**2)**0.5

    def _update_preview(self):
        is_hole = self.type_combo.currentText() == "楼梯口"
        count = self.count_spin.value()
        o_w = self.width_spin.value()
        o_h = self.height_spin.value()
        margin = self.margin_spin.value()

        if is_hole:
            # 楼梯口：沿X方向等距分布
            L = self.model.length if self.model else 20
            W = self.model.width if self.model else 15
            usable = L - 2 * margin
            total_w = count * o_w
            if total_w > usable or usable <= 0:
                self.status_label.setText(f"⚠️ 放不下！可用{usable:.1f}m")
                self.status_label.setStyleSheet("color:#f38ba8;")
                self._result = []
                self.preview_table.setRowCount(0)
                return

            spacing = (usable - total_w) / (count + 1) if count > 0 else 0
            y_pos = (W - o_h) / 2  # 居中

            self._result = []
            self.preview_table.setRowCount(count)
            for i in range(count):
                x = margin + spacing * (i + 1) + o_w * i
                item = {
                    "_kind": "hole",
                    "name": self.name_edit.text() or f"洞口{i+1}",
                    "x": round(x, 2), "y": round(y_pos, 2),
                    "length": o_w, "width": o_h,
                }
                self._result.append(item)
                self.preview_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
                self.preview_table.setItem(
                    i, 1, QTableWidgetItem(f"({x:.1f},{y_pos:.1f})"))
                self.preview_table.setItem(
                    i, 2, QTableWidgetItem(f"{o_w:.1f}×{o_h:.1f}"))
                self.preview_table.setItem(i, 3, QTableWidgetItem("-"))

            self.status_label.setText(
                f"✅ {count}个楼梯口 | 间距{spacing:.2f}m")
            self.status_label.setStyleSheet("color:#a6e3a1;")
        else:
            # 门窗：沿墙等距
            wall_len = self._get_wall_length()
            usable = wall_len - 2 * margin
            total_w = count * o_w
            if total_w > usable or usable <= 0:
                self.status_label.setText(
                    f"⚠️ 墙长{wall_len:.1f}m 放不下{count}个")
                self.status_label.setStyleSheet("color:#f38ba8;")
                self._result = []
                self.preview_table.setRowCount(0)
                return

            spacing = (usable - total_w) / (count + 1) if count > 0 else 0

            self._result = []
            self.preview_table.setRowCount(count)
            for i in range(count):
                center = margin + spacing * (i + 1) + o_w * (i + 0.5)
                pos = center / wall_len
                item = {
                    "wall_index": self.wall_combo.currentData(),
                    "type": self.type_combo.currentText(),
                    "position": round(pos, 4),
                    "width": o_w, "height": o_h,
                    "z_bottom": self.z_spin.value(),
                }
                self._result.append(item)
                self.preview_table.setItem(i, 0, QTableWidgetItem(str(i+1)))
                self.preview_table.setItem(
                    i, 1, QTableWidgetItem(f"{pos:.3f}"))
                self.preview_table.setItem(
                    i, 2, QTableWidgetItem(f"{o_w:.1f}×{o_h:.1f}"))
                self.preview_table.setItem(
                    i, 3, QTableWidgetItem(f"{self.z_spin.value():.1f}"))

            self.status_label.setText(
                f"✅ 墙长{wall_len:.1f}m | {count}个 | 间距{spacing:.2f}m")
            self.status_label.setStyleSheet("color:#a6e3a1;")

    def _validate_and_accept(self):
        if not self._result:
            QMessageBox.warning(self, "错误", "无法生成，请调整参数")
            return
        self.accept()

    def get_data(self):
        return self._result
    

class BatchWallDialog(QDialog):
    """批量生成内墙"""

    def __init__(self, parent=None, model=None):
        super().__init__(parent)
        self.model = model
        self._result = []
        self.setWindowTitle("批量生成内墙")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QGridLayout()
        form.setSpacing(4)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)

        L = model.length if model else 20
        W = model.width if model else 15

        # 方向
        form.addWidget(QLabel("方向:"), 0, 0)
        self.dir_combo = QComboBox()
        self.dir_combo.addItems(["横向(东西)", "纵向(南北)"])
        self.dir_combo.currentIndexChanged.connect(self._update_preview)
        form.addWidget(self.dir_combo, 0, 1)

        # 数量
        form.addWidget(QLabel("数量:"), 0, 2)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(2)
        self.count_spin.valueChanged.connect(self._update_preview)
        form.addWidget(self.count_spin, 0, 3)

        # 墙厚
        form.addWidget(QLabel("墙厚:"), 1, 0)
        self.thick_spin = QDoubleSpinBox()
        self.thick_spin.setRange(0.05, 1.0)
        self.thick_spin.setValue(model.wall_thickness if model else 0.24)
        self.thick_spin.setSuffix(" m")
        form.addWidget(self.thick_spin, 1, 1)

        # 边距
        form.addWidget(QLabel("边距:"), 1, 2)
        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0, 50)
        self.margin_spin.setValue(1.0)
        self.margin_spin.setSuffix(" m")
        self.margin_spin.valueChanged.connect(self._update_preview)
        form.addWidget(self.margin_spin, 1, 3)

        layout.addLayout(form)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#a6adc8; font-size:12px;")
        layout.addWidget(self.status_label)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(4)
        self.preview_table.setHorizontalHeaderLabels(
            ["名称", "起点", "终点", "厚度"])
        self.preview_table.setMaximumHeight(150)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.preview_table)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_preview()

    def _update_preview(self):
        L = self.model.length if self.model else 20
        W = self.model.width if self.model else 15
        count = self.count_spin.value()
        margin = self.margin_spin.value()
        is_horizontal = self.dir_combo.currentIndex() == 0
        thick = self.thick_spin.value()

        if is_horizontal:
            # 横向墙：沿Y方向等距，墙从x=0到x=L
            usable = W - 2 * margin
        else:
            usable = L - 2 * margin

        if usable <= 0:
            self.status_label.setText("⚠️ 边距太大")
            self.status_label.setStyleSheet("color:#f38ba8;")
            self._result = []
            self.preview_table.setRowCount(0)
            return

        spacing = usable / (count + 1)

        self._result = []
        self.preview_table.setRowCount(count)
        for i in range(count):
            pos = margin + spacing * (i + 1)
            if is_horizontal:
                wall = {
                    "name": f"内墙H{i+1}",
                    "x1": 0, "y1": round(pos, 2),
                    "x2": L, "y2": round(pos, 2),
                    "thickness": thick,
                    "height": 3.0,
                }
            else:
                wall = {
                    "name": f"内墙V{i+1}",
                    "x1": round(pos, 2), "y1": 0,
                    "x2": round(pos, 2), "y2": W,
                    "thickness": thick,
                    "height": 3.0,
                }
            self._result.append(wall)
            self.preview_table.setItem(
                i, 0, QTableWidgetItem(wall["name"]))
            self.preview_table.setItem(
                i, 1, QTableWidgetItem(
                    f"({wall['x1']:.1f},{wall['y1']:.1f})"))
            self.preview_table.setItem(
                i, 2, QTableWidgetItem(
                    f"({wall['x2']:.1f},{wall['y2']:.1f})"))
            self.preview_table.setItem(
                i, 3, QTableWidgetItem(f"{thick:.2f}"))

        self.status_label.setText(
            f"✅ {count}面内墙 | 间距{spacing:.2f}m")
        self.status_label.setStyleSheet("color:#a6e3a1;")

    def _validate_and_accept(self):
        if not self._result:
            QMessageBox.warning(self, "错误", "无法生成")
            return
        self.accept()

    def get_data(self):
        return self._result


class WallOpeningManagerDialog(QDialog):
    """门窗管理对话框：左侧墙体列表，右侧该墙开口列表"""

    def __init__(self, parent=None, walls=None, openings=None, building_length=20, building_width=15):
        super().__init__(parent)
        self.setWindowTitle("门窗管理")
        self.setMinimumSize(700, 500)
        self._walls = walls or []
        self._openings = list(openings or [])
        self._L = building_length
        self._W = building_width
        self._build_ui()
        self._refresh_wall_list()

    # ── UI ────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)

        # Left: wall list
        left = QVBoxLayout()
        left.addWidget(QLabel("墙体列表"))
        self.wall_list = QTableWidget()
        self.wall_list.setColumnCount(3)
        self.wall_list.setHorizontalHeaderLabels(["名称", "类型", "长度"])
        self.wall_list.setSelectionBehavior(QTableWidget.SelectRows)
        self.wall_list.setSelectionMode(QTableWidget.SingleSelection)
        self.wall_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.wall_list.currentCellChanged.connect(self._on_wall_selected)
        left.addWidget(self.wall_list)
        root.addLayout(left, 1)
        # Right: openings for selected wall
        right = QVBoxLayout()
        right.addWidget(QLabel("该墙开口"))
        self.opening_table = QTableWidget()
        self.opening_table.setColumnCount(5)
        self.opening_table.setHorizontalHeaderLabels(["类型", "位置", "宽度", "高度", "底高"])
        self.opening_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right.addWidget(self.opening_table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("添加开口")
        add_btn.setStyleSheet(
            "QPushButton{background:#a6e3a1;color:#1e1e2e;font-weight:bold;"
            "padding:4px 10px;border-radius:3px}")
        add_btn.clicked.connect(self._add_opening)
        btn_row.addWidget(add_btn)

        edit_btn = QPushButton("编辑")
        edit_btn.setStyleSheet(
            "QPushButton{background:#89b4fa;color:#1e1e2e;font-weight:bold;"
            "padding:4px 10px;border-radius:3px}")
        edit_btn.clicked.connect(self._edit_opening)
        btn_row.addWidget(edit_btn)

        del_btn = QPushButton("删除")
        del_btn.setStyleSheet(
            "QPushButton{background:#f38ba8;color:#1e1e2e;font-weight:bold;"
            "padding:4px 10px;border-radius:3px}")
        del_btn.clicked.connect(self._delete_opening)
        btn_row.addWidget(del_btn)

        right.addLayout(btn_row)
        root.addLayout(right, 2)

        # Bottom OK/Cancel
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    def _refresh_wall_list(self):
        self.wall_list.setRowCount(len(self._walls))
        for i, w in enumerate(self._walls):
            name = w.get("name", f"墙{i}")
            if w.get("is_fire_partition"):
                wtype = "防火墙"
            elif w.get("is_external"):
                wtype = "外墙"
            else:
                wtype = "内墙"
            wlen = ((w["x2"] - w["x1"])**2 + (w["y2"] - w["y1"])**2)**0.5
            self.wall_list.setItem(i, 0, QTableWidgetItem(name))
            self.wall_list.setItem(i, 1, QTableWidgetItem(wtype))
            self.wall_list.setItem(i, 2, QTableWidgetItem(f"{wlen:.1f}m"))

    def _on_wall_selected(self, row, col, prev_row, prev_col):
        if row < 0:
            self.opening_table.setRowCount(0)
            return
        wall_openings = [o for o in self._openings if o.get("wall_index") == row]
        self.opening_table.setRowCount(len(wall_openings))
        for i, o in enumerate(wall_openings):
            self.opening_table.setItem(i, 0, QTableWidgetItem(o.get("type", "door")))
            self.opening_table.setItem(i, 1, QTableWidgetItem(f"{o.get('position', 0.5):.2f}"))
            self.opening_table.setItem(i, 2, QTableWidgetItem(f"{o.get('width', 1.0):.1f}"))
            self.opening_table.setItem(i, 3, QTableWidgetItem(f"{o.get('height', 2.0):.1f}"))
            self.opening_table.setItem(i, 4, QTableWidgetItem(f"{o.get('z_bottom', 0):.1f}"))

    def _add_opening(self):
        wi = self.wall_list.currentRow()
        if wi < 0:
            QMessageBox.warning(self, "提示", "请先选择一面墙")
            return
        dlg = OpeningDialog(self, opening={"wall_index": wi}, walls=self._walls)
        if dlg.exec() == QDialog.Accepted:
            self._openings.append(dlg.get_data())
            self._on_wall_selected(wi, 0, -1, 0)

    def _edit_opening(self):
        wi = self.wall_list.currentRow()
        oi = self.opening_table.currentRow()
        if wi < 0 or oi < 0:
            return
        wall_openings = [o for o in self._openings if o.get("wall_index") == wi]
        if oi >= len(wall_openings):
            return
        opening = wall_openings[oi]
        dlg = OpeningDialog(self, opening=opening, walls=self._walls)
        if dlg.exec() == QDialog.Accepted:
            new_data = dlg.get_data()
            # Update in-place
            idx = self._openings.index(opening)
            self._openings[idx] = new_data
            self._on_wall_selected(wi, 0, -1, 0)

    def _delete_opening(self):
        wi = self.wall_list.currentRow()
        oi = self.opening_table.currentRow()
        if wi < 0 or oi < 0:
            return
        wall_openings = [o for o in self._openings if o.get("wall_index") == wi]
        if oi < len(wall_openings):
            self._openings.remove(wall_openings[oi])
            self._on_wall_selected(wi, 0, -1, 0)

    def get_openings(self):
        return self._openings

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
                 building_width=15, wall_thickness=0.24):
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
            self.table.setItem(i, 5, QTableWidgetItem(f"{fc.get('firewall_thickness', 0.2):.2f}"))
        self._canvas.set_compartments(self._compartments)

    def _add_compartment(self):
        idx = len(self._compartments)
        self._compartments.append({
            "id": f"FC_{idx}", "name": f"防火分区{idx+1}",
            "x_min": 0, "x_max": self._L,
            "y_min": 0, "y_max": self._W,
            "firewall_thickness": 0.2, "firewall_material": "CONCRETE",
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
                    "firewall_thickness": 0.2, "firewall_material": "CONCRETE",
                }
            else:
                fc = {
                    "id": f"FC_{i}", "name": f"防火分区{i+1}",
                    "x_min": 0, "x_max": self._L,
                    "y_min": round(i * self._W / n, 2),
                    "y_max": round((i + 1) * self._W / n, 2),
                    "firewall_thickness": 0.2, "firewall_material": "CONCRETE",
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
        from models.building import Building, Story
        from models.parameter_engine import ParameterEngine

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
        from models.building import Building, BuildingGroup

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

        self.result_model = BuildingGroup(buildings=buildings)
        self.accept()

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