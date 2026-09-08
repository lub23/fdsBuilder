#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File  : facility_panel.py
@Author: Lubber
@Date  : 2026-03-19
@Version : 3.0
@Desc  : Panel with inline parameter editing, facility selection, and scene management.
         Updated for new FacilityManager API with equivalent/specialized model types.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QHBoxLayout,
    QMessageBox,
    QDialog,
    QDoubleSpinBox,
    QSpinBox,
    QGridLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QRadioButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import (
    QFont,
    QColor,
    QBrush,
    QIcon,
    QPen,
    QPainter,
    QPixmap,
)
from models.facility import FacilityManager
from models.building import BuildingGroup
from ui.styles import CollapsibleGroup, apply_button_variant

# Alias for backwards compatibility within this file
CollapsibleSection = CollapsibleGroup


def _eye_icon(color: str = "#1e1e2e") -> QIcon:
    """Draw a small eye glyph so the preview button stays font-independent
    and its text line stays vertically centered (emoji baselines drift)."""
    pixmap = QPixmap(22, 22)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.8)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    outline = QRectF(2.5, 4.0, 17.0, 14.0)
    painter.drawArc(outline, 20 * 16, 140 * 16)
    painter.drawArc(outline, 200 * 16, 140 * 16)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(8.0, 7.5, 6.0, 6.0))
    painter.end()
    return QIcon(pixmap)

# Facilities with a trained per-facility model but no facilities/*.json
# definition (hence no 3D preview geometry). They remain fully predictable
# via their reference FDS file. Code -> standardized display name.
TRAINED_NO_JSON_FACILITIES: list[tuple[str, str]] = [
    ("Boeing_Satellite", "卫星工厂（多功能分区）"),
    ("MPPF", "加工厂房（MPPF）"),
    ("SLC", "移动发射平台+发射塔"),
    ("boeing", "飞机工厂（总装车间+部装车间）"),
    ("factory", "飞机工厂（沃斯堡）"),
    ("hanger", "发射场运载火箭集成车库"),
    ("lcc", "发射控制中心"),
    ("lob", "发射控制中心（SLC3）"),
    ("maf", "加工厂房（MAF）"),
    ("ocb", "部装车间"),
    ("sspf", "部装车间（SSPF）"),
    ("vab", "总装车间"),
    ("Hangar", "机场机库（埃格林）"),
    ("TWA", "机场机库（TWA）"),
    ("ligen", "机场机库（里根）"),
    ("tesla", "机械制造设施"),
    ("yjc", "冶金-钢铁厂"),
]

# Three top-level categories shown in the facility tree. Each maps to the
# facility code (JSON facility stem or trained-only code) plus its Chinese
# display name. Equivalent facilities (aerospace / airport_hangar /
# machinery_manufacturing / metallurgical_facilities) keep their building
# sub-nodes; specialized ones are single nodes.
FACILITY_CATEGORIES: list[tuple[str, str, list[tuple[str, str, bool]]]] = [
    (
        "航空航天（含机场机库）",
        "#a6e3a1",
        [
            ("aerospace", "航空航天设施", True),
            ("airport_hangar", "机场机库", True),
            ("Boeing_Satellite", "卫星工厂（多功能分区）", False),
            ("MPPF", "加工厂房（MPPF）", False),
            ("SLC", "移动发射平台+发射塔", False),
            ("boeing", "飞机工厂（总装车间+部装车间）", False),
            ("factory", "飞机工厂（沃斯堡）", False),
            ("hanger", "发射场运载火箭集成车库", False),
            ("lcc", "发射控制中心", False),
            ("lob", "发射控制中心（SLC3）", False),
            ("maf", "加工厂房（MAF）", False),
            ("ocb", "部装车间", False),
            ("sspf", "部装车间（SSPF）", False),
            ("vab", "总装车间", False),
            ("Hangar", "机场机库（埃格林）", False),
            ("TWA", "机场机库（TWA）", False),
            ("ligen", "机场机库（里根）", False),
        ],
    ),
    (
        "机械制造",
        "#f9e2af",
        [
            ("machinery_manufacturing", "机械制造设施", True),
            ("frymaster_corporation", "机械-总装", False),
            ("gleason_cutting_tools_corporation", "机械-机械加工", False),
            ("harbison_fischer", "机械-部装", False),
            ("tesla", "机械制造设施", False),
        ],
    ),
    (
        "冶金",
        "#f38ba8",
        [
            ("metallurgical_facilities", "冶金设施", True),
            ("alcoa", "冶金-电解厂", False),
            ("materion_buffalo", "冶金-金精炼", False),
            ("materion_newton", "冶金-钽精炼", False),
            ("warrick_power_plant", "冶金-发电厂", False),
            ("yjc", "冶金-钢铁厂", False),
        ],
    ),
]


