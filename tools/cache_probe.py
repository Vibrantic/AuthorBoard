#!/usr/bin/env python3
"""Minimal reproduction: is DeviceCoordinateCache working at all?"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys, time
from PySide6.QtWidgets import QApplication, QGraphicsScene, QGraphicsRectItem, QGraphicsView
from PySide6.QtGui import QImage, QPainter, QColor, QBrush
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QGraphicsItem


app = QApplication(sys.argv)


def time_render(scene, rect, n=5):
    img = QImage(1600, 1000, QImage.Format.Format_ARGB32)
    times = []
    for _ in range(n):
        img.fill(0xFF15161A)
        t0 = time.perf_counter()
        p = QPainter(img)
        scene.render(p, QRectF(img.rect()), rect)
        p.end()
        times.append((time.perf_counter() - t0) * 1000)
    return times


# --- Control: 20 plain QGraphicsRectItems, no custom paint ---
print("== control: 20 plain QGraphicsRectItems ==")
scene = QGraphicsScene()
rect = QRectF(0, 0, 200, 150)
for i in range(20):
    item = QGraphicsRectItem(rect)
    item.setBrush(QBrush(QColor(255, 240, 150)))
    item.setPen(QColor(0, 0, 0, 45))
    item.setPos((i % 5) * 220, (i // 5) * 170)
    item.setCacheMode(QGraphicsRectItem.CacheMode.DeviceCoordinateCache)
    scene.addItem(item)
scene.setSceneRect(0, 0, 1100, 680)
times = time_render(scene, QRectF(0, 0, 1100, 680))
print("  frames (ms):", [f"{t:.1f}" for t in times])

# --- Our NoteItem, cache on ---
print("== NoteItem, cache on ==")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import NoteData
from note_item import NoteItem
from theme import apply_dark_palette
apply_dark_palette(app)

scene2 = QGraphicsScene()
for i in range(20):
    nd = NoteData(x=(i % 5) * 220.0, y=(i // 5) * 170.0,
                  title=f"Note {i}", content="hello world " * 5, tags=["a", "b"])
    nd.pins = []
    item = NoteItem(nd)
    scene2.addItem(item)
scene2.setSceneRect(0, 0, 1100, 680)
times = time_render(scene2, QRectF(0, 0, 1100, 680))
print("  frames (ms):", [f"{t:.1f}" for t in times])

# --- Our NoteItem, cache off ---
print("== NoteItem, cache OFF ==")
for it in scene2.items():
    it.setCacheMode(QGraphicsItem.CacheMode.NoCache) if False else None
for it in scene2.items():
    if hasattr(it, "setCacheMode"):
        it.setCacheMode(it.CacheMode.NoCache)
times = time_render(scene2, QRectF(0, 0, 1100, 680))
print("  frames (ms):", [f"{t:.1f}" for t in times])
print("DONE")