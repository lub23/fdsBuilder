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
    QGroupBox,
    QGridLayout,
    QLineEdit,
    QDoubleSpinBox,
    QComboBox,
    QPushButton,
    QCheckBox,
    QHBoxLayout,
    QSizePolicy,
    QSpinBox,
    QDialog,
    QTextEdit,
    QSlider,
    QFileDialog,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal, QProcess, QProcessEnvironment, QTimer
import os
import subprocess
from ui.styles import CollapsibleGroup


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
        if danger:
            btn.setStyleSheet(
                "QPushButton{background:#f38ba8;color:#1e1e2e;font-weight:bold;"
                "padding:2px 8px;border-radius:3px}"
                "QPushButton:hover{background:#e06080;color:#1e1e2e}"
            )
        else:
            btn.setStyleSheet(
                "QPushButton{background:#89b4fa;color:#1e1e2e;font-weight:bold;"
                "padding:2px 8px;border-radius:3px}"
                "QPushButton:hover{background:#74c7ec;color:#1e1e2e}"
            )
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

        # Row 1: Flux (kW/m²) | Duration (s)
        form.addWidget(QLabel("热通量:"), 1, 0)
        self.heat_flux_spin = QDoubleSpinBox()
        self.heat_flux_spin.setRange(50, 20000)
        self.heat_flux_spin.setValue(1000)
        self.heat_flux_spin.setDecimals(0)
        self.heat_flux_spin.setSingleStep(500)
        self.heat_flux_spin.setSuffix(" kW/m²")
        self.heat_flux_spin.valueChanged.connect(self._on_flux_changed)
        form.addWidget(self.heat_flux_spin, 1, 1)

        form.addWidget(QLabel("持续:"), 1, 2)
        self.heat_duration_spin = QDoubleSpinBox()
        self.heat_duration_spin.setRange(0, 36000)
        self.heat_duration_spin.setValue(1.36)
        self.heat_duration_spin.setDecimals(2)
        self.heat_duration_spin.setSuffix(" s")
        self.heat_duration_spin.valueChanged.connect(self._on_flux_changed)
        form.addWidget(self.heat_duration_spin, 1, 3)

        grp.content_layout.addLayout(form)
        return grp

    _ELEV_VALUES = [0, 30, 45, 60]

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

    # ── FDS仿真执行 ─────────────────────────────────
    def _build_simulation_run_section(self):
        grp = CollapsibleGroup("🔥 FDS仿真执行")
        layout = QVBoxLayout()
        layout.setSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        def _mkbtn(text, bg_color, tooltip=""):
            btn = QPushButton(text)
            btn.setFixedHeight(30)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(
                f"QPushButton{{background:{bg_color};color:#1e1e2e;font-weight:bold;"
                f"padding:3px 6px;border-radius:3px;font-size:12px}}"
                f"QPushButton:disabled{{background:#45475a;color:#6c7086}}"
            )
            if tooltip:
                btn.setToolTip(tooltip)
            return btn

        self.run_fds_btn = _mkbtn("▶️ 运行", "#a6e3a1", "运行FDS仿真")
        self.run_fds_btn.clicked.connect(self.run_fds_simulation)
        btn_row.addWidget(self.run_fds_btn)

        self.stop_fds_btn = _mkbtn("⏹️ 停止", "#f38ba8", "停止当前仿真")
        self.stop_fds_btn.setEnabled(False)
        self.stop_fds_btn.clicked.connect(self.stop_fds_simulation)
        btn_row.addWidget(self.stop_fds_btn)

        self.smv_btn = _mkbtn("🔍 查看", "#89b4fa", "用Smokeview打开仿真结果")
        self.smv_btn.setEnabled(False)
        self.smv_btn.clicked.connect(self.open_smokeview)
        btn_row.addWidget(self.smv_btn)

        self.predict_btn = _mkbtn("⚡ 预测", "#f9e2af", "工程快速预测(毁伤代理模型)")
        self.predict_btn.clicked.connect(self.run_predict)
        btn_row.addWidget(self.predict_btn)

        layout.addLayout(btn_row)

        self.progress_label = QLabel("就绪")
        self.progress_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(self.progress_label)

        self.output_text = QLabel("")
        self.output_text.setStyleSheet("color: #cdd6f4; font-size: 11px;")
        self.output_text.setWordWrap(True)
        self.output_text.setMaximumHeight(40)
        layout.addWidget(self.output_text)

        # -- Window heat flux display --
        flux_row = QHBoxLayout()
        flux_row.setSpacing(4)
        self.flux_label = QLabel("窗口热通量: -- kW/m²")
        self.flux_label.setStyleSheet(
            "color: #f9e2af; font-size: 12px; font-weight: bold;"
        )
        flux_row.addWidget(self.flux_label)
        self.flux_peak_label = QLabel("峰值: --")
        self.flux_peak_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        flux_row.addWidget(self.flux_peak_label)
        flux_row.addStretch()
        layout.addLayout(flux_row)

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

    def _on_flux_changed(self):
        """Flux / duration — FDS-only, no 3D refresh."""
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

    # ── FDS仿真执行 ─────────────────────────────────
    def run_fds_simulation(self):
        """运行FDS仿真"""
        bg = self.model
        chid = bg.name or "building"
        chid = chid.replace(" ", "_").replace(".", "_").replace("-", "_")
        chid = "".join(c for c in chid if ord(c) < 128) or "building"

        hs = bg.heat_source
        heat_flux_kw = int(hs.get("net_heat_flux", 1000))
        azimuth = int(hs.get("azimuth", 0))
        elevation = int(hs.get("elevation", 0))
        duration = int(hs.get("duration", 0) * 1000)
        sim_time = int(bg.simulation_time)

        chid_suffix = f"q{heat_flux_kw}_a{azimuth}_e{elevation}_d{duration}_t{sim_time}"
        default_filename = f"{chid}_{chid_suffix}.fds"
        # 1. 先导出FDS文件
        fds_path, _ = QFileDialog.getSaveFileName(
            self, "保存FDS文件", default_filename, "FDS文件 (*.fds)"
        )
        if not fds_path:
            return

        # 确保扩展名
        if not fds_path.endswith(".fds"):
            fds_path += ".fds"

        # 生成FDS代码
        from generators.fds_generator import FDSGenerator

        generator = FDSGenerator(self.model)
        fds_code = generator.generate()
        num_meshes = getattr(generator, "_num_meshes", 1)

        # 写入文件
        try:
            with open(fds_path, "w", encoding="utf-8") as f:
                f.write(fds_code)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法保存FDS文件: {str(e)}")
            return

        # 2. 查找FDS可执行文件
        fds_exe = self._find_fds_exe()
        if not fds_exe:
            QMessageBox.warning(
                self,
                "未找到FDS",
                "未找到FDS可执行文件。请确保FDS已安装并添加到系统PATH。\n"
                "FDS文件已保存到: " + fds_path,
            )
            return

        # 3. 运行FDS
        self.progress_label.setText("正在运行FDS仿真...")
        self.output_text.setText(f"网格: {num_meshes} | 执行: {fds_exe}\n文件: {fds_path}")
        self.run_fds_btn.setEnabled(False)
        self.stop_fds_btn.setEnabled(True)

        # 保存当前FDS路径用于smokeview
        self._current_fds_path = fds_path
        # SMV文件使用CHID命名，在工作目录中
        work_dir = os.path.dirname(fds_path)
        chid = getattr(self, "model", None) and self.model.chid or "building"
        sanitized = chid.replace(" ", "_").replace(".", "_").replace("-", "_")
        sanitized = "".join(c for c in sanitized if ord(c) < 128) or "building"
        self._current_smv_file = os.path.join(work_dir, sanitized + ".smv")

        # 仿真启动后即可尝试打开Smokeview
        self.smv_btn.setEnabled(True)

        # 使用QProcess运行
        self._fds_process = QProcess(self)
        self._fds_process.setProcessChannelMode(QProcess.MergedChannels)
        self._fds_process.readyReadStandardOutput.connect(self._on_fds_output)
        self._fds_process.finished.connect(self._on_fds_finished)
        self._fds_process.errorOccurred.connect(self._on_fds_error)

        self._fds_process.setWorkingDirectory(work_dir)

        # Build environment with FDS DLL directories in PATH
        env = QProcessEnvironment.systemEnvironment()
        fds_dir = os.path.dirname(os.path.abspath(fds_exe))
        extra_dirs = self._collect_fds_lib_dirs(fds_dir)
        current_path = env.value("PATH", "")
        for d in extra_dirs:
            if d not in current_path:
                current_path = d + os.pathsep + current_path
        env.insert("PATH", current_path)

        # 多核并行：多 MPI 进程 × 多 OpenMP 线程
        import os as _os
        cpu_count = len(_os.sched_getaffinity(0)) if hasattr(_os, "sched_getaffinity") else _os.cpu_count() or 1
        omp_threads = max(1, cpu_count // num_meshes)
        env.insert("OMP_NUM_THREADS", str(omp_threads))
        env.insert("I_MPI_FABRICS", "shm")

        # 栈空间：Intel FDS 在栈上分配大数组，默认 8MB 会 segfault
        import resource
        try:
            resource.setrlimit(
                resource.RLIMIT_STACK,
                (resource.RLIM_INFINITY, resource.RLIM_INFINITY),
            )
        except (ValueError, resource.error):
            pass

        # 查找 Intel MPI 启动器
        mpirun = self._find_mpirun(fds_exe)

        if mpirun and num_meshes > 1:
            args = ["-np", str(num_meshes), fds_exe, fds_path]
            self.output_text.append(f"MPI 启动: {mpirun} {' '.join(args)}")
            self._fds_process.setProcessEnvironment(env)
            self._fds_process.start(mpirun, args)
        else:
            self._fds_process.setProcessEnvironment(env)
            self._fds_process.start(fds_exe, [fds_path])
            self.progress_label.setText("MPI 不可用，单进程运行")

    @staticmethod
    def _collect_fds_lib_dirs(fds_dir: str) -> list:
        """Collect directories that may contain FDS runtime DLLs."""
        dirs = [fds_dir]
        parent = os.path.dirname(fds_dir)
        # Common sub-directories shipped with FDS installations
        for sub in (
            "bin",
            "lib",
            os.path.join("bin", "mpi"),
            "mpi",
            "FDS",
            os.path.join("FDS", "bin"),
        ):
            candidate = os.path.join(parent, sub)
            if os.path.isdir(candidate):
                dirs.append(candidate)
        # Also check MPICH / Intel MPI typical locations
        for env_var in ("I_MPI_ROOT", "MSMPI_BIN"):
            val = os.environ.get(env_var)
            if val:
                for sub in ("", "bin", "lib"):
                    p = os.path.join(val, sub) if sub else val
                    if os.path.isdir(p):
                        dirs.append(p)
        return dirs

    def _on_fds_error(self, error):
        """QProcess startup / runtime error handler."""
        error_msgs = {
            QProcess.FailedToStart: "无法启动FDS进程（可能缺少DLL或权限不足）",
            QProcess.Crashed: "FDS进程崩溃",
            QProcess.Timedout: "FDS进程超时",
            QProcess.WriteError: "写入FDS进程失败",
            QProcess.ReadError: "读取FDS进程输出失败",
        }
        msg = error_msgs.get(error, f"FDS进程错误 (code={error})")
        self.progress_label.setText(f"错误: {msg}")
        self.output_text.setText(
            f"{msg}\n\n请检查:\n"
            "1. FDS程序路径是否正确\n"
            "2. MPI运行时是否已安装\n"
            "3. 系统环境变量PATH是否包含FDS目录"
        )
        self.run_fds_btn.setEnabled(True)
        self.stop_fds_btn.setEnabled(False)

    def _find_fds_exe(self):
        """查找FDS可执行文件"""
        # 先检查用户设置的路径
        from ui.mainwindow import MainWindow

        user_path = MainWindow._load_program_path("fds")
        if user_path and os.path.exists(user_path):
            return user_path

        # 尝试从PATH中查找 (跨平台: Windows用where, Linux/macOS用which)
        try:
            cmd = "where" if os.name == "nt" else "which"
            result = subprocess.run([cmd, "fds"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[0]
        except:
            pass

        return None

    @staticmethod
    def _find_mpirun(fds_exe: str | None = None) -> str | None:
        """查找 Intel MPI mpirun，优先 fds 同级 INTEL 目录"""
        # 优先：fds_exe 同级 INTEL/bin/mpirun
        if fds_exe:
            fds_dir = os.path.dirname(os.path.abspath(fds_exe))
            candidates = [
                os.path.join(fds_dir, "INTEL", "bin", "mpirun"),
                os.path.join(fds_dir, "..", "INTEL", "bin", "mpirun"),
            ]
            for c in candidates:
                norm = os.path.normpath(c)
                if os.path.isfile(norm) and os.access(norm, os.X_OK):
                    return norm

        # I_MPI_ROOT 环境变量
        impi_root = os.environ.get("I_MPI_ROOT")
        if impi_root:
            c = os.path.join(impi_root, "bin", "mpirun")
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c

        # PATH 中的 mpirun
        try:
            cmd = "where" if os.name == "nt" else "which"
            result = subprocess.run([cmd, "mpirun"], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[0]
        except Exception:
            pass

        return None

    def _on_fds_output(self):
        """FDS输出"""
        output = (
            self._fds_process.readAllStandardOutput()
            .data()
            .decode("utf-8", errors="ignore")
        )
        if output:
            lines = output.strip().split("\n")
            if lines:
                self.progress_label.setText(lines[-1][:100])
                self.output_text.setText("\n".join(lines[-5:]))

    def _parse_window_flux(self):
        """Parse `*_devc.csv` for the `window_heat_flux` channel."""
        work_dir = getattr(self, "_current_fds_path", None)
        if not work_dir:
            return
        work_dir = os.path.dirname(work_dir)
        import glob
        csv_files = glob.glob(os.path.join(work_dir, "*_devc.csv"))
        if not csv_files:
            return
        try:
            with open(csv_files[0], "r") as f:
                lines = f.readlines()
            if len(lines) < 2:
                return
            header = [h.strip() for h in lines[0].split(",")]
            # Find window_heat_flux column index
            col = None
            for i, h in enumerate(header):
                if "window_heat_flux" in h or "WINDOW_HEAT_FLUX" in h:
                    col = i
                    break
            if col is None:
                return
            # Parse last few rows for current and peak value
            values = []
            for row in lines[1:]:
                parts = row.split(",")
                if len(parts) > col:
                    try:
                        v = float(parts[col])
                        values.append(v)
                    except ValueError:
                        pass
            if values:
                latest = values[-1]
                peak = max(values)
                self.flux_label.setText(f"窗口热通量: {latest:.1f} kW/m²")
                self.flux_peak_label.setText(f"峰值: {peak:.1f} kW/m²")
                # Color-code: yellow for moderate, red for high
                if peak > 100:
                    self.flux_label.setStyleSheet(
                        "color: #f38ba8; font-size: 12px; font-weight: bold;"
                    )
                elif peak > 20:
                    self.flux_label.setStyleSheet(
                        "color: #f9e2af; font-size: 12px; font-weight: bold;"
                    )
                else:
                    self.flux_label.setStyleSheet(
                        "color: #a6e3a1; font-size: 12px; font-weight: bold;"
                    )
        except Exception:
            pass

    def _on_fds_finished(self, exit_code, exit_status):
        """FDS完成"""
        self.run_fds_btn.setEnabled(True)
        self.stop_fds_btn.setEnabled(False)

        if exit_code == 0:
            self.progress_label.setText("仿真完成!")
            self._parse_window_flux()
        else:
            # Decode Windows NTSTATUS codes
            hint = ""
            unsigned = exit_code & 0xFFFFFFFF
            if unsigned == 0xC0000135:
                hint = "\n原因: 缺少DLL（STATUS_DLL_NOT_FOUND）\n请确保MPI和FDS运行时DLL在系统PATH中"
            elif unsigned == 0xC0000142:
                hint = "\n原因: DLL初始化失败\n请检查FDS版本与系统兼容性"
            self.progress_label.setText(
                f"仿真失败 (退出码: {exit_code} / 0x{unsigned:08X})"
            )
            if hint:
                self.output_text.setText(self.output_text.text() + hint)

    def stop_fds_simulation(self):
        """停止FDS仿真"""
        if hasattr(self, "_fds_process") and self._fds_process:
            self._fds_process.kill()
            self._fds_process.waitForFinished()
            self.progress_label.setText("已停止")
            self.run_fds_btn.setEnabled(True)
            self.stop_fds_btn.setEnabled(False)

    def open_smokeview(self):
        """用Smokeview打开结果"""
        smv_file = getattr(self, "_current_smv_file", None)
        if not smv_file or not os.path.exists(smv_file):
            from PySide6.QtWidgets import QMessageBox

            msg = f"找不到仿真结果文件:\n{smv_file}" if smv_file else "未运行仿真"
            if (
                hasattr(self, "_fds_process")
                and self._fds_process
                and self._fds_process.state() != QProcess.NotRunning
            ):
                msg += "\n\n仿真正在运行中，请稍等片刻再试。"
            QMessageBox.warning(self, "提示", msg)
            return

        # 查找smokeview
        smv_exe = self._find_smokeview_exe()
        if not smv_exe:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self,
                "未找到Smokeview",
                "未找到Smokeview可执行文件。请确保Smokeview已安装并添加到系统PATH。",
            )
            return

        # 启动smokeview
        try:
            subprocess.Popen([smv_exe, smv_file])
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "错误", f"无法启动Smokeview: {str(e)}")

    def _find_smokeview_exe(self):
        """查找Smokeview可执行文件"""
        # 先检查用户设置的路径
        from ui.mainwindow import MainWindow

        user_path = MainWindow._load_program_path("smokeview")
        if user_path and os.path.exists(user_path):
            return user_path

        # 跨平台: Windows用where, Linux/macOS用which
        try:
            cmd = "where" if os.name == "nt" else "which"
            result = subprocess.run(
                [cmd, "smokeview"], capture_output=True, text=True
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[0]
        except:
            pass

        # Windows 常见安装路径
        common_paths = [
            "smokeview",
            "C:/Program Files/FDS/Smokeview/bin/smokeview.exe",
            "C:/Program Files (x86)/FDS/Smokeview/bin/smokeview.exe",
            "C:/FDS/Smokeview/bin/smokeview.exe",
        ]
        # Linux 常见安装路径
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
    def _update_default_output_labels(self, model):
        """Update labels showing default auto-generated slices/devices."""
        buildings = model.building_group.buildings
        total_h = model.total_height
        lines_s = []
        lines_d = []
        for b in buildings:
            cx, cy = 0.0, 0.0  # FDS coords centered
            cz = total_h / 2
            lines_s.append(f"PBX={cx:.1f} TEMP")
            lines_s.append(f"PBY={cy:.1f} TEMP+HRRPUV")
            lines_s.append(f"PBZ={cz:.1f} TEMP")
            for story in b.stories:
                z_mid = story.z_bottom + story.height / 2
                lines_d.append(
                    f"{b.name}_{story.name} ({b.x_offset:.0f},{b.y_offset:.0f},{z_mid:.1f})"
                )
        self._default_slice_label.setText(
            "默认切片: " + "; ".join(lines_s) if lines_s else "默认切片: (无建筑)"
        )
        self._default_device_label.setText(
            "默认测点: " + "; ".join(lines_d) if lines_d else "默认测点: (无建筑)"
        )

    def sync_ui_from_model(self, model):
        """从模型同步UI状态"""
        self._syncing = True
        try:
            hs = model.heat_source
            # uses kW/m²
            self.heat_flux_spin.setValue(hs.get("net_heat_flux", 1000))
            self.heat_azimuth_slider.setValue(hs.get("azimuth", 0))
            elev = hs.get("elevation", 0)
            elev_idx = {0: 0, 30: 1, 45: 2, 60: 3}.get(elev, 0)
            self.heat_elevation_slider.setValue(elev_idx)
            self.heat_duration_spin.setValue(hs.get("duration", 1.36))
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
        # UI uses kW/m², model stores MW/m², convert.
        m.heat_source = {
            "azimuth": self.heat_azimuth_slider.value(),
            "elevation": self._ELEV_VALUES[min(self.heat_elevation_slider.value(), 3)],
            "net_heat_flux": self.heat_flux_spin.value(),
            "duration": self.heat_duration_spin.value(),
        }
        m.simulation_time = self.sim_time_spin.value()
        m.domain["grid_size"] = float(self.grid_size_spin.value())
        # Mesh count is no longer user-configurable: always use the generator
        # default (4 meshes, 2×2) for MPI parallel execution.
        m.domain.pop("num_meshes", None)

    # ── 工程快速预测 ────────────────────────────────────────
    def run_predict(self):
        """运行工程快速预测（使用 agent_damage 的融合模型）"""
        from PySide6.QtWidgets import QMessageBox
        import time

        if not hasattr(self, "model") or not self.model.buildings:
            QMessageBox.warning(self, "预测", "当前没有展示的设施")
            return

        try:
            from agent_damage.src.inference import (
                CheckpointError,
                group_to_facility,
                list_available_checkpoints,
                load_predictor_from_checkpoints,
                nearest_enum,
            )
            from agent_damage.src.processing.heat_source import (
                AZIMUTH_OPTIONS,
                DURATION_OPTIONS,
                ELEVATION_OPTIONS,
                HEAT_FLUX_OPTIONS,
                HeatSourceParams,
            )
            from ui.damage_result_dialog import DamageResultDialog
        except ImportError as exc:
            QMessageBox.critical(
                self,
                "预测失败",
                f"无法导入 agent_damage 模块：{exc}",
            )
            return

        # 1. Build heat source, clamping UI values to enum-valid options.
        # UI heat_flux is now kW/m²; convert to nearest enum value (stored as kW/m²).
        ui_flux_kw = max(self.heat_flux_spin.value(), 1e-3)
        try:
            heat_source = HeatSourceParams(
                elevation=ELEVATION_OPTIONS[min(self.heat_elevation_slider.value(), 3)],
                azimuth=int(nearest_enum(self.heat_azimuth_slider.value(), AZIMUTH_OPTIONS)),
                duration=float(self.heat_duration_spin.value()),
                heat_flux=float(nearest_enum(ui_flux_kw, HEAT_FLUX_OPTIONS)),
            )
        except ValueError as exc:
            QMessageBox.critical(self, "预测失败", f"热源参数无效：{exc}")
            return

        # 2. Load the ensemble predictor from checkpoints.
        try:
            predictor = load_predictor_from_checkpoints()
        except CheckpointError as exc:
            available = list_available_checkpoints()
            msg = str(exc)
            if available:
                msg += "\n\n当前检测到: " + ", ".join(available)
            msg += (
                "\n\n请先在 agent_damage 目录下运行训练脚本：\n"
                "    python agent_damage/scripts/generate_data.py\n"
                "    python agent_damage/scripts/train.py --models svm rf mlp cnn1d"
            )
            QMessageBox.warning(self, "预测", msg)
            return
        except Exception as exc:
            QMessageBox.critical(self, "预测失败", f"加载模型失败：{exc}")
            return

        # 3. Convert main-app BuildingGroup → agent_damage Facility and predict.
        try:
            facility = group_to_facility(self.model)
            if not facility.buildings:
                QMessageBox.warning(self, "预测", "当前设施没有可预测的建筑")
                return
            t0 = time.perf_counter()
            result = predictor.predict_facility(facility, heat_source)
            infer_ms = (time.perf_counter() - t0) * 1000.0
        except Exception as exc:
            import traceback

            traceback.print_exc()
            QMessageBox.critical(self, "预测失败", f"推理出错：{exc}")
            return

        # 4. Display beautified dialog.
        model_names = [name.upper() for name in predictor.models.keys()]
        dialog = DamageResultDialog(
            facility_result=result,
            heat_source=heat_source,
            infer_time_ms=infer_ms,
            model_names=model_names,
            algorithm="max",
            parent=self,
        )
        dialog.exec()