class _SizeRadioGroupFacade:
    """Compatibility facade exposing the old ``size_combo`` API over a dict of
    mutually-exclusive QRadioButtons ("小"/"中"/"大")."""

    def __init__(self, radios: dict[str, QRadioButton]):
        self._radios = radios
        self._blocked = False

    def currentText(self) -> str:
        for size, rb in self._radios.items():
            if rb.isChecked():
                return size
        return "中"

    def isEnabled(self) -> bool:
        return any(rb.isEnabled() for rb in self._radios.values())

    def setEnabled(self, enabled: bool) -> None:
        for rb in self._radios.values():
            rb.setEnabled(enabled)
        if not enabled:
            self._radios["中"].setChecked(True)

    def blockSignals(self, blocked: bool) -> bool:
        prev = self._blocked
        self._blocked = blocked
        for rb in self._radios.values():
            rb.blockSignals(blocked)
        return prev

    def setCurrentText(self, text: str) -> None:
        if text in self._radios:
            self._radios[text].setChecked(True)

    def setToolTip(self, tip: str) -> None:
        for rb in self._radios.values():
            rb.setToolTip(tip)


class FacilityListPanel(QWidget):
    """Left sidebar: facility tree + inline params + scene list."""

    facility_selected = Signal(dict)  # replace entire model (category generation)
    building_added = Signal(object)  # append one Building object
    scene_building_selected = Signal(int)  # select building for editing
    trained_facility_selected = Signal(str)  # trained-only facility: FDS preview + prediction
    normal_facility_selected = Signal()  # a JSON facility was selected; leave FDS preview

    def __init__(self, parent=None):
        super().__init__(parent)
        self.facility_manager = FacilityManager()
        self.selected_facility_data = None
        self._params = None
        self._syncing = False
        font = self.font()
        font.setPointSize(font.pointSize() + 2)
        self.setFont(font)
        self.setStyleSheet(
            "QLabel{font-size:15px;} QGroupBox{font-size:15px;} "
            "QSpinBox{font-size:15px;} QDoubleSpinBox{font-size:15px;} "
            "QRadioButton{font-size:15px;} QPushButton{font-size:15px;} "
            "QTreeWidget{font-size:15px;} QTableWidget{font-size:15px;}"
        )
        self.setup_ui()
        self._populate_tree()

    # ==================================================
    # UI Setup
    # ==================================================

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- 1. Facility tree --
        sec_tree = CollapsibleSection("设施类型")
        self.facility_tree = QTreeWidget()
        self.facility_tree.setHeaderHidden(True)
        self.facility_tree.setMinimumHeight(540)
        self.facility_tree.setStyleSheet(
            "QTreeWidget{font-size:13px;}"
            "QTreeWidget::item{padding:3px 0;min-height:22px;}"
        )
        self.facility_tree.itemClicked.connect(self._on_tree_clicked)
        sec_tree.content_layout.addWidget(self.facility_tree)

        # Description label
        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        self.desc_label.setMinimumHeight(42)
        self.desc_label.setStyleSheet("color:#a6adc8; font-size:12px;")
        sec_tree.content_layout.addWidget(self.desc_label)
        outer.addWidget(sec_tree)

        sec_bld = CollapsibleSection("建筑参数")
        g = QGridLayout()
        g.setSpacing(3)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)

        def _lbl(text):
            lbl = QLabel(text)
            lbl.setFixedWidth(lbl.sizeHint().width())
            return lbl

        def _range_label(width=None):
            lbl = QLabel("")
            lbl.setStyleSheet("color:#6c7086; font-size:11px;")
            if width:
                lbl.setMinimumWidth(width)
            return lbl

        # Size class is intentionally the only visible scale control. Exact
        # dimensions are already shown in the scene table after generation.
        # Three mutually-exclusive radio buttons sit on the same row as the
        # label; they fade when the control is disabled.
        self.size_radios: dict[str, QRadioButton] = {}
        size_row = QHBoxLayout()
        size_row.setSpacing(14)
        for size in ("小", "中", "大"):
            rb = QRadioButton(size)
            rb.setEnabled(False)
            rb.setStyleSheet(
                "QRadioButton{font-size:14px;color:#cdd6f4;font-weight:bold;padding:2px 0;}"
                "QRadioButton:hover{color:#ffffff;}"
                "QRadioButton:disabled{color:#6c7086;font-weight:normal;}"
                "QRadioButton::indicator{width:18px;height:18px;"
                "border:2px solid #6c7086;border-radius:9px;background:#313244;}"
                "QRadioButton::indicator:checked{border:2px solid #89b4fa;"
                "background:#89b4fa;}"
                "QRadioButton::indicator:disabled{border:2px solid #45475a;"
                "background:#313244;}"
                "QRadioButton::indicator:disabled:checked{border:2px solid #585b70;"
                "background:#585b70;}"
            )
            rb.toggled.connect(lambda checked, s=size: self._on_size_class_changed(s) if checked else None)
            self.size_radios[size] = rb
            size_row.addWidget(rb)
        self._size_range_label = _range_label()
        self._size_range_label.setWordWrap(True)
        size_row.addWidget(self._size_range_label)
        size_row.addStretch()
        self.size_combo = _SizeRadioGroupFacade(self.size_radios)
        r = 0
        g.addWidget(_lbl("规模:"), r, 0)
        g.addLayout(size_row, r, 1, 1, 5)

        # Kept as a hidden compatibility field for older integrations that may
        # still access ``rng_size``; it is never added to the visible layout.
        self.rng_size = QLabel("")
        self.rng_size.setVisible(False)

        sec_bld.content_layout.addLayout(g)

        # Hidden stories widget: read-only display for specialized buildings.
        self.sp_N = QSpinBox()
        self.sp_N.setRange(1, 30)
        self.sp_N.setValue(1)
        self.sp_N.setMinimumHeight(28)
        self.sp_N.setStyleSheet("font-size:13px;")
        self.sp_N.setVisible(False)
        self.rng_N = _range_label(width=80)
        self.rng_N.setVisible(False)

        def _hidden_dspin() -> QDoubleSpinBox:
            sb = QDoubleSpinBox()
            sb.setRange(0, 99999)
            sb.setDecimals(1)
            sb.setVisible(False)
            return sb

        def _hidden_label() -> QLabel:
            lbl = QLabel("")
            lbl.setVisible(False)
            return lbl

        self._hidden_length = _hidden_dspin()
        self._hidden_width = _hidden_dspin()
        self._hidden_height = _hidden_dspin()
        self._rng_length = _hidden_label()
        self._rng_width = _hidden_label()
        self._rng_height = _hidden_label()

        self._param_spinboxes = {
            "length": self._hidden_length,
            "width": self._hidden_width,
            "height": self._hidden_height,
            "stories": self.sp_N,
        }
        self._range_labels = {
            "length": self._rng_length,
            "width": self._rng_width,
            "height": self._rng_height,
            "stories": self.rng_N,
        }
        self._param_ranges = {}  # raw [min, max, ...] per field
        self._param_scale_values = {}  # field -> (small, medium, large)

        # Keep the parameter section compact so the facility tree gets the
        # extra vertical space. Leave enough room for the size combo to render
        # fully with a little breathing space.
        sec_bld.setMinimumHeight(104)
        sec_bld.setMaximumHeight(110)
        outer.addWidget(sec_bld)

        # -- Primary actions --
        # Keep the two facility-level actions on one row. Individual-building
        # generation is deliberately omitted to make the main workflow clear.
        action_layout = QHBoxLayout()
        action_layout.setSpacing(6)

        self.combustible_btn = QPushButton("可燃物管理…")
        self.combustible_btn.setEnabled(False)
        self.combustible_btn.setMinimumHeight(36)
        self.combustible_btn.setToolTip("查看或配置当前设施 / 建筑的可燃物")
        apply_button_variant(self.combustible_btn, "primary")
        self.combustible_btn.clicked.connect(self._on_combustible_clicked)
        action_layout.addWidget(self.combustible_btn, 1)

        self.generate_category_btn = QPushButton("生成设施")
        self.generate_category_btn.setEnabled(False)
        self.generate_category_btn.setMinimumHeight(36)
        self.generate_category_btn.setToolTip("按当前规模生成所选设施的全部建筑")
        apply_button_variant(self.generate_category_btn, "success")
        self.generate_category_btn.clicked.connect(self._on_generate_category)
        action_layout.addWidget(self.generate_category_btn, 1)

        outer.addLayout(action_layout)

        # -- 8. Scene object list --
        sec_scene = CollapsibleSection("场景目标列表")
        self.scene_table = QTableWidget()
        self.scene_table.setColumnCount(3)
        self.scene_table.setHorizontalHeaderLabels(["名称", "尺寸（m）", "位置（m）"])
        header = self.scene_table.horizontalHeader()
        # All three columns participate in stretch sizing, so the available
        # width is always filled without nested horizontal scroll bars.
        for column in range(3):
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        header.setSectionsClickable(False)
        header.setHighlightSections(False)
        self.scene_table.verticalHeader().setVisible(False)
        self.scene_table.verticalHeader().setDefaultSectionSize(30)
        self.scene_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.scene_table.setSelectionMode(QTableWidget.SingleSelection)
        self.scene_table.setAlternatingRowColors(True)
        self.scene_table.setShowGrid(False)
        self.scene_table.setMinimumHeight(130)
        self.scene_table.setStyleSheet(
            "QTableWidget{font-size:12px;}"
            "QTableWidget::item{padding:3px 6px;}"
            "QTableWidget::item:alternate{background:#2b2d3d;}"
        )
        self.scene_table.cellClicked.connect(self._on_scene_table_clicked)
        sec_scene.content_layout.addWidget(self.scene_table)

        outer.addWidget(sec_scene)

    # ==================================================
    # Facility tree
    # ==================================================

    def _populate_tree(self):
        """Populate the facility tree grouped by the three engineering categories."""
        self.facility_tree.clear()

        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(bold_font.pointSize() + 1)

        for cat_name, color, entries in FACILITY_CATEGORIES:
            cat_root = QTreeWidgetItem([cat_name])
            cat_root.setFont(0, bold_font)
            cat_root.setForeground(0, QBrush(QColor(color)))
            cat_root.setData(0, Qt.UserRole, {"node": "group"})

            for code, cn, is_equivalent in entries:
                fac_data = self.facility_manager.facilities.get(code)
                if fac_data is not None:
                    # Facility defined in facilities/*.json
                    if is_equivalent:
                        category_item = QTreeWidgetItem([f"{cn}（等效）"])
                        category_item.setData(
                            0, Qt.UserRole, {"facility": code, "type": "equivalent", "node": "facility"}
                        )
                        for building in fac_data.get("buildings", []):
                            child_label = building.get("cn_name", building["name"])
                            child = QTreeWidgetItem([child_label])
                            child.setData(
                                0,
                                Qt.UserRole,
                                {
                                    "facility": code,
                                    "building": building["name"],
                                    "type": "equivalent",
                                    "node": "building",
                                },
                            )
                            category_item.addChild(child)
                    else:
                        category_item = QTreeWidgetItem([cn])
                        category_item.setData(
                            0, Qt.UserRole, {"facility": code, "type": "specialized", "node": "facility"}
                        )
                    cat_root.addChild(category_item)
                else:
                    # Trained-only facility (no JSON / no 3D geometry): Chinese
                    # name only; prediction happens via the 预测 button.
                    item = QTreeWidgetItem([cn])
                    item.setData(
                        0,
                        Qt.UserRole,
                        {"facility": code, "type": "specialized", "node": "trained_only"},
                    )
                    cat_root.addChild(item)

            self.facility_tree.addTopLevelItem(cat_root)
            self.facility_tree.expandItem(cat_root)

    # Alias for backward compatibility
    def load_facilities(self):
        self._populate_tree()

    def _on_tree_clicked(self, item, column):
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        node = data.get("node", "")

        # Group root nodes ("等效模型" / "特异模型") are not actionable
        if node == "group":
            return

        facility_name = data["facility"]
        ftype = data["type"]

        if node == "building":
            # A specific building was selected
            building_name = data["building"]
            self.selected_facility_data = data

            if ftype == "equivalent":
                self._show_equivalent_params(facility_name, building_name)
            else:
                self._show_specialized_params(facility_name, building_name)

            self.generate_category_btn.setEnabled(True)
            self._reset_generate_button_label()
            self.combustible_btn.setEnabled(True)
            self.combustible_btn.setToolTip("查看或配置当前设施 / 建筑的可燃物")
            self.normal_facility_selected.emit()

        elif node == "trained_only":
            # A trained-only facility (no JSON / no 3D template): the 3D view
            # previews its reference FDS geometry (facilities/{code}.fds);
            # heat-source conditions are set in the right panel.
            self.selected_facility_data = data
            cn = dict(TRAINED_NO_JSON_FACILITIES).get(facility_name, facility_name)
            self.desc_label.setText(
                f"{cn} — 训练设施，无三维模板，可预览FDS几何并直接预测"
            )
            self.generate_category_btn.setEnabled(True)
            self.generate_category_btn.setIconSize(QSize(18, 18))
            self.generate_category_btn.setIcon(_eye_icon("#1e1e2e"))
            self.generate_category_btn.setText("预览设施")
            self.generate_category_btn.setToolTip(
                "加载该设施的参考FDS文件并在3D视图预览几何（热源参数在右侧面板设置）"
            )
            self.combustible_btn.setEnabled(True)
            self.combustible_btn.setToolTip("查看可燃材料概览（解析自参考FDS文件）")
            self.size_combo.setEnabled(False)
            self._update_size_range_label(None)

        elif node == "facility":
            self.selected_facility_data = data
            self._show_facility_params(facility_name)
            self.generate_category_btn.setEnabled(True)
            self._reset_generate_button_label()
            self.combustible_btn.setEnabled(True)
            self.combustible_btn.setToolTip("查看或配置当前设施 / 建筑的可燃物")
            self.normal_facility_selected.emit()

    def _reset_generate_button_label(self):
        self.generate_category_btn.setText("生成设施")
        self.generate_category_btn.setIcon(QIcon())
        self.generate_category_btn.setToolTip("按当前规模生成所选设施的全部建筑")

    def _update_size_range_label(self, facility_name: str | None):
        """在规模选择下方标注各档次对应的设施总建筑面积（footprint）."""
        if not facility_name:
            self._size_range_label.setText("")
            return
        fac_data = self.facility_manager.facilities.get(facility_name)
        if not fac_data:
            self._size_range_label.setText("")
            return
        if fac_data.get("type") == "specialized":
            self._size_range_label.setText("特异模型 — 尺寸随模型，不分小/中/大")
            return
        areas = {"small": 0.0, "medium": 0.0, "large": 0.0}
        has_any = False
        for b in fac_data.get("buildings", []):
            for tier, dims in (b.get("scale_dimensions") or {}).items():
                if tier not in areas or not isinstance(dims, dict):
                    continue
                length = float(dims.get("length", 0) or 0)
                width = float(dims.get("width", 0) or 0)
                if length and width:
                    areas[tier] += length * width
                    has_any = True
        if not has_any:
            self._size_range_label.setText("")
            return
        self._size_range_label.setText(
            f"建筑面积：小 {areas['small']:,.0f} m² · "
            f"中 {areas['medium']:,.0f} m² · 大 {areas['large']:,.0f} m²"
        )

    # ==================================================
    # Parameter display for equivalent models
    # ==================================================

    def _show_equivalent_params(self, facility_name, building_name):
        """Fill inline param controls from equivalent model default params."""
        bdata = self.facility_manager.get_building_data(facility_name, building_name)
        params = self.facility_manager.default_params(facility_name, building_name)
        ranges = params.get("ranges", {})
        scale_values = params.get("scale_values", {})
        self._params = {
            "facility": facility_name,
            "building": building_name,
            "type": "equivalent",
        }
        self._syncing = True
        self._param_ranges = ranges
        self._param_scale_values = scale_values

        # Populate the compact size selector (大/中/小). Exact dimensions
        # are intentionally deferred to the generated scene table.
        self.size_combo.setEnabled(True)
        self.size_combo.blockSignals(True)
        self.size_combo.setCurrentText("中")
        self.size_combo.blockSignals(False)

        self.sp_N.setVisible(False)
        self.rng_N.setVisible(False)

        # Description
        cn = bdata.get("cn_name", building_name)
        desc = bdata.get("description", "")
        self.desc_label.setText(f"{cn}\n{desc}" if desc else cn)
        self._update_size_range_label(facility_name)
        self._syncing = False

    # ==================================================
    # Size class selection callback
    # ==================================================

    def _on_size_class_changed(self, text: str):
        if self._syncing or not (self._param_scale_values or self._param_ranges):
            return
        idx = {"小": 0, "中": 1, "大": 2}.get(text, 1)
        self._syncing = True
        try:
            for field_name, spinbox in self._param_spinboxes.items():
                hints = self._scale_hints_from_params(
                    self._param_scale_values, self._param_ranges
                )
                if field_name not in hints:
                    continue
                val = hints[field_name][idx]
                if field_name == "stories":
                    val = int(round(val))
                spinbox.setValue(val)
        finally:
            self._syncing = False

    @staticmethod
    def _scale_hints_from_params(scale_values: dict, ranges: dict) -> dict:
        """Return ``{field: (small, medium, large)}`` for display."""
        hints = {}
        for field_name in ["length", "width", "height", "stories"]:
            if field_name in scale_values:
                values = tuple(scale_values[field_name])
            else:
                r = ranges.get(field_name, [0, 0])
                if len(r) >= 3:
                    values = (r[0], r[2], r[1])
                elif len(r) >= 2:
                    values = (r[0], (r[0] + r[1]) / 2, r[1])
                elif r:
                    values = (r[0], r[0], r[0])
                else:
                    values = (0, 0, 0)
            hints[field_name] = values
        return hints

    # ==================================================
    # Parameter display for specialized models
    # ==================================================

    def _show_specialized_params(self, facility_name, building_name):
        """Show read-only values from specialized building data."""
        bdata = self.facility_manager.get_building_data(facility_name, building_name)
        boundary = bdata.get("boundary", [0, 20, 0, 10])
        values = {
            "length": boundary[1],
            "width": boundary[3],
            "height": bdata.get("height", 3.0),
            "stories": len(bdata.get("stories", [])),
        }
        self._params = {
            "facility": facility_name,
            "building": building_name,
            "type": "specialized",
        }
        self._syncing = True
        self._param_scale_values = {}
        try:
            for field_name, val in values.items():
                spinbox = self._param_spinboxes[field_name]
                # Temporarily widen range so setValue doesn't clamp
                spinbox.setMinimum(0)
                spinbox.setMaximum(99999)
                spinbox.setValue(val)
                spinbox.setEnabled(False)
                self._range_labels[field_name].setVisible(False)

            # Size combo disabled for specialized models
            self.size_combo.setEnabled(False)

            # Description
            cn = bdata.get("cn_name", building_name)
            self.desc_label.setText(f"{cn} (特异模型 - 参数只读)")
            self._update_size_range_label(facility_name)
        finally:
            self._syncing = False

    # ==================================================
    # Parameter display for facility-level (aggregated)
    # ==================================================

    def _show_facility_params(self, facility_name: str):
        """Fill inline param controls with aggregated ranges across all buildings."""
        fac_data = self.facility_manager.facilities[facility_name]
        buildings = fac_data["buildings"]
        ftype = fac_data["type"]
        cn_name = fac_data["cn_name"]

        self._params = {
            "facility": facility_name,
            "building": None,
            "type": ftype,
        }
        self._syncing = True
        try:
            if ftype == "specialized":
                self._param_scale_values = {}
                self.size_combo.setEnabled(False)
                self.rng_size.setText("")
                spinbox = self._param_spinboxes["stories"]
                spinbox.setEnabled(False)
                self._range_labels["stories"].setVisible(False)
                self.desc_label.setText(
                    f"{cn_name} (特异模型) — 共 {len(buildings)} 个建筑"
                )
                self._update_size_range_label(facility_name)
                return

            # --- Equivalent: aggregate ranges across all buildings ---
            # Collect per-building ranges
            all_ranges: dict[str, dict] = {}  # bname -> {field: [min, max, ...]}
            all_scale_values: dict[str, dict] = {}
            for b in buildings:
                bname = b["name"]
                all_ranges[bname] = {
                    "length": b.get("length_range", [0, 0]),
                    "width": b.get("width_range", [0, 0]),
                    "height": b.get("height_range", [0, 0]),
                    "stories": b.get("stories_range", [0, 0]),
                }
                all_scale_values[bname] = self.facility_manager.scale_dimension_options(
                    facility_name, bname
                )

            # Use first building's ranges for preview & _param_ranges
            first_bname = buildings[0]["name"]
            first_ranges = all_ranges[first_bname]
            first_scale_values = all_scale_values[first_bname]
            self._param_ranges = first_ranges  # so _on_size_class_changed works
            self._param_scale_values = first_scale_values

            self.size_combo.setEnabled(True)
            self.size_combo.blockSignals(True)
            self.size_combo.setCurrentText("中")
            self.size_combo.blockSignals(False)

            self.desc_label.setText(
                f"{cn_name} (等效模型) — 共 {len(buildings)} 个建筑"
            )
            self._update_size_range_label(facility_name)
            self.sp_N.setVisible(False)
            self.rng_N.setVisible(False)
        finally:
            self._syncing = False

    # ==================================================
    # Size-class helper (for facility-level generation)
    # ==================================================

    def _build_params_for_size_class(
        self, facility_name: str, building_name: str, size_idx: int
    ) -> dict:
        """Build params dict from building's own ranges at the given size index.
        size_idx: 0=小, 1=中, -1=大
        """
        scale_idx = self._size_idx_to_scale_idx(size_idx)
        return self.facility_manager.params_for_scale(
            facility_name, building_name, scale_idx=scale_idx
        )

    @staticmethod
    def _size_idx_to_scale_idx(size_idx: int) -> int:
        if size_idx == 0:
            return 0
        if size_idx == 1:
            return 1
        return 2

    # ==================================================
    # Scene building lookup (for offset preservation)
    # ==================================================

    def _get_scene_building_offset(self, facility: str, building_name: str) -> tuple[float, float] | None:
        """Look up offset of an existing building with matching name in the scene."""
        buildings = getattr(self, "_scene_buildings", [])
        for b in buildings:
            if b.name == building_name or getattr(b, "cn_name", "") == building_name:
                return (b.offset_x, b.offset_y)
        return None

    # ==================================================
    # Generate actions
    # ==================================================

    @staticmethod
    def _auto_arrange_buildings(buildings, gap=15.0):
        x = 0.0
        for b in buildings:
            b.boundary[0] = x
            b.boundary[2] = 0.0
            x += b.length + gap

    def _on_generate(self):
        if not self.selected_facility_data:
            QMessageBox.warning(self.window(), "提示", "请先从设施类型中选择一个建筑")
            return

        data = self.selected_facility_data
        facility = data.get("facility")
        building_name = data.get("building")
        ftype = data.get("type")

        if not facility or not building_name:
            QMessageBox.warning(self.window(), "提示", "请先从设施类型中选择一个具体建筑")
            return

        if ftype == "specialized":
            building = self.facility_manager.load_specialized(facility, building_name)
        else:
            size_text = self.size_combo.currentText() if self.size_combo.isEnabled() else "中"
            size_idx = {"小": 0, "中": 1, "大": -1}.get(size_text, 1)
            params = self._build_params_for_size_class(
                facility, building_name, size_idx
            )
            existing_offset = self._get_scene_building_offset(facility, building_name)
            building = self.facility_manager.load_equivalent(
                facility, building_name, params,
                current_offset=existing_offset,
            )

        self.building_added.emit(building)

    def _on_generate_category(self):
        """Generate all buildings in the selected facility."""
        if not self.selected_facility_data:
            return

        facility_name = self.selected_facility_data.get("facility")
        if not facility_name:
            return

        if self.selected_facility_data.get("node") == "trained_only":
            # No 3D template: "generate" means loading the FDS geometry preview.
            self.trained_facility_selected.emit(facility_name)
            return

        ftype = self.facility_manager.get_type(facility_name)
        size_text = self.size_combo.currentText() if self.size_combo.isEnabled() else "中"
        size_idx = {"小": 0, "中": 1, "大": -1}.get(size_text, 1)

        # Internal arrange policy (decided once, in code, no UI opt-out):
        # - "specialized" facilities ship their own authoritative bounds.
        #   We never repack; doing so would silently overwrite curated data.
        # - "equivalent" facilities use a facility-level layout when present,
        #   so small / medium / large scenes keep the same inter-building gap.
        #   Legacy templates without layout still fall back to overlap cleanup.
        from models.build_arranger import arrange_buildings, has_overlap

        buildings = []

        if ftype == "specialized":
            for bname in self.facility_manager.list_buildings(facility_name):
                buildings.append(
                    self.facility_manager.load_specialized(facility_name, bname)
                )
        else:
            for bname in self.facility_manager.list_buildings(facility_name):
                params = self._build_params_for_size_class(
                    facility_name, bname, size_idx
                )
                buildings.append(
                    self.facility_manager.load_equivalent(
                        facility_name, bname, params
                    )
                )
            layout_applied = self.facility_manager.arrange_buildings_by_layout(
                facility_name, buildings
            )
            if not layout_applied and len(buildings) > 1 and has_overlap(buildings):
                arrange_buildings(buildings, gap=20.0)

        if not buildings:
            return

        group = BuildingGroup(name=facility_name, buildings=buildings)
        self.facility_selected.emit(group.to_dict())

    def _on_combustible_clicked(self):
        """Route combustible button to building-level or facility-level dialog."""
        if not self.selected_facility_data:
            return
        node = self.selected_facility_data.get("node")
        if node in ("trained_only", "facility"):
            if node == "facility" and self.facility_manager.get_type(
                self.selected_facility_data.get("facility", "")
            ) != "specialized":
                self._open_facility_combustible_dialog()
                return
            self._open_fds_combustible_dialog()
        elif node == "facility":
            self._open_facility_combustible_dialog()
        else:
            self._open_combustible_dialog()

    def _open_fds_combustible_dialog(self):
        """Open read-only combustible overview parsed from the reference FDS."""
        facility_name = self.selected_facility_data.get("facility")
        if not facility_name:
            return
        fac_data = self.facility_manager.facilities.get(facility_name, {})
        cn = fac_data.get("cn_name") or dict(TRAINED_NO_JSON_FACILITIES).get(
            facility_name, facility_name
        )
        from services.fds_parser import (
            combustible_summary,
            load_fds_scene,
            resolve_reference_fds,
        )

        fds_path = resolve_reference_fds(facility_name)
        if fds_path is None:
            QMessageBox.warning(self, "提示", f"未找到 {cn} 的参考FDS文件")
            return
        try:
            scene = load_fds_scene(fds_path)
        except Exception as exc:  # surfaced to the user, not fatal
            QMessageBox.warning(self, "提示", f"解析FDS文件 {fds_path.name} 失败：\n{exc}")
            return

        rows = combustible_summary(scene)
        combustible_boxes = sum(row["boxes"] for row in rows)
        non_combustible_boxes = len(scene.obstacles) - combustible_boxes

        from ui.dialogs import FdsCombustibleOverviewDialog

        dlg = FdsCombustibleOverviewDialog(self, cn, rows, non_combustible_boxes)
        dlg.exec()

    def _open_combustible_dialog(self):
        """Open combustible management with the current building's FC list."""
        if not self._params:
            return

        facility = self._params.get("facility")
        building_name = self._params.get("building")
        ftype = self._params.get("type")
        if not facility or not building_name:
            return

        # Collect fire_compartments as plain dicts for the dialog.
        fcs: list[dict] = []
        if ftype == "specialized":
            bdata = self.facility_manager.get_building_data(facility, building_name)
            for story in bdata.get("stories", []):
                for fc in story.get("fire_compartments", []):
                    fcs.append(fc)
        else:
            params_full = self.facility_manager.default_params(facility, building_name)
            bld = self.facility_manager.load_equivalent(facility, building_name, params_full)
            for story in bld.stories:
                for fc in story.fire_compartments:
                    fcs.append(fc.to_dict())

        from ui.dialogs import CombustibleSelectionDialog

        current_sel = self._params.get("combustible_selections", {})
        dlg = CombustibleSelectionDialog(
            self,
            current_sel,
            fire_compartments=fcs,
        )
        if dlg.exec() == QDialog.Accepted:
            self._params["combustible_selections"] = dlg.get_selections()

    def _open_facility_combustible_dialog(self):
        """Open facility-level combustible overview dialog (read-only)."""
        if not self.selected_facility_data:
            return
        facility_name = self.selected_facility_data.get("facility")
        if not facility_name:
            return

        size_text = self.size_combo.currentText() if self.size_combo.isEnabled() else "中"
        size_idx = {"小": 0, "中": 1, "大": -1}.get(size_text, 1)

        from ui.dialogs import FacilityCombustibleOverviewDialog

        dlg = FacilityCombustibleOverviewDialog(
            self,
            facility_manager=self.facility_manager,
            facility_name=facility_name,
            size_idx=size_idx,
        )
        dlg.exec()

    # ==================================================
    # Compatibility stubs (for FacilityDialog path)
    # ==================================================

    def generate_equivalent_model(self):
        self._on_generate()

    def generate_category_model(self):
        self._on_generate_category()

    # ==================================================
    # Scene object list
    # ==================================================

    def update_scene_list(self, buildings):
        """Update scene table from list of Building objects."""
        self.scene_table.setRowCount(len(buildings))
        self._scene_buildings = buildings  # keep reference for selection

        for i, b in enumerate(buildings):
            name_item = QTableWidgetItem(b.cn_name or b.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.scene_table.setItem(i, 0, name_item)

            size_item = QTableWidgetItem(f"{b.length:.1f} × {b.width:.1f} × {b.height:.1f}")
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)
            self.scene_table.setItem(i, 1, size_item)

            pos_item = QTableWidgetItem(f"({b.offset_x:.1f}, {b.offset_y:.1f})")
            pos_item.setFlags(pos_item.flags() & ~Qt.ItemIsEditable)
            self.scene_table.setItem(i, 2, pos_item)

    def _on_scene_table_clicked(self, row, col):
        """Handle scene table click - select building."""
        if 0 <= row < len(getattr(self, "_scene_buildings", [])):
            self._selected_scene_idx = row
            self.scene_building_selected.emit(row)
