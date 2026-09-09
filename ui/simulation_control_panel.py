#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File  : simulation_control_panel.py
@Author: Lubber
@Date  : 2026-03-20
@Version : 1.0
@Desc  : Simulation control panel for heat source and simulation parameters
"""

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QGridLayout,
    QDoubleSpinBox,
    QComboBox,
    QPushButton,
    QHBoxLayout,
    QSizePolicy,
    QSlider,
    QMessageBox,
    QProgressDialog,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
import os
import time
from ui.styles import CollapsibleGroup, apply_button_variant
from services.fds_naming import VIDEO_ROOT, simulation_suffix, video_path_for


class _PredictionWorker(QThread):
    """Run model loading and inference outside the Qt main loop."""

    completed = Signal(object)
    failed = Signal(str, str)

    def __init__(self, kind, model=None, facility_name=None, heat_source=None):
        super().__init__()
        self.kind = kind
        self.model = model
        self.facility_name = facility_name
        self.heat_source = dict(heat_source or {})

    def run(self):
        try:
            from agent_damage.src.inference.split_model_predictor import (
                load_split_model_predictor,
            )
            from services.damage_prediction import (
                UnsupportedDamageFacility,
                predict_current_model,
                predict_facility_by_name,
            )

            predictor = load_split_model_predictor()
            if self.kind == "current":
                context = predict_current_model(self.model, predictor)
            else:
                context = predict_facility_by_name(
                    self.facility_name,
                    predictor,
                    self.heat_source,
                )
            self.completed.emit(context)
        except ImportError as exc:
            self.failed.emit("error", f"无法加载预测模型依赖：{exc}")
        except FileNotFoundError:
            self.failed.emit("missing", "预测模型不存在。")
        except UnsupportedDamageFacility as exc:
            self.failed.emit("unsupported", str(exc))
        except Exception as exc:
            import traceback

            traceback.print_exc()
            self.failed.emit("error", f"生成特征或推理出错：{exc}")


class SimulationControlPanel(QWidget):
    """模拟控制面板 - 包含热源和模拟参数"""

    parameters_changed = Signal(str)  # kind: "heat_geom" | "heat_flux" | "sim" | "slice_device"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._syncing = False
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)
        self.setup_ui()

    @staticmethod
    def _dark_btn(text, slot, danger=False):
        """深色背景、深色字体的按钮"""
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(26)
        btn.clicked.connect(slot)
        apply_button_variant(btn, "danger" if danger else "primary", small=True)
        return btn

    # ── 热源 ────────────────────────────────────────
    def _build_heat_section(self):
        grp = CollapsibleGroup("热源参数")

        form = QGridLayout()
        form.setContentsMargins(0, 2, 0, 0)
        form.setSpacing(4)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)

        # Row 0: Azimuth slider | Elevation snap
        form.addWidget(QLabel("方位角:"), 0, 0)
        az_row = QHBoxLayout()
        az_row.setSpacing(4)
        self.heat_azimuth_slider = QSlider(Qt.Horizontal)
        self.heat_azimuth_slider.setRange(0, 360)
        self.heat_azimuth_slider.setValue(0)
        self.heat_azimuth_slider.setSingleStep(5)
        self.heat_azimuth_slider.setPageStep(45)
        self.heat_azimuth_slider.setTickPosition(QSlider.TicksBelow)
        self.heat_azimuth_slider.setTickInterval(45)
        self.heat_azimuth_slider.valueChanged.connect(self._on_azimuth_label_update)
        self.heat_azimuth_slider.sliderReleased.connect(self._on_azimuth_committed)
        az_row.addWidget(self.heat_azimuth_slider)
        self.azimuth_label = QLabel("0°")
        self.azimuth_label.setFixedWidth(50)
        self.azimuth_label.setStyleSheet(
            "color:#89b4fa;font-weight:bold;font-size:11px;"
        )
        az_row.addWidget(self.azimuth_label)
        form.addLayout(az_row, 0, 1)

        form.addWidget(QLabel("俯仰角:"), 0, 2)
        elev_row = QHBoxLayout()
        elev_row.setSpacing(4)
        self.heat_elevation_slider = QSlider(Qt.Horizontal)
        self.heat_elevation_slider.setRange(0, 3)
        self.heat_elevation_slider.setValue(0)
        self.heat_elevation_slider.setToolTip(
            "当前损伤模型训练覆盖 0°、30°、45°、60°；75°/90° 暂不外推"
        )
        self.heat_elevation_slider.setTickPosition(QSlider.TicksBelow)
        self.heat_elevation_slider.setTickInterval(1)
        self.heat_elevation_slider.valueChanged.connect(self._on_elevation_changed)
        self.heat_elevation_slider.sliderReleased.connect(self._on_azimuth_committed)
        elev_row.addWidget(self.heat_elevation_slider)
        self.elevation_label = QLabel("0°")
        self.elevation_label.setFixedWidth(40)
        self.elevation_label.setStyleSheet("color:#89b4fa;font-weight:bold;")
        elev_row.addWidget(self.elevation_label)
        form.addLayout(elev_row, 0, 3)

        # Row 1: Flux target q_avg (kW/m²) | calibrated duration (s)
        form.addWidget(QLabel("热通量:"), 1, 0)
        self.heat_flux_spin = QDoubleSpinBox()
        self.heat_flux_spin.setRange(0, 100000)
        self.heat_flux_spin.setValue(1000)
        self.heat_flux_spin.setDecimals(0)
        self.heat_flux_spin.setSingleStep(500)
        self.heat_flux_spin.setSuffix(" kW/m²")
        self.heat_flux_spin.setToolTip("0 到持续时间窗口内的目标平均热通量")
        self.heat_flux_spin.valueChanged.connect(self._on_flux_changed)
        form.addWidget(self.heat_flux_spin, 1, 1)

        form.addWidget(QLabel("持续:"), 1, 2)
        self.heat_duration_spin = QComboBox()
        for duration in self._DURATION_VALUES:
            self.heat_duration_spin.addItem(f"{duration:g} s", duration)
        self.heat_duration_spin.currentIndexChanged.connect(self._on_flux_changed)
        form.addWidget(self.heat_duration_spin, 1, 3)

        grp.content_layout.addLayout(form)
        return grp

    _ELEV_VALUES = [0, 30, 45, 60]
    _DURATION_VALUES = [1.36, 2.1, 7.5]

    # ── 模拟 + 输出 ─────────────────────────────────
    def _build_simulation_section(self):
        grp = CollapsibleGroup("⚙️ 模拟 / 输出")
        g = QGridLayout()
        g.setSpacing(4)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)

        g.addWidget(QLabel("时间:"), 0, 0)
        self.sim_time_spin = QDoubleSpinBox()
        self.sim_time_spin.setRange(1, 36000)
        self.sim_time_spin.setValue(1800)
        self.sim_time_spin.setSuffix(" s")
        self.sim_time_spin.valueChanged.connect(
            lambda v: self._on_param_changed_debounced("sim")
        )
        g.addWidget(self.sim_time_spin, 0, 1)

        grp.content_layout.addLayout(g)
        return grp

    # ── 工程预测 ─────────────────────────────────
    def _build_simulation_run_section(self):
        grp = CollapsibleGroup("🎯 工程预测")
        layout = QVBoxLayout()
        layout.setSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        def _mkbtn(text, variant="primary", tooltip=""):
            btn = QPushButton(text)
            btn.setFixedHeight(30)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            apply_button_variant(btn, variant, small=True)
            if tooltip:
                btn.setToolTip(tooltip)
            return btn

        self.result_label = QLabel("就绪：选择设施后可进行工程快速预测")
        self.result_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        self.predict_btn = _mkbtn("⚡ 预测", "warning", "工程快速预测(损伤代理模型)")
        self.predict_btn.clicked.connect(self.run_predict)
        action_row.addWidget(self.predict_btn)

        self.play_video_btn = _mkbtn(
            "▶️ 播放工况演示", "primary", "播放当前工况(设施+热源参数)的预渲染仿真视频"
        )
        self.play_video_btn.clicked.connect(self.play_demo_video)
        action_row.addWidget(self.play_video_btn)
        layout.addLayout(action_row)

        grp.content_layout.addLayout(layout)
        return grp

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # 添加热源和模拟部分
        root.addWidget(self._build_heat_section())
        root.addWidget(self._build_simulation_section())
        root.addWidget(self._build_simulation_run_section())
        # No trailing stretch: the right-column splitter gives the FDS
        # preview all leftover room.

    # ── 事件处理 ────────────────────────────────────────
    def _toggle_heat(self, state):
        # Legacy — heat source is always enabled now.
        self.on_param_changed("heat_geom")

    def _on_azimuth_label_update(self, value):
        """Snap to 5° and update label (no model refresh)."""
        snapped = round(value / 5) * 5
        if self.heat_azimuth_slider.value() != snapped:
            self.heat_azimuth_slider.setValue(snapped)
            return
        self._refresh_azimuth_label(snapped, self._current_elevation())

    def _current_elevation(self) -> int:
        return self._ELEV_VALUES[min(self.heat_elevation_slider.value(), 3)]

    def _refresh_azimuth_label(self, azimuth: int, elevation: int):
        self.azimuth_label.setText(f"{azimuth}°")

    def _on_azimuth_committed(self):
        """Slider released — emit heat_geom event."""
        self.on_param_changed("heat_geom")

    def _on_elevation_changed(self, index):
        val = self._ELEV_VALUES[min(index, len(self._ELEV_VALUES) - 1)]
        self.elevation_label.setText(f"{val}°")
        self.on_param_changed("heat_geom")

    def _on_flux_changed(self, *_args):
        """Flux / duration — FDS-only, no 3D refresh."""
        if self._syncing:
            return
        self._debounce_kind = "heat_flux"
        self._debounce_timer.start(500)

    def _on_param_changed_debounced(self, kind: str = "sim"):
        self._debounce_kind = kind
        self._debounce_timer.start(500)

    def _on_debounce_timeout(self):
        self.on_param_changed(getattr(self, "_debounce_kind", "sim"))

    def on_param_changed(self, kind: str = "sim"):
        if not self._syncing:
            self.sync_model_from_ui()
            self.parameters_changed.emit(kind)

    def _current_duration(self) -> float:
        value = self.heat_duration_spin.currentData()
        return float(value if value is not None else self._DURATION_VALUES[0])

    def _set_duration_value(self, duration: float):
        nearest = min(
            self._DURATION_VALUES,
            key=lambda candidate: abs(candidate - float(duration)),
        )
        idx = self._DURATION_VALUES.index(nearest)
        self.heat_duration_spin.setCurrentIndex(idx)

    # ── 工况显示 ─────────────────────────────────
    def current_heat_source(self) -> dict[str, float]:
        """Return the current UI heat-source direction without needing a model."""
        return {
            "azimuth": self.heat_azimuth_slider.value(),
            "elevation": self._current_elevation(),
            "net_heat_flux": self.heat_flux_spin.value(),
            "duration": self._current_duration(),
        }

    def _facility_display_name(self) -> str:
        """Return the Chinese display name for the current facility selection."""
        pending = getattr(self, "_pending_trained_facility", None)
        if pending:
            from ui.facility_panel import TRAINED_NO_JSON_FACILITIES

            return dict(TRAINED_NO_JSON_FACILITIES).get(pending, pending)
        model = self.model
        try:
            from models.facility import FacilityManager

            manager = FacilityManager()
            name = getattr(model, "name", "") or ""
            cn = manager.facilities.get(name, {}).get("cn_name", "")
            if cn:
                return cn
            # Single-building generation keeps the group name empty; infer
            # the facility from the building template names in the group.
            for building in getattr(model, "buildings", None) or []:
                for stem, data in manager.facilities.items():
                    names = {
                        b.get("name") or b.get("cn_name")
                        for b in data.get("buildings", [])
                    }
                    if building.name in names or getattr(
                        building, "cn_name", ""
                    ) in names:
                        return data.get("cn_name", stem) or stem
        except Exception:
            pass
        return name or ""

    def _condition_display(self) -> dict:
        """Build the condition info shown on the demo player dialog."""
        hs = dict(getattr(self.model, "heat_source", {}) or {})
        return {
            "facility_name": self._facility_display_name(),
            "heat_flux": hs.get("net_heat_flux"),
            "duration": hs.get("duration"),
            "azimuth": hs.get("azimuth"),
            "elevation": hs.get("elevation"),
            "sim_time": getattr(self.model, "simulation_time", None),
        }

    # ── 工况演示视频 ─────────────────────────────────
    def _resolve_demo_video(self) -> str | None:
        """Return the expected demo video path for the current selection.

        Trained-only facilities have no geometry, so the loaded model name
        stays the default (``building``); for those the reference case's
        CHID prefix is used instead.  Returns ``None`` if no model loaded.
        """
        if not hasattr(self, "model") or self.model is None:
            return None
        pending = getattr(self, "_pending_trained_facility", None)
        if pending:
            from services.damage_prediction import reference_case_base_name

            base = reference_case_base_name(pending)
            return f"{VIDEO_ROOT}/{base}_{simulation_suffix(self.model)}.mp4"
        return video_path_for(self.model)

    def play_demo_video(self):
        """Play the pre-rendered mp4 for the current facility + parameters.

        The expected clip is ``video/{name}_{suffix}.mp4`` derived from the
        current model's heat-source/simulation parameters. When no clip
        exists for this condition the user is told the demo is missing.
        """
        self.sync_model_from_ui()
        expected = self._resolve_demo_video()
        if expected is None:
            QMessageBox.warning(
                self.window(),
                "演示视频",
                "当前未加载设施。",
            )
            return
        if not os.path.isfile(expected):
            condition = self._condition_display()

            def _value(value, suffix="", numeric=True):
                if value is None:
                    return "—"
                return f"{float(value):g}{suffix}" if numeric else str(value)

            QMessageBox.warning(
                self.window(),
                "当前工况演示",
                "当前工况演示文件不存在。\n\n"
                f"设施：{condition.get('facility_name') or '—'}\n"
                f"热通量：{_value(condition.get('heat_flux'), ' kW/m²')}\n"
                f"方位角：{_value(condition.get('azimuth'), '°')}\n"
                f"俯仰角：{_value(condition.get('elevation'), '°')}\n"
                f"持续时间：{_value(condition.get('duration'), ' s')}\n"
                f"模拟时间：{_value(condition.get('sim_time'), ' s')}",
            )
            return
        try:
            from ui.video_player_dialog import VideoPlayerDialog
        except ImportError as exc:
            QMessageBox.critical(
                self.window(),
                "播放失败",
                f"无法加载内置视频播放器: {exc}\n\n需要 PySide6 的 QtMultimedia 组件。",
            )
            return
        dialog = VideoPlayerDialog(expected, condition=self._condition_display(), parent=self)
        dialog.exec()
        self.result_label.setText("工况演示播放完成")

    # ── 同步方法 ────────────────────────────────────────
    def sync_ui_from_model(self, model):
        """从模型同步UI状态"""
        self._syncing = True
        try:
            hs = model.heat_source
            # UI value is the target window-average heat flux q_avg in kW/m².
            self.heat_flux_spin.setValue(hs.get("net_heat_flux", 1000))
            self.heat_azimuth_slider.setValue(hs.get("azimuth", 0))
            elev = hs.get("elevation", 0)
            elev_idx = {0: 0, 30: 1, 45: 2, 60: 3}.get(elev, 0)
            self.heat_elevation_slider.setValue(elev_idx)
            self._set_duration_value(hs.get("duration", 1.36))
            self.elevation_label.setText(f"{elev}°")
            self._refresh_azimuth_label(hs.get("azimuth", 0), elev)

            # 模拟设置
            self.sim_time_spin.setValue(model.simulation_time)
        finally:
            self._syncing = False

    def set_model(self, model):
        """设置模型并同步UI"""
        self.model = model
        self._pending_trained_facility = None
        self.sync_ui_from_model(model)

    def sync_model_from_ui(self):
        """从UI同步数据到模型"""
        if not hasattr(self, "model"):
            return
        m = self.model
        # Store the UI target window-average heat flux q_avg in kW/m².
        m.heat_source = {
            "azimuth": self.heat_azimuth_slider.value(),
            "elevation": self._ELEV_VALUES[min(self.heat_elevation_slider.value(), 3)],
            "net_heat_flux": self.heat_flux_spin.value(),
            "duration": self._current_duration(),
        }
        m.simulation_time = self.sim_time_spin.value()
        m.domain["grid_size"] = 1.0
        m.domain["refinement_zone"] = {
            "enabled": True,
            "depth": 1.0,
            "grid_size": 1.0,
        }
        # Mesh count is no longer user-configurable: always use the generator
        # default (4 meshes, 2×2) for MPI parallel execution.
        m.domain.pop("num_meshes", None)

    # ── 工程快速预测 ────────────────────────────────────────
    def _set_predicting(self, busy: bool):
        """Toggle the predict button's busy state so the UI shows progress."""
        self.predict_btn.setEnabled(not busy)
        self.predict_btn.setText("⏳ 正在预测中…" if busy else "⚡ 预测")
        if not busy:
            self.result_label.setText("就绪：选择设施后可进行工程快速预测")

    def _show_predict_progress(self):
        """Show a non-blocking modal busy dialog with elapsed time."""
        self._close_predict_progress()
        self._predict_started = time.monotonic()
        progress = QProgressDialog(
            "正在加载损伤模型并计算特征…\n已用时 0.0 s",
            None,
            0,
            0,
            self,
        )
        progress.setWindowTitle("工程预测")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.setMinimumWidth(420)
        progress.show()
        self._predict_progress = progress
        self._predict_progress_timer = QTimer(self)
        self._predict_progress_timer.setInterval(80)
        self._predict_progress_timer.timeout.connect(
            self._update_predict_progress
        )
        self._predict_progress_timer.start()

    def _update_predict_progress(self):
        progress = getattr(self, "_predict_progress", None)
        if progress is None:
            return
        elapsed = time.monotonic() - getattr(self, "_predict_started", time.monotonic())
        progress.setLabelText(
            f"正在加载损伤模型并计算特征…\n已用时 {elapsed:.1f} s"
        )

    def _close_predict_progress(self):
        timer = getattr(self, "_predict_progress_timer", None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        self._predict_progress_timer = None
        progress = getattr(self, "_predict_progress", None)
        if progress is not None:
            progress.close()
            progress.deleteLater()
        self._predict_progress = None

    def _finish_prediction_after_progress(self, callback):
        """Keep the busy indicator readable, then run the UI completion."""
        elapsed = time.monotonic() - getattr(self, "_predict_started", time.monotonic())
        delay_ms = max(0, int((1.2 - elapsed) * 1000))
        QTimer.singleShot(delay_ms, callback)

    def _cleanup_prediction_worker(self):
        worker = getattr(self, "_predict_worker", None)
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        self._predict_worker = None

    def _start_prediction_worker(self, kind, model=None, facility_name=None, heat_source=None):
        if getattr(self, "_predict_worker", None) is not None:
            return
        worker = _PredictionWorker(kind, model, facility_name, heat_source)
        worker.completed.connect(self._on_prediction_completed)
        worker.failed.connect(self._on_prediction_failed)
        self._predict_worker = worker
        worker.start()

    def _on_prediction_completed(self, context):
        worker = self.sender()

        def show_result():
            from ui.damage_result_dialog import ExperimentalDamageResultDialog

            if worker is not None and worker.kind == "current":
                hs = dict(getattr(worker.model, "heat_source", {}) or {})
                heat_source = {
                    "azimuth": float(hs.get("azimuth", 0)),
                    "elevation": float(hs.get("elevation", 0)),
                    "heat_flux": float(hs.get("net_heat_flux", 0)),
                    "duration": float(hs.get("duration", 0)),
                }
            else:
                heat_source = dict(getattr(worker, "heat_source", {}) or {})
            self._close_predict_progress()
            dialog = ExperimentalDamageResultDialog(
                context=context,
                heat_source=heat_source,
                infer_time_ms=(
                    time.monotonic() - getattr(self, "_predict_started", time.monotonic())
                ) * 1000.0,
                parent=self,
            )
            dialog.exec()
            self._set_predicting(False)
            self._cleanup_prediction_worker()

        self._finish_prediction_after_progress(show_result)

    def _on_prediction_failed(self, failure_kind, message):
        def show_error():
            self._close_predict_progress()
            if failure_kind == "missing":
                QMessageBox.warning(self.window(), "预测模型不存在", message)
            elif failure_kind == "unsupported":
                QMessageBox.warning(self.window(), "暂不支持该设施", message)
            else:
                QMessageBox.critical(self.window(), "预测失败", message)
            self._set_predicting(False)
            self._cleanup_prediction_worker()

        self._finish_prediction_after_progress(show_error)

    def run_predict(self):
        """使用真实 FDS 工况训练的设施级 Dk 代理模型进行快速预测。"""
        import time

        pending = getattr(self, "_pending_trained_facility", None)
        if pending:
            self.run_predict_for_facility(pending)
            return
        if not hasattr(self, "model") or not self.model.buildings:
            QMessageBox.warning(self.window(), "预测", "当前没有展示的设施")
            return

        self._set_predicting(True)
        self._show_predict_progress()
        self.sync_model_from_ui()
        self._start_prediction_worker("current", model=self.model)

    def set_pending_trained_facility(self, facility_name: str):
        """Remember the selected trained-only facility for the 预测 button.

        Trained-only facilities have no BuildingGroup, so the regular
        ``run_predict`` path cannot run; the button routes to
        ``run_predict_for_facility`` instead.
        """
        self._pending_trained_facility = facility_name

    def run_predict_for_facility(self, facility_name: str):
        """Predict a trained-only facility (no JSON / no 3D geometry) directly.

        Uses the facility's own training-case FDS as the feature source and the
        current heat-source panel values as the condition.
        """
        self._set_predicting(True)
        self._show_predict_progress()
        hs = dict(getattr(self, "heat_source", None) or {})
        if hasattr(self, "model") and self.model is not None:
            hs = dict(getattr(self.model, "heat_source", {}) or {})
        heat_source = {
            "azimuth": float(hs.get("azimuth", 0)),
            "elevation": float(hs.get("elevation", 0)),
            "heat_flux": float(hs.get("heat_flux", hs.get("net_heat_flux", 1000))),
            "duration": float(hs.get("duration", 1.36)),
        }
        self._start_prediction_worker(
            "facility",
            facility_name=facility_name,
            heat_source=heat_source,
        )
