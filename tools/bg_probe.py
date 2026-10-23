#!/usr/bin/env python3
"""Isolate what dominates the 136 ms 1:1 frame."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import tempfile
os.environ["AUTHORBOARD_HOME"] = tempfile.mkdtemp(prefix="ab-bg-")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPainter
import i18n; i18n.set_language("en")
from theme import apply_dark_palette
from main import MainWindow
from storage import Storage

app = QApplication([])
app.setStyle("Fusion")
apply_dark_palette(app)

w = MainWindow()
w.resize(1600, 1000)
w.show()
app.processEvents()
w.restore_project(Storage.load(sys.argv[1]), fit=True)
w.view.reset_zoom()
w.view.centerOn(w.scene.itemsBoundingRect().center())
app.processEvents()

def frames(label, n=15):
    times = []
    for _ in range(n):
        app.processEvents()
        t0 = time.perf_counter()
        w.view.grab()
        times.append((time.perf_counter() - t0) * 1000)
    print(f"  {label:35s} median {sorted(times)[len(times)//2]:6.1f} ms  min {min(times):6.1f}")

frames("baseline")

# --- replace drawBackground with plain fill ---
_orig = w.scene.drawBackground
def plain_bg(painter, rect):
    painter.fillRect(rect, QColor("#15161a"))
w.scene.drawBackground = plain_bg
frames("plain fill background")
w.scene.drawBackground = _orig

# --- plain fill + hide all notes (keep only the grid) ---
for item in w.scene.note_lookup.values():
    item.setVisible(False)
for th in w.scene.connection_items:
    th.setVisible(False)
frames("baseline, no notes/threads")
w.scene.drawBackground = plain_bg
frames("plain bg, no notes/threads")
w.scene.drawBackground = _orig

# restore visibility
for item in w.scene.note_lookup.values():
    item.setVisible(True)
for th in w.scene.connection_items:
    th.setVisible(True)

# --- switch update mode ---
from PySide6.QtWidgets import QGraphicsView
w.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
frames("FullViewportUpdate")
w.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
frames("MinimalViewportUpdate")
w.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
frames("BoundingRectViewportUpdate")
w.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
frames("SmartViewportUpdate (baseline)")

print("DONE")