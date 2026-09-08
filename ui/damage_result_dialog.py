#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File  : damage_result_dialog.py
@Desc  : Beautified dialog for displaying agent_damage prediction results.
         Shows overall damage level with colored banner, heat source summary,
         and scrollable per-building cards with probability bars.
"""

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# ── Color palette (matches existing dark theme) ────────────────────────
BG_ROOT = "#1e1e2e"
BG_CARD = "#313244"
BG_CARD_SOFT = "#393952"
FG_MAIN = "#cdd6f4"
FG_DIM = "#a6adc8"
ACCENT_BLUE = "#89b4fa"

LEVEL_COLORS = {
    "low": {
        "bright": "#a6e3a1",
        "dark": "#40a02b",
        "icon": "🟢",
        "label": "轻微",
    },
    "medium": {
        "bright": "#f9e2af",
        "dark": "#df8e1d",
        "icon": "🟡",
        "label": "中度",
    },
    "high": {
        "bright": "#f38ba8",
        "dark": "#d20f39",
        "icon": "🔴",
        "label": "严重",
    },
}


class DamageResultDialog(QDialog):
    """工程预测结果美化显示对话框。"""

    def __init__(
        self,
        facility_result: Any,
        heat_source: Any,
        infer_time_ms: float,
        model_names: list[str] | None = None,
        algorithm: str = "max",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("工程预测结果")
        self.setMinimumSize(680, 620)
        self.setStyleSheet(f"QDialog {{ background: {BG_ROOT}; }}")

        self._result = facility_result
        self._heat_source = heat_source
        self._infer_time_ms = infer_time_ms
        self._model_names = model_names or []
        self._algorithm = algorithm
        self._setup_ui()

    # ── layout ─────────────────────────────────────────────────────
    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        root.addWidget(self._build_header())
        root.addWidget(self._build_heat_panel())
        root.addWidget(self._build_buildings_title())
        root.addWidget(self._build_buildings_list(), stretch=1)
        root.addLayout(self._build_footer())

    # ── header (overall level banner) ──────────────────────────────
    def _build_header(self) -> QFrame:
        overall_level = self._result.get_overall_level(algorithm=self._algorithm)
        overall = overall_level.value
        palette = LEVEL_COLORS[overall]
        bright, dark = palette["bright"], palette["dark"]

        matching = [
            r for r in self._result.building_results
            if r.damage_level == overall_level
        ]
        overall_prob = (
            sum(r.probability for r in matching) / len(matching)
            if matching else 0.0
        )

        banner = QFrame()
        banner.setStyleSheet(
            f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {bright}, stop:1 {dark});
                border-radius: 14px;
            }}
            QLabel {{ background: transparent; color: {BG_ROOT}; }}
            """
        )
        layout = QVBoxLayout(banner)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(6)

        title = QLabel(
            f"{palette['icon']}  整体毁伤等级：{palette['label']}"
        )
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: 800; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        sub_parts = [
            f"概率 {overall_prob * 100:.1f}%",
            f"不确定度 {self._result.overall_uncertainty:.3f}",
            f"推理 {self._infer_time_ms / 1000.0:.2f} s",
            f"{len(self._result.building_results)} 栋单体建筑",
        ]
        sub = QLabel("   •   ".join(sub_parts))
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("font-size: 13px; font-weight: 500;")
        layout.addWidget(sub)

        return banner

    # ── heat source summary ────────────────────────────────────────
    def _build_heat_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame {{ background: {BG_CARD}; border-radius: 10px; }}"
        )
        grid = QGridLayout(panel)
        grid.setContentsMargins(18, 14, 18, 14)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)

        title = QLabel("🔥 热源参数")
        title.setStyleSheet(
            f"color: {ACCENT_BLUE}; font-weight: bold; font-size: 14px;"
            " background: transparent;"
        )
        grid.addWidget(title, 0, 0, 1, 4)

        items = [
            ("方位角", f"{self._heat_source.azimuth}°"),
            ("俯仰角", f"{self._heat_source.elevation}°"),
            ("热通量", f"{self._heat_source.heat_flux} kW/m²"),
            ("持续", f"{self._heat_source.duration} s"),
        ]
        for i, (label_text, value_text) in enumerate(items):
            cell = self._heat_cell(label_text, value_text)
            grid.addWidget(cell, 1, i)
            grid.setColumnStretch(i, 1)

        return panel

    def _heat_cell(self, label: str, value: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        l = QLabel(label)
        l.setStyleSheet(f"color: {FG_DIM}; font-size: 11px; background: transparent;")
        v = QLabel(value)
        v.setStyleSheet(
            f"color: {FG_MAIN}; font-size: 17px; font-weight: bold;"
            " background: transparent;"
        )
        layout.addWidget(l)
        layout.addWidget(v)
        return w

    # ── buildings section ──────────────────────────────────────────
    def _build_buildings_title(self) -> QLabel:
        title = QLabel(f"📍 单体建筑毁伤（{len(self._result.building_results)} 栋）")
        title.setStyleSheet(
            f"color: {ACCENT_BLUE}; font-weight: bold; font-size: 14px;"
        )
        return title

    def _build_buildings_list(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }\n"
            f"QScrollBar:vertical {{ background: {BG_ROOT}; width: 10px; }}\n"
            f"QScrollBar::handle:vertical {{ background: {BG_CARD_SOFT};"
            " border-radius: 4px; min-height: 24px; }"
        )

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        for br in self._result.building_results:
            v.addWidget(self._building_card(br))
        v.addStretch()

        scroll.setWidget(inner)
        return scroll

    def _building_card(self, br: Any) -> QFrame:
        level_value = br.damage_level.value
        palette = LEVEL_COLORS[level_value]
        icon = palette["icon"]
        label = palette["label"]
        bar_color = palette["dark"]

        card = QFrame()
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {BG_CARD};
                border-left: 4px solid {bar_color};
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; }}
            """
        )

        h = QHBoxLayout(card)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(16)

        # Left: building name + dims
        left = QVBoxLayout()
        left.setSpacing(2)
        display_name = getattr(br.building, "cn_name", None) or br.building.name
        name_lbl = QLabel(f"{icon} {display_name}")
        name_lbl.setStyleSheet(
            f"color: {FG_MAIN}; font-weight: bold; font-size: 14px;"
        )
        dims_lbl = QLabel(
            f"{br.building.length:.1f} × {br.building.width:.1f}"
            f" × {br.building.height:.1f} m"
            f"   |   {br.building.stories} 层"
        )
        dims_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 11px;")
        left.addWidget(name_lbl)
        left.addWidget(dims_lbl)
        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setStyleSheet("background: transparent;")
        h.addWidget(left_widget, stretch=3)

        # Middle: probability bar + label
        middle = QVBoxLayout()
        middle.setSpacing(3)
        prob_lbl = QLabel(f"{label}   {br.probability * 100:.1f}%")
        prob_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        prob_lbl.setStyleSheet(
            f"color: {bar_color}; font-weight: bold; font-size: 14px;"
        )
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(br.probability * 100))
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                background: #45475a;
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {bar_color};
                border-radius: 3px;
            }}
            """
        )
        middle.addWidget(prob_lbl)
        middle.addWidget(bar)
        mid_widget = QWidget()
        mid_widget.setLayout(middle)
        mid_widget.setStyleSheet("background: transparent;")
        h.addWidget(mid_widget, stretch=3)

        # Right: uncertainty
        right = QVBoxLayout()
        right.setSpacing(2)
        u_lbl = QLabel("不确定度")
        u_lbl.setAlignment(Qt.AlignRight)
        u_lbl.setStyleSheet(f"color: {FG_DIM}; font-size: 10px;")
        u_val = QLabel(f"{br.uncertainty:.3f}")
        u_val.setAlignment(Qt.AlignRight)
        u_val.setStyleSheet(f"color: {FG_MAIN}; font-size: 13px; font-weight: bold;")
        right.addWidget(u_lbl)
        right.addWidget(u_val)
        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setStyleSheet("background: transparent;")
        h.addWidget(right_widget, stretch=1)

        return card

    # ── footer ─────────────────────────────────────────────────────
    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(120, 36)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: {ACCENT_BLUE};
                color: {BG_ROOT};
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{ background: #74c7ec; }}
            """
        )
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        return row


EXPERIMENTAL_GRADE_COLORS = {
    0: {"bright": "#a6e3a1", "dark": "#40a02b", "icon": "🟢"},
    1: {"bright": "#94e2d5", "dark": "#179299", "icon": "🔵"},
    2: {"bright": "#f9e2af", "dark": "#df8e1d", "icon": "🟡"},
    3: {"bright": "#f38ba8", "dark": "#d20f39", "icon": "🔴"},
}


class ExperimentalDamageResultDialog(QDialog):
    """Display one facility-level prediction from the FDS-trained Dk model."""

    def __init__(
        self,
        context: Any,
        heat_source: dict[str, float],
        infer_time_ms: float,
        parent=None,
    ):
        super().__init__(parent)
        self._context = context
        self._prediction = context.prediction
        self._heat_source = heat_source
        self._infer_time_ms = infer_time_ms
        self.setWindowTitle("毁伤等级预测结果")
        self.setMinimumSize(680, 390)
        self.setStyleSheet(f"QDialog {{ background: {BG_ROOT}; }}")
        self._setup_experimental_ui()

    def _setup_experimental_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        root.addWidget(self._build_experimental_header())
        root.addWidget(self._build_experimental_heat_panel())
        subtarget_grades = getattr(self._prediction, "subtarget_grades", None)
        if subtarget_grades:
            root.addWidget(self._build_subtarget_title())
            root.addWidget(self._build_subtarget_list(), stretch=1)
        else:
            root.addStretch()

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(100, 34)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT_BLUE}; color: {BG_ROOT}; "
            "border: none; border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background: #b4befe; }"
        )
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)

    def _build_subtarget_title(self) -> QLabel:
        title = QLabel(f"📍 各子目标毁伤等级（{len(self._prediction.subtarget_grades)} 个）")
        title.setStyleSheet(
            f"color: {ACCENT_BLUE}; font-weight: bold; font-size: 14px;"
        )
        return title

    def _build_subtarget_list(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }\n"
            f"QScrollBar:vertical {{ background: {BG_ROOT}; width: 10px; }}\n"
            f"QScrollBar::handle:vertical {{ background: {BG_CARD_SOFT};"
            " border-radius: 4px; min-height: 24px; }"
        )
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        for st in self._prediction.subtarget_grades:
            v.addWidget(self._subtarget_card(st))
        v.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _subtarget_card(self, st: dict[str, object]) -> QFrame:
        grade = int(st["grade"])
        palette = EXPERIMENTAL_GRADE_COLORS.get(
            grade, {"dark": "#7f849c", "icon": "•", "bright": "#cdd6f4"}
        )
        card = QFrame()
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {BG_CARD};
                border-left: 4px solid {palette['dark']};
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; }}
            """
        )
        h = QHBoxLayout(card)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(16)
        name_lbl = QLabel(f"{palette['icon']} {st.get('cn_name', st.get('name', ''))}")
        name_lbl.setStyleSheet(
            f"color: {FG_MAIN}; font-weight: bold; font-size: 14px;"
        )
        h.addWidget(name_lbl, stretch=1)
        grade_lbl = QLabel(st.get("grade_name", ""))
        grade_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grade_lbl.setStyleSheet(
            f"color: {palette['dark']}; font-weight: bold; font-size: 14px;"
        )
        h.addWidget(grade_lbl)
        return card

    def _build_experimental_header(self) -> QFrame:
        grade = int(self._prediction.damage_grade)
        palette = EXPERIMENTAL_GRADE_COLORS[grade]
        banner = QFrame()
        banner.setStyleSheet(
            f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {palette['bright']}, stop:1 {palette['dark']});
                border-radius: 14px;
            }}
            QLabel {{ background: transparent; color: {BG_ROOT}; }}
            """
        )
        layout = QVBoxLayout(banner)
        layout.setContentsMargins(28, 22, 28, 22)
        title = QLabel(
            f"{palette['icon']}  整体毁伤等级：{self._prediction.damage_grade_name}"
        )
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 24px; font-weight: 800;")
        layout.addWidget(title)
        subtitle_parts = []
        subtitle_parts.append(f"模型加载和推理 {self._infer_time_ms / 1000.0:.2f} s")
        result_source = (
            "权威工况结果"
            if self._prediction.used_observed_result
            else "代理模型预测"
        )
        subtitle_parts.append(result_source)
        subtitle = QLabel("  •  ".join(subtitle_parts))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 13px; font-weight: 500;")
        layout.addWidget(subtitle)
        return banner

    def _build_experimental_heat_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(f"QFrame {{ background: {BG_CARD}; border-radius: 10px; }}")
        grid = QGridLayout(panel)
        grid.setContentsMargins(18, 14, 18, 14)
        title_text = "🔥 本次预测工况"
        title = QLabel(title_text)
        title.setStyleSheet(f"color: {ACCENT_BLUE}; font-weight: bold; font-size: 14px;")
        grid.addWidget(title, 0, 0, 1, 4)
        items = (
            ("方位角", f"{self._heat_source['azimuth']:g}°"),
            ("俯仰角", f"{self._heat_source['elevation']:g}°"),
            ("目标热通量", f"{self._heat_source['heat_flux']:g} kW/m²"),
            ("持续时间", f"{self._heat_source['duration']:g} s"),
        )
        for column, (name, value) in enumerate(items):
            label = QLabel(f"{name}\n{value}")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(f"color: {FG_MAIN}; font-size: 13px;")
            grid.addWidget(label, 1, column)
            grid.setColumnStretch(column, 1)
        return panel
