#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Measure hot paths (Optimization.md Phase 0).

    python tools/profile_board.py board.json

Runs headless; the script sets QT_QPA_PLATFORM itself, so you don't need to
set it in the shell.  Prints aggregate timings for the hot paths plus a
per-frame breakdown of the two render cases (1:1 pan, fit-all) so you can see
whether the device cache is warming up once or being defeated every frame.
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ab-prof-")
os.environ["AUTHORBOARD_HOME"] = os.path.join(TMP, "home")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import QRectF

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
app.processEvents()


def timeit(label, fn, n=1):
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    dt = (time.perf_counter() - t0) / n
    print(f"{label:28s} {dt*1000:8.2f} ms")
    return dt


# ------------------------------------------------------------------ hot paths
timeit("open board", lambda: w.restore_project(project, fit=True), n=3)
s = w.scene
print(f"  notes={len(s.note_lookup)}  threads={len(s.connection_items)}  "
      f"rects={len(s._note_rects)}")

timeit("reapply_filter", s.reapply_filter, n=10)


def refresh():
    for k in w._dirty_flags:
        w._dirty_flags[k] = True
    w.refresh_views()


timeit("refresh_views", refresh, n=5)
timeit("checkpoint", w.checkpoint, n=5)

# ----------------------------------------------------------- render: 1:1 pan
w.view.reset_zoom()                        # 1:1
centre = s.itemsBoundingRect().center()
w.view.centerOn(centre)
app.processEvents()

vp_size = w.view.viewport().size()
visible = w.view.mapToScene(w.view.viewport().rect()).boundingRect()
visible_items = [it for it in s.items(visible) if hasattr(it, "paint")]
print(f"  visible items at 1:1: {len(visible_items)}  "
      f"scene rect {visible.width():.0f} x {visible.height():.0f}")


def render_frame(src_rect, img=None):
    """Render one frame of ``src_rect`` into a viewport-sized image."""
    if img is None:
        img = QImage(vp_size, QImage.Format.Format_ARGB32)
    img.fill(0xFF15161A)
    p = QPainter(img)
    s.render(p, QRectF(img.rect()), src_rect)
    p.end()
    return img


# Warm up once so the very first frame's allocations don't skew the average.
warm_img = QImage(vp_size, QImage.Format.Format_ARGB32)

# per-frame breakdown
times = []
for i in range(20):
    t0 = time.perf_counter()
    render_frame(visible, warm_img)
    times.append((time.perf_counter() - t0) * 1000)
print("  1:1 frames (ms):", [f"{t:.1f}" for t in times])
print(f"  1:1 average (excluding first): {sum(times[1:]) / len(times[1:]):.2f} ms")


# ------------------------------------------------------- render: fit-all
w.view.fit_all()
app.processEvents()
visible_fit = w.view.mapToScene(w.view.viewport().rect()).boundingRect()
visible_fit_items = [it for it in s.items(visible_fit) if hasattr(it, "paint")]
print(f"  visible items at fit: {len(visible_fit_items)}  "
      f"scene rect {visible_fit.width():.0f} x {visible_fit.height():.0f}")

# fresh image — different source rect, so the cache for this viewport is cold
fit_img = QImage(vp_size, QImage.Format.Format_ARGB32)
times_fit = []
for i in range(20):
    t0 = time.perf_counter()
    render_frame(visible_fit, fit_img)
    times_fit.append((time.perf_counter() - t0) * 1000)
print("  fit frames (ms):", [f"{t:.1f}" for t in times_fit])
print(f"  fit average (excluding first): "
      f"{sum(times_fit[1:]) / len(times_fit[1:]):.2f} ms")

print("ALL OK")