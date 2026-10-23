#!/usr/bin/env python3
"""Compare BSP index vs NoIndex (Optimization.md 1.9).

    python tools/bsp_probe.py showcase/_stress_2000_clusters.json
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["AUTHORBOARD_HOME"] = tempfile.mkdtemp(prefix="ab-bsp-")

from PySide6.QtWidgets import QApplication, QGraphicsScene
from PySide6.QtCore import QPointF

import i18n
i18n.set_language("en")
from theme import apply_dark_palette
from main import MainWindow
from storage import Storage

app = QApplication([])
app.setStyle("Fusion")
apply_dark_palette(app)

project = Storage.load(sys.argv[1])
w = MainWindow()
w.resize(1600, 1000)
w.show()
w.restore_project(project, fit=True)
app.processEvents()
w.view.reset_zoom()
w.view.centerOn(w.scene.itemsBoundingRect().center())
app.processEvents()

scene = w.scene


def measure(label, n_frames=30):
    """Measure: 30 pan frames, 30 drag frames on one note, 5 add/remove cycles."""
    # --- pan ---
    h = w.view.horizontalScrollBar()
    w.view.grab()                     # warm up
    t0 = time.perf_counter()
    for _ in range(n_frames):
        h.setValue(h.value() + 8)
        app.processEvents()
        w.view.grab()
    pan_ms = (time.perf_counter() - t0) * 1000 / n_frames

    # --- drag a note ---
    note = next(iter(scene.note_lookup.values()))
    start = note.pos()
    w.view.grab()                     # warm up
    t0 = time.perf_counter()
    for i in range(n_frames):
        note.setPos(start.x() + i, start.y() + i)
        app.processEvents()
        w.view.grab()
    note.setPos(start)
    drag_ms = (time.perf_counter() - t0) * 1000 / n_frames

    # --- add / remove cycle (BSP rebalance cost) ---
    from models import NoteData
    t0 = time.perf_counter()
    for _ in range(5):
        data = NoteData(x=0, y=0, title="tmp", content="x")
        item = scene.add_note_item(data)
        app.processEvents()
        scene.remove_note(item)
        app.processEvents()
    add_remove_ms = (time.perf_counter() - t0) * 1000 / 5

    print(f"  {label:20s} pan {pan_ms:6.2f} ms | drag {drag_ms:6.2f} ms | "
          f"add/remove {add_remove_ms:6.2f} ms")
    return pan_ms, drag_ms, add_remove_ms


print(f"notes={len(scene.note_lookup)}  threads={len(scene.connection_items)}  "
      f"scene_rect={scene.sceneRect().width():.0f}x{scene.sceneRect().height():.0f}")

print("== BspTreeIndex (default) ==")
scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)
app.processEvents()
bsp = measure("BSP")

print("== NoIndex ==")
scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
app.processEvents()
no = measure("NoIndex")

print("== BspTreeIndex again (warm) ==")
scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)
app.processEvents()
bsp2 = measure("BSP (warm)")

print()
print(f"pan:        BSP {bsp[0]:.2f}  vs  NoIndex {no[0]:.2f}  "
      f"({'NoIndex faster' if no[0] < bsp[0] * 0.9 else 'BSP faster' if bsp[0] < no[0] * 0.9 else 'roughly equal'})")
print(f"drag:       BSP {bsp[1]:.2f}  vs  NoIndex {no[1]:.2f}  "
      f"({'NoIndex faster' if no[1] < bsp[1] * 0.9 else 'BSP faster' if bsp[1] < no[1] * 0.9 else 'roughly equal'})")
print(f"add/remove: BSP {bsp[2]:.2f}  vs  NoIndex {no[2]:.2f}  "
      f"({'NoIndex faster' if no[2] < bsp[2] * 0.9 else 'BSP faster' if bsp[2] < no[2] * 0.9 else 'roughly equal'})")
print("DONE")