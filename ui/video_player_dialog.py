#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Video player dialog for pre-rendered condition demo clips (mp4)."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtCore import QTimer
from PySide6.QtCore import QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPolygonF, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QPushButton,
    QVBoxLayout,
)


def format_condition(condition: dict | None) -> str:
    """Render the condition dict as a single human-readable line.

    Example: ``波音卫星制造厂 | 热通量 30000 kW/m² | 持续时间 7.5 s |
    方位角 270° | 俯仰角 60° | 模拟时长 1800 s``
    """
    parts: list[str] = []
    condition = condition or {}
    facility = str(condition.get("facility_name") or "").strip()
    if facility:
        parts.append(facility)
    if condition.get("heat_flux") is not None:
        parts.append(f"热通量 {float(condition['heat_flux']):g} kW/m²")
    if condition.get("duration") is not None:
        parts.append(f"持续时间 {float(condition['duration']):g} s")
    if condition.get("azimuth") is not None:
        parts.append(f"方位角 {int(float(condition['azimuth']))}°")
    if condition.get("elevation") is not None:
        parts.append(f"俯仰角 {int(float(condition['elevation']))}°")
    if condition.get("sim_time") is not None:
        parts.append(f"模拟时长 {float(condition['sim_time']):g} s")
    return "  |  ".join(parts)


def _format_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _media_icon(kind: str, color: str = "#cdd6f4") -> QIcon:
    """Draw a play/pause glyph so the button never depends on the UI font."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    if kind == "play":
        painter.drawPolygon(
            QPolygonF([QPointF(7.0, 4.0), QPointF(7.0, 20.0), QPointF(19.0, 12.0)])
        )
    else:
        painter.drawRect(QRectF(6.0, 4.0, 4.5, 16.0))
        painter.drawRect(QRectF(13.5, 4.0, 4.5, 16.0))
    painter.end()
    return QIcon(pixmap)


class VideoPlayerDialog(QDialog):
    """Modal dialog that plays a local mp4 with play/pause and a seek bar.

    The UI shows the simulation condition (facility name, heat source
    parameters) instead of the video file name.
    """

    def __init__(self, video_path: str, condition: dict | None = None, parent=None):
        super().__init__(parent)
        self.video_path = os.path.abspath(video_path)
        condition_text = format_condition(condition)
        facility = str((condition or {}).get("facility_name") or "").strip()
        self.setWindowTitle(f"工况演示 - {facility}" if facility else "工况演示")
        self.resize(1280, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        if condition_text:
            self.condition_label = QLabel(condition_text)
            self.condition_label.setWordWrap(True)
            self.condition_label.setStyleSheet("color: #89b4fa; font-size: 13px; font-weight: bold;")
            layout.addWidget(self.condition_label)

        self._video_widget = QVideoWidget()
        self._video_widget.setMinimumSize(640, 360)
        layout.addWidget(self._video_widget, 1)

        # ── control row: play/pause icon | seek bar | time | status ──
        control_row = QHBoxLayout()
        control_row.setSpacing(8)

        # Single button that toggles between play and pause states.
        self._icon_play = _media_icon("play")
        self._icon_pause = _media_icon("pause")
        self._play_btn = QPushButton()
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.setCursor(Qt.PointingHandCursor)
        self._play_btn.setIconSize(QSize(20, 20))
        self._play_btn.setIcon(self._icon_pause)  # autoplay: shows the pause glyph
        self._play_btn.setToolTip("暂停")
        self._play_btn.clicked.connect(self._toggle_play)
        control_row.addWidget(self._play_btn)

        self._pos_slider = QSlider(Qt.Horizontal)
        self._pos_slider.setRange(0, 0)
        self._pos_slider.setSingleStep(1)
        self._pos_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._pos_slider.sliderPressed.connect(self._on_slider_pressed)
        self._pos_slider.sliderReleased.connect(self._on_slider_released)
        self._pos_slider.valueChanged.connect(self._on_slider_value_changed)
        control_row.addWidget(self._pos_slider, 1)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFixedWidth(96)
        self.time_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        control_row.addWidget(self.time_label)

        self.status_label = QLabel("播放中")
        self.status_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        control_row.addWidget(self.status_label)
        layout.addLayout(control_row)

        # FFmpeg writes its demux banner directly to C-level stderr, bypassing
        # Qt logging. Mute fd 2 until the media is opened (duration known); a
        # fallback timer guarantees the stream is restored either way.
        self._mute_stderr()
        self._mute_restore_timer = QTimer(self)
        self._mute_restore_timer.setSingleShot(True)
        self._mute_restore_timer.setInterval(2000)
        self._mute_restore_timer.timeout.connect(self._restore_stderr)
        self._audio_output = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.setVideoOutput(self._video_widget)
        self._player.setSource(QUrl.fromLocalFile(self.video_path))
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_player_error)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_media_ready)
        self._seeking = False
        self._mute_restore_timer.start()
        self._player.play()

    # ── C-level stderr muting ───────────────────────
    def _mute_stderr(self):
        if self._stderr_muted():
            return
        try:
            self._stderr_saved = os.dup(2)
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 2)
            os.close(devnull)
            self._stderr_hidden = True
        except OSError:
            self._stderr_hidden = False

    def _stderr_muted(self) -> bool:
        return getattr(self, "_stderr_hidden", False)

    def _restore_stderr(self, *_args):
        self._mute_restore_timer.stop()
        if not self._stderr_muted():
            return
        try:
            os.dup2(self._stderr_saved, 2)
            os.close(self._stderr_saved)
        except (OSError, AttributeError):
            pass
        self._stderr_hidden = False

    def _on_media_ready(self, *_args):
        """Media opened (demux banner printed) — unmute stderr and init the bar."""
        self._restore_stderr()
        self._on_duration_changed(*_args[:1])

    # ── playback control ──────────────────────────────
    def _toggle_play(self):
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._player.play()
        else:  # StoppedState — ended or errored, restart from the beginning
            self._player.setPosition(0)
            self._player.play()

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.status_label.setText("播放中")
            self._play_btn.setIcon(self._icon_pause)
            self._play_btn.setToolTip("暂停")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.status_label.setText("已暂停")
            self._play_btn.setIcon(self._icon_play)
            self._play_btn.setToolTip("播放")
        else:
            self.status_label.setText("播放完成")
            self._play_btn.setIcon(self._icon_play)
            self._play_btn.setToolTip("重新播放")

    def _on_player_error(self, error, message):
        self.status_label.setText(f"播放失败: {message or str(error)}")

    # ── seek bar ──────────────────────────────────────
    def _on_duration_changed(self, duration_ms: int):
        self._pos_slider.setRange(0, max(0, duration_ms // 1000))
        self._refresh_time_label()

    def _on_position_changed(self, position_ms: int):
        if self._seeking:
            return
        self._pos_slider.setValue(position_ms // 1000)
        self._refresh_time_label()

    def _on_slider_pressed(self):
        self._seeking = True

    def _on_slider_released(self):
        self._player.setPosition(self._pos_slider.value() * 1000)
        self._seeking = False

    def _on_slider_value_changed(self):
        if self._seeking:
            self._refresh_time_label()

    def _refresh_time_label(self):
        current = (
            self._pos_slider.value()
            if self._seeking
            else self._player.position() // 1000
        )
        self.time_label.setText(
            f"{_format_time(current)} / {_format_time(self._pos_slider.maximum())}"
        )

    def closeEvent(self, event):
        self._restore_stderr()
        self._player.stop()
        event.accept()
