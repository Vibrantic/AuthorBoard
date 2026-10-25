# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Dark theme: colours, the Qt style sheet, icons and colour helpers.
"""

from PySide6.QtCore import Qt

from i18n import N_
from PySide6.QtGui import QColor, QPalette, QPixmap, QIcon, QPainter, QPen

ACCENT = "#6c9cff"

PRESET_COLORS = [
    (N_("Blau"), "#4da6ff"),
    (N_("Rot"), "#e8505b"),
    (N_("Grün"), "#4cc38a"),
    (N_("Gelb"), "#ffd54f"),
    (N_("Orange"), "#ff9f43"),
    (N_("Violett"), "#b388ff"),
    (N_("Weiß"), "#f1f1f1"),
    (N_("Schwarz"), "#222222"),
    (N_("Braun"), "#a47148"),
]

CUSTOM_TYPE_COLORS = [
    "#f8bbd0", "#c5e1a5", "#b3e5fc", "#ffe0b2",
    "#d1c4e9", "#b2dfdb", "#f0f4c3", "#ffccbc",
]

GROUP_COLORS = [
    "#4da6ff", "#4cc38a", "#ff9f43", "#b388ff",
    "#ffd54f", "#e8505b", "#26a69a", "#f48fb1",
]

def color_icon(color: str, size: int = 14) -> QIcon:
    """A small rounded colour swatch as QIcon."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(QPen(QColor(255, 255, 255, 70), 1))
    p.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    p.end()

    return QIcon(pm)


def ideal_text_color(color: QColor) -> QColor:
    """Dunkle Schrift auf hellem Grund, helle auf dunklem."""
    lum = (
        0.299 * color.red()
        + 0.587 * color.green()
        + 0.114 * color.blue()
    )
    return QColor("#2b2b30") if lum > 150 else QColor("#f5f5f7")


def apply_dark_palette(app):
    """Give the application a dark QPalette."""
    pal = QPalette()
    R = QPalette.ColorRole

    pal.setColor(R.Window, QColor("#16171b"))
    pal.setColor(R.WindowText, QColor("#e6e6ea"))
    pal.setColor(R.Base, QColor("#1e1f24"))
    pal.setColor(R.AlternateBase, QColor("#26272e"))
    pal.setColor(R.ToolTipBase, QColor("#26272e"))
    pal.setColor(R.ToolTipText, QColor("#e6e6ea"))
    pal.setColor(R.Text, QColor("#e6e6ea"))
    pal.setColor(R.Button, QColor("#26272e"))
    pal.setColor(R.ButtonText, QColor("#e6e6ea"))
    pal.setColor(R.BrightText, QColor("#ff6b6b"))
    pal.setColor(R.Highlight, QColor(ACCENT))
    pal.setColor(R.HighlightedText, QColor("#101114"))
    pal.setColor(R.PlaceholderText, QColor("#7c7c88"))

    app.setPalette(pal)


STYLESHEET = """
QMainWindow, QDialog { background: #16171b; }
QWidget { color: #e6e6ea; font-size: 10pt; }

QToolTip {
    background: #26272e; color: #e6e6ea;
    border: 1px solid #3a3b45; padding: 4px 6px;
}

QMenuBar { background: #1a1b20; padding: 2px; }
QMenuBar::item { padding: 5px 10px; border-radius: 4px; background: transparent; }
QMenuBar::item:selected { background: #2a2c35; }

QMenu {
    background: #1e1f24; border: 1px solid #33343d;
    padding: 6px; border-radius: 6px;
}
QMenu::item { padding: 6px 22px 6px 12px; border-radius: 4px; }
QMenu::item:selected { background: #2f3a57; }
QMenu::separator { height: 1px; background: #33343d; margin: 5px 8px; }

QToolBar {
    background: #1a1b20; border: none;
    border-bottom: 1px solid #2a2b33; spacing: 6px; padding: 5px 8px;
}
QToolBar QToolButton {
    padding: 5px 12px; border-radius: 6px;
    background: transparent; border: none;
}
QToolBar QToolButton:hover { background: #2a2c35; }
QToolBar::separator { width: 1px; background: #2a2b33; margin: 4px 6px; }

QStatusBar { background: #1a1b20; color: #8d8e9a; }

QDockWidget { font-weight: 600; }
QDockWidget::title {
    background: #1a1b20; padding: 9px 12px;
    border-bottom: 1px solid #2a2b33;
}

#SidePanel, #InspectorBody { background: #1a1b20; }
QScrollArea { border: none; background: #1a1b20; }

QLabel#Section {
    color: #8d8e9a; font-size: 8pt; font-weight: 600; margin-top: 6px;
}
QLabel#Muted { color: #8d8e9a; font-size: 9pt; }
QLabel#Hint { color: #7c7c88; font-size: 8pt; }

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
    background: #1e1f24; border: 1px solid #33343d;
    border-radius: 6px; padding: 6px 8px;
    selection-background-color: #3d5a99;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 1px solid #6c9cff;
}
QComboBox QAbstractItemView {
    background: #1e1f24; border: 1px solid #33343d;
    selection-background-color: #2f3a57; outline: 0;
}

QPushButton, QToolButton {
    background: #26272e; border: 1px solid #33343d;
    border-radius: 6px; padding: 6px 12px;
}
QPushButton:hover, QToolButton:hover {
    background: #2f313a; border-color: #444653;
}
QPushButton:pressed, QToolButton:pressed { background: #20212a; }
QPushButton:disabled { color: #6a6b75; }
QToolButton::menu-indicator { image: none; }

QPushButton#Danger { color: #ff8f8f; }
QPushButton#Danger:hover { background: #3a2328; border-color: #6b3a42; }

QTreeWidget, QListWidget, QTableWidget {
    background: #1a1b20; border: none; outline: 0;
    alternate-background-color: #1e1f24;
}
QTreeWidget { border-top: 1px solid #2a2b33; }
QTreeWidget::item, QListWidget::item { padding: 4px 2px; border-radius: 4px; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #24252c; }
QTreeWidget::item:selected, QListWidget::item:selected {
    background: #2f3a57; color: white;
}

QTableWidget {
    background: #1e1f24; border: 1px solid #33343d;
    border-radius: 6px; gridline-color: #2a2b33;
}
QTableWidget::item:selected { background: #2f3a57; color: white; }
QHeaderView::section {
    background: #22232a; color: #8d8e9a; border: none;
    border-bottom: 1px solid #33343d; padding: 5px 8px;
}

QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical {
    background: #3a3b45; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #4a4b57; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal {
    background: #3a3b45; border-radius: 5px; min-width: 30px;
}
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QDialog#Palette { background: #1e1f24; border: 1px solid #6c9cff; }
QDialog#Palette QLineEdit { font-size: 12pt; padding: 10px 12px; }
QDialog#Palette QListWidget { background: #1e1f24; }
QDialog#Palette QListWidget::item { padding: 7px 8px; }

QMessageBox { background: #1e1f24; }

#ShelfBar { background: #16171b; }
QLabel#ShelfTitle { font-size: 20pt; font-weight: 700; color: #e6e6ea; }
QGraphicsView { background: #15161a; }
QTextBrowser { background: #1e1f24; border: 1px solid #33343d; border-radius: 6px; }
QSpinBox { background: #1e1f24; border: 1px solid #33343d; border-radius: 6px; padding: 6px 8px; }
"""
