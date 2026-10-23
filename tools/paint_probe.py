#!/usr/bin/env python3
"""Measure the real QGraphicsView paint path (what the user sees when panning).

    python tools/paint_probe.py showcase/_stress_2000.json
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ab-paint-")
os.environ["AUTHORBOARD_HOME"] = os.path.join(TMP, "home")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF

import i18n
i18n.set_language("en")
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
app.processEvents()

# Go to 1:1 and centre on the middle of the content
w.view.reset_zoom()
w.view.centerOn(w.scene.itemsBoundingRect().center())
app.processEvents()


def paint_frames(label, n=20, step_px=0):
    """Render the *view* (not the scene) n times, moving by step_px each frame.

    ``view.grab()`` calls QGraphicsView::paintEvent, which is the same path
    the compositor uses — it goes through the item caches.
    """
    times = []
    for i in range(n):
        # Move the view so we exercise the pan path, not a static view.
        if step_px:
            w.view.horizontalScrollBar().setValue(
                w.view.horizontalScrollBar().value() + step_px)
        app.processEvents()
        t0 = time.perf_counter()
        img = w.view.grab()          # triggers paintEvent
        print('visible thread count:', w.scene._visible_thread_count)
        dt = (time.perf_counter() - t0) * 1000
        times.append(dt)
    print(f"  {label} frames (ms):", [f"{t:.1f}" for t in times])
    print(f"  {label} median: {sorted(times)[len(times)//2]:.2f} ms, "
          f"mean: {sum(times)/len(times):.2f} ms")
    return times


print(f"  notes={len(w.scene.note_lookup)}  threads={len(w.scene.connection_items)}")
print("== static 1:1 (no panning) ==")
paint_frames("static", n=20, step_px=0)

print("== panning 1:1 (moves 8 px per frame, like a slow drag) ==")
paint_frames("pan", n=40, step_px=8)

print("== after panning settles ==")
paint_frames("settled", n=20, step_px=0)

print("== fit-all (zoomed out, many items visible) ==")
w.view.fit_all()
app.processEvents()
paint_frames("fit", n=20, step_px=0)

print("== fit-all, cache disabled ==")
for it in list(w.scene.note_lookup.values()) + list(w.scene.pin_lookup.values()):
    it.setCacheMode(it.CacheMode.NoCache)
app.processEvents()
paint_frames("fit-nocache", n=10, step_px=0)

print("== fit-all, cache re-enabled ==")
for it in list(w.scene.note_lookup.values()) + list(w.scene.pin_lookup.values()):
    it.setCacheMode(it.CacheMode.DeviceCoordinateCache)
app.processEvents()
paint_frames("fit-cache", n=10, step_px=0)

print("DONE")