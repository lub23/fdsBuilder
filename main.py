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
from PySide6.QtGui import QIcon

from ui.styles import *
from ui.mainwindow import MainWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    
    # icon
    # app.setWindowIcon(QIcon("icon.png"))
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()