
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
    QGridLayout, QScrollArea, QWidget, QPlainTextEdit,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from models.combustibles import (
    CombustibleManager, Combustible, DistributionMethod, SPECIALIZED_COMPONENTS,
)
from models.materials import COMBUSTIBLE_LIBRARY
from models.facility import FacilityManager

# Wall identifiers for the 4 exterior walls
WALL_IDS = ["x_min", "x_max", "y_min", "y_max"]
WALL_LABELS = {"x_min": "X- (西墙)", "x_max": "X+ (东墙)", "y_min": "Y- (南墙)", "y_max": "Y+ (北墙)"}

# ============================================================
# 开口编辑对话框
# ============================================================
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

        self.result_model = BuildingGroup(name=bname, buildings=buildings)
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
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["名称", "类型", "总数量", "出现位置", "组成部件"]
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
        from models.building import Building, BuildingGroup
        from models.parameter_engine import ParameterEngine

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
            # Parts summary for specialized components
            parts = ""
            if g["typ"] == "specialized_component":
                comp = SPECIALIZED_COMPONENTS.get(g["key"])
                if comp and comp.parts:
                    seen: dict[str, int] = {}
                    for p in comp.parts:
                        mk = p.material_key
                        label = COMBUSTIBLE_LIBRARY.get(mk, {}).get("name", mk)
                        seen[label] = seen.get(label, 0) + 1
                    parts = "、".join(
                        f"{name}({count})" if count > 1 else name
                        for name, count in sorted(seen.items())
                    )

            self.table.setItem(i, 0, QTableWidgetItem(g["name"]))
            type_label = "可燃物" if g["typ"] == "combustible" else "组件"
            self.table.setItem(i, 1, QTableWidgetItem(type_label))
            self.table.setItem(i, 2, QTableWidgetItem(str(g["total"])))
            locs_str = "\n".join(sorted(g["locs"]))
            self.table.setItem(i, 3, QTableWidgetItem(locs_str))
            self.table.setItem(i, 4, QTableWidgetItem(parts))

        self.table.resizeColumnsToContents()

        # Summary
        n_comb = sum(1 for g in sorted_groups if g["typ"] == "combustible")
        n_sc = sum(1 for g in sorted_groups if g["typ"] == "specialized_component")
        total = sum(g["total"] for g in sorted_groups)
        self.summary_label.setText(
            f"合计：{n_comb} 种可燃物 + {n_sc} 种组件, 共 {total} 件"
        )
