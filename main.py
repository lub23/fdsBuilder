#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
@File  : main.py
@Author: Bo Lu
@Date  : 2026-01-22
@Version : 1.0
@Desc  : Main program entry
'''



import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from ui.styles import DARK_STYLE
from ui.mainwindow import MainWindow


def _install_quiet_media_logs():
    """Hide QtMultimedia's FFmpeg banner/stream dump and the internal
    QFuture-continuation warning that otherwise clutter the console while
    a demo video is playing."""
    from PySide6.QtCore import qInstallMessageHandler

    def _handler(msg_type, context, message):
        if (context.category or "") == "qt.multimedia.ffmpeg" or message.startswith(
            "Parent future has"
        ):
            return
        if context.category:
            print(f"{context.category}: {message}", file=sys.stderr)
        else:
            print(message, file=sys.stderr)

    qInstallMessageHandler(_handler)


def main():
    _install_quiet_media_logs()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)

    # icon
    # app.setWindowIcon(QIcon("icon.png"))

    window = MainWindow()
    window.resize(1440, 900)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
