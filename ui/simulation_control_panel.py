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
    QWidget,
    QVBoxLayout,
    QLabel,
    QGridLayout,
    QDoubleSpinBox,
    QComboBox,
    QPushButton,
    QHBoxLayout,
    QSizePolicy,
    QCheckBox,
    QSlider,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
import os
import subprocess
from ui.styles import CollapsibleGroup, apply_button_variant
from services.fds_naming import (
    RESULTS_ROOT,
    default_fds_filename,
    default_smv_filename,
    results_dir_for,
    results_smv_path,
    sanitize_chid,
    simulation_suffix,
)
from services.program_paths import load_program_path


# ---- Smokeview command-line view options -----------------------------
# Each entry maps a UI checkbox label to the Smokeview CLI flag passed to
# the executable when launching.  These are the subset of view-only flags
# documented in the Smokeview source (firemodels/smv /Source/smokeview/command_args.c).
SMV_VIEW_OPTIONS: list[tuple[str, str]] = [
    ("仅轮廓 (Outline)", "-outline"),
    ("加载温度切片 (Temp)", "-load_temp"),
    ("加载热通量切片 (HRRPUV)", "-load_hrrpuv"),
]


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
        self.heat_flux_spin.setRange(100, 20000)
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

        g.addWidget(QLabel("网格尺寸:"), 0, 2)
        self.grid_size_spin = QDoubleSpinBox()
        self.grid_size_spin.setRange(0.1, 5.0)
        self.grid_size_spin.setValue(1.0)
        self.grid_size_spin.setSingleStep(0.1)
        self.grid_size_spin.setToolTip(
            "网格尺寸 (m)\n小规模建议 0.5, 中规模 1.0, 大规模 2.0"
        )
        self.grid_size_spin.valueChanged.connect(
            lambda _v: self._on_param_changed_debounced("sim")
        )
        g.addWidget(self.grid_size_spin, 0, 3)

        grp.content_layout.addLayout(g)
        return grp

    # ── Smokeview 查看 ─────────────────────────────────
    def _build_simulation_run_section(self):
        grp = CollapsibleGroup("🔍 Smokeview 查看结果")
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

        self.result_label = QLabel("就绪：选择设施后点开将打开对应.results/.smv")
        self.result_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        self.smv_btn = _mkbtn("🔍 打开结果", "primary", "用Smokeview打开预计算仿真结果")
        self.smv_btn.clicked.connect(self.open_smokeview)
        btn_row.addWidget(self.smv_btn)

        self.browse_smv_btn = _mkbtn("📂浏览…", "primary", "手动选择一个 .smv 文件打开")
        self.browse_smv_btn.clicked.connect(self.browse_and_open_smv)
        btn_row.addWidget(self.browse_smv_btn)

        layout.addLayout(btn_row)

        predict_row = QHBoxLayout()
        predict_row.setSpacing(4)
        self.predict_btn = _mkbtn("⚡ 预测", "warning", "工程快速预测(毁伤代理模型)")
        self.predict_btn.clicked.connect(self.run_predict)
        predict_row.addWidget(self.predict_btn)
        predict_row.addStretch()
        layout.addLayout(predict_row)

        # ---- SMV view option checkboxes (set initial display state) ----
        options_row = QHBoxLayout()
        options_row.setSpacing(6)
        self.smv_option_checks: list[QCheckBox] = []
        for label, _flag in SMV_VIEW_OPTIONS:
            cb = QCheckBox(label)
            cb.setStyleSheet("font-size:11px; padding:1px 4px;")
            options_row.addWidget(cb, alignment=Qt.AlignLeft)
            self.smv_option_checks.append(cb)
        options_row.addStretch()
        layout.addLayout(options_row)

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

    # ── Smokeview 启动 ─────────────────────────────────
    def _resolve_results_dir(self) -> str:
        """Return the expected results directory for the current model.

        Falls back to ``results/`` itself when the model is missing.
        """
        if not hasattr(self, "model") or self.model is None:
            return RESULTS_ROOT
        return results_dir_for(self.model)

    def _resolve_results_smv(self) -> str | None:
        """Return the expected ``.smv`` path for the current model.

        Returns ``None`` if no model is loaded.
        """
        if not hasattr(self, "model") or self.model is None:
            return None
        return results_smv_path(self.model)

    def _selected_smv_view_flags(self) -> list[str]:
        flags: list[str] = []
        for cb, (_label, flag) in zip(self.smv_option_checks, SMV_VIEW_OPTIONS):
            if cb.isChecked():
                flags.append(flag)
        return flags

    def browse_and_open_smv(self):
        """Pick any ``.smv`` file on disk and open it in Smokeview."""
        start_dir = self._resolve_results_dir()
        if not os.path.isdir(start_dir):
            start_dir = RESULTS_ROOT
        path, _ = QFileDialog.getOpenFileName(
            self, "选择Smokeview文件 (.smv)", start_dir, "Smokeview (*.smv)"
        )
        if not path:
            return
        self._launch_smokeview(path)

    def open_smokeview(self):
        """Open the Smokeview result for the currently-loaded facility + params.

        Resolution order:
        1. Build the expected path ``results/{name}/{name}_{suffix}/{name}_{suffix}.smv``
           from the current model and parameters.
        2. If it does not exist, scan ``results/{name}/`` for any subdirectory
           whose ``.smv`` name matches the current heat-source parameters, then
           for any subdirectory containing ``.smv`` files at all.
        3. If still nothing, fall back to opening ``results/{name}/`` in the
           OS file manager so the user can pick manually.
        """
        expected = self._resolve_results_smv()
        if expected and os.path.isfile(expected):
            self._launch_smokeview(expected)
            return

        candidates = self._scan_available_smv_files()
        if not candidates:
            QMessageBox.warning(
                self.window(),
                "未找到结果",
                f"找不到预计算的 Smokeview 结果。\n\n期望路径:\n{expected or '(未加载设施)'}\n\n"
                f"请确认 results/ 下已有对应的设施文件夹。\n"
                "可点击「📂浏览…」手动选择任意 .smv 文件。",
            )
            return

        # Single candidate — open directly. Multiple — pick first and inform.
        chosen = candidates[0]
        if len(candidates) > 1:
            items = [os.path.basename(p) for p in candidates[:50]]
            from PySide6.QtWidgets import QInputDialog

            chosen_name, ok = QInputDialog.getItem(
                self,
                "选择结果",
                f"找到 {len(candidates)} 个结果文件，请选择一个打开:",
                items,
                0,
                False,
            )
            if not ok:
                return
            chosen = next(p for p in candidates if os.path.basename(p) == chosen_name)
        self._launch_smokeview(chosen)

    def _scan_available_smv_files(self) -> list[str]:
        """Scan ``results/{model.name}/`` for ``.smv`` files, ordered by
        closeness to the current parameters' suffix."""
        if not hasattr(self, "model") or self.model is None:
            return []
        name = sanitize_chid(getattr(self.model, "name", "") or "building")
        base_dir = os.path.join(RESULTS_ROOT, name)
        if not os.path.isdir(base_dir):
            return []
        try:
            subdirs = [
                os.path.join(base_dir, d)
                for d in os.listdir(base_dir)
                if os.path.isdir(os.path.join(base_dir, d))
            ]
        except OSError:
            return []
        try:
            target_suffix = simulation_suffix(self.model)
        except Exception:
            target_suffix = ""

        matching: list[str] = []
        for sd in subdirs:
            smv_in_sd = [
                os.path.join(sd, f)
                for f in os.listdir(sd)
                if f.lower().endswith(".smv")
            ]
            if not smv_in_sd:
                continue
            if target_suffix and target_suffix in os.path.basename(sd):
                matching.append(smv_in_sd[0])
        if matching:
            return matching
        fallback: list[str] = []
        for sd in subdirs:
            for f in os.listdir(sd):
                if f.lower().endswith(".smv"):
                    fallback.append(os.path.join(sd, f))
        fallback.sort()
        return fallback

    def _launch_smokeview(self, smv_file: str):
        """Find Smokeview executable and launch it on ``smv_file`` with the
        currently-selected view option flags."""
        smv_exe = self._find_smokeview_exe()
        if not smv_exe:
            QMessageBox.warning(
                self.window(),
                "未找到Smokeview",
                "未找到Smokeview可执行文件。\n"
                "请通过菜单 → 设置 → 设置Smokeview程序路径 指定 smokeview 可执行文件路径,\n"
                "或确保 smokeview 已添加到系统 PATH。",
            )
            return
        flags = self._selected_smv_view_flags()
        cmd = [smv_exe] + flags + [smv_file]
        try:
            subprocess.Popen(cmd)
            self.result_label.setText(
                f"已启动: smokeview {' '.join(flags)} {os.path.basename(smv_file)}"
            )
        except Exception as e:
            QMessageBox.critical(self.window(), "错误", f"无法启动Smokeview: {str(e)}")

    def _find_smokeview_exe(self):
        """查找Smokeview可执行文件 — 用于启动查看程序。"""
        user_path = load_program_path("smokeview")
        if user_path and os.path.exists(user_path):
            return user_path
        try:
            cmd = "where" if os.name == "nt" else "which"
            result = subprocess.run(
                [cmd, "smokeview"], capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[0]
        except Exception:
            pass
        common_paths = [
            "smokeview",
            "C:/Program Files/FDS/Smokeview/bin/smokeview.exe",
            "C:/Program Files (x86)/FDS/Smokeview/bin/smokeview.exe",
            "C:/FDS/Smokeview/bin/smokeview.exe",
        ]
        if os.name != "nt":
            common_paths += [
                "/usr/local/bin/smokeview",
                "/usr/bin/smokeview",
                "/opt/fds/bin/smokeview",
            ]
        for path in common_paths:
            if os.path.exists(path):
                return path
        return None

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
            self.grid_size_spin.setValue(model.domain.get("grid_size", 1.0))
        finally:
            self._syncing = False

    def set_model(self, model):
        """设置模型并同步UI"""
        self.model = model
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
        m.domain["grid_size"] = float(self.grid_size_spin.value())
        m.domain["refinement_zone"] = {
            "enabled": True,
            "depth": 1.0,
            "grid_size": 1.0,
        }
        # Mesh count is no longer user-configurable: always use the generator
        # default (4 meshes, 2×2) for MPI parallel execution.
        m.domain.pop("num_meshes", None)

    # ── 工程快速预测 ────────────────────────────────────────
    def run_predict(self):
        """使用真实 FDS 工况训练的设施级 Dk 代理模型进行快速预测。"""
        import time

        if not hasattr(self, "model") or not self.model.buildings:
            QMessageBox.warning(self.window(), "预测", "当前没有展示的设施")
            return

        try:
            from agent_damage.src.inference.experimental_predictor import (
                DEFAULT_EXPERIMENTAL_MODEL,
                load_experimental_dk_predictor,
            )
            from services.damage_prediction import (
                UnsupportedDamageFacility,
                predict_current_model,
            )
            from ui.damage_result_dialog import ExperimentalDamageResultDialog
        except ImportError as exc:
            QMessageBox.critical(
                self.window(),
                "预测失败",
                f"无法导入最新毁伤代理模型依赖：{exc}\n\n"
                "请执行 uv sync 安装 pandas 与 scikit-learn。",
            )
            return

        try:
            # The artifact is ~130 MB. Cache the deserialised predictor on the
            # panel so repeated predictions do not reload it from disk.
            predictor = getattr(self, "_experimental_damage_predictor", None)
            if predictor is None:
                predictor = load_experimental_dk_predictor()
                self._experimental_damage_predictor = predictor
        except FileNotFoundError:
            QMessageBox.warning(
                self.window(),
                "预测模型不存在",
                f"未找到最新模型文件：\n{DEFAULT_EXPERIMENTAL_MODEL}\n\n"
                "请先运行 agent_damage/scripts/train_experimental.py 生成模型。",
            )
            return
        except Exception as exc:
            QMessageBox.critical(self.window(), "预测失败", f"加载最新模型失败：{exc}")
            return

        try:
            t0 = time.perf_counter()
            context = predict_current_model(self.model, predictor)
            infer_ms = (time.perf_counter() - t0) * 1000.0
        except UnsupportedDamageFacility as exc:
            QMessageBox.warning(self.window(), "暂不支持该设施", str(exc))
            return
        except Exception as exc:
            import traceback

            traceback.print_exc()
            QMessageBox.critical(self.window(), "预测失败", f"生成特征或推理出错：{exc}")
            return

        hs = self.model.heat_source
        dialog = ExperimentalDamageResultDialog(
            context=context,
            heat_source={
                "azimuth": float(hs.get("azimuth", 0)),
                "elevation": float(hs.get("elevation", 0)),
                "heat_flux": float(hs.get("net_heat_flux", 0)),
                "duration": float(hs.get("duration", 0)),
            },
            infer_time_ms=infer_ms,
            parent=self,
        )
        dialog.exec()
