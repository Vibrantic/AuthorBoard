#!/usr/bin/env python3
"""Isolate the cost inside NoteItem.paint.

    python tools/note_paint_probe.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys, time
from PySide6.QtWidgets import QApplication, QGraphicsScene
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QFontMetrics
from PySide6.QtCore import QRectF

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from models import NoteData
from theme import apply_dark_palette
import note_item as ni

app = QApplication([])
app.setStyle("Fusion")
apply_dark_palette(app)

# Representative note: longish content, a few attributes, a few tags.
nd = NoteData(x=0, y=0, width=260, height=200,
              title="Chapter 12",
              content="The fire broke out at midnight and the sky turned to ash. " * 4,
              tags=["war", "fire"],
              )
from models import AttributeData
nd.attributes = [AttributeData("Date", "12.05.1887"),
                 AttributeData("Place", "Ashwood"),
                 AttributeData("Status", "draft")]


def render_one(item, iterations=200):
    img = QImage(260, 200, QImage.Format.Format_ARGB32)
    img.fill(0xFF15161A)
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        p = QPainter(img)
        item.paint(p, _FakeOption(), None)
        p.end()
        times.append((time.perf_counter() - t0) * 1_000_000)  # µs
    times = times[10:]        # drop warmup
    return min(times), sum(times) / len(times)


class _FakeOption:
    def levelOfDetailFromTransform(self, t):
        return 1.0


# --- full paint ---
item = ni.NoteItem(nd)
item.setPos(0, 0)
lo, avg = render_one(item)
print(f"full paint              : min {lo:.0f} µs  avg {avg:.0f} µs")


# --- patch paint: skip body text ---
_orig = ni.NoteItem.paint


def _paint_no_body(self, painter, option, widget=None):
    m = self.model
    saved = m.content
    m.content = ""
    try:
        _orig(self, painter, option, widget)
    finally:
        m.content = saved


ni.NoteItem.paint = _paint_no_body
lo, avg = render_one(item)
print(f"full paint, no body text: min {lo:.0f} µs  avg {avg:.0f} µs")
ni.NoteItem.paint = _orig


# --- patch paint: skip attribute loop ---
def _paint_no_attrs(self, painter, option, widget=None):
    saved = self.model.attributes
    self.model.attributes = []
    try:
        _orig(self, painter, option, widget)
    finally:
        self.model.attributes = saved


ni.NoteItem.paint = _paint_no_attrs
lo, avg = render_one(item)
print(f"full paint, no attrs    : min {lo:.0f} µs  avg {avg:.0f} µs")
ni.NoteItem.paint = _orig


# --- patch paint: skip tag chips ---
def _paint_no_tags(self, painter, option, widget=None):
    saved = self.model.tags
    self.model.tags = []
    try:
        _orig(self, painter, option, widget)
    finally:
        self.model.tags = saved


ni.NoteItem.paint = _paint_no_tags
lo, avg = render_one(item)
print(f"full paint, no tags     : min {lo:.0f} µs  avg {avg:.0f} µs")
ni.NoteItem.paint = _orig


# --- patch paint: skip shadow + outline + fold (paper drawing only) ---
def _paint_flat(self, painter, option, widget=None):
    painter.fillRect(self.rect(), QColor(self.model.color))


ni.NoteItem.paint = _paint_flat
lo, avg = render_one(item)
print(f"flat rect (fill only)   : min {lo:.0f} µs  avg {avg:.0f} µs")
ni.NoteItem.paint = _orig


# --- just measure a wrap drawText call on its own ---
img = QImage(260, 200, QImage.Format.Format_ARGB32)
p = QPainter(img)
from PySide6.QtGui import QTextOption
opt = QTextOption()
opt.setWrapMode(QTextOption.WrapMode.WordWrap)
long_text = nd.content * 4       # ensure the text overflows the rect
times = []
for _ in range(200):
    t0 = time.perf_counter()
    p.setFont(ni._BODY_FONT)
    p.drawText(QRectF(14, 56, 232, 100), long_text, opt)
    times.append((time.perf_counter() - t0) * 1_000_000)
p.end()
times = times[10:]
print(f"one wrapped drawText    : min {min(times):.0f} µs  avg {sum(times)/len(times):.0f} µs")


# --- QFontMetrics construction cost ---
times = []
for _ in range(1000):
    t0 = time.perf_counter()
    fm = QFontMetrics(ni._ATTR_FONT)
    _ = fm.horizontalAdvance("Date: 12.05.1887")
    times.append((time.perf_counter() - t0) * 1_000_000)
print(f"QFontMetrics+measure    : min {min(times):.0f} µs  avg {sum(times)/len(times):.0f} µs")
print("DONE")

# --- does the cache actually prevent paint calls? ---
scene = QGraphicsScene()
item2 = ni.NoteItem(nd)
item2.setPos(0, 0)
scene.addItem(item2)
scene.setSceneRect(-200, -200, 700, 600)

from PySide6.QtGui import QImage

paint_calls = [0]
_orig_paint = ni.NoteItem.paint
def _counting_paint(self, painter, option, widget=None):
    paint_calls[0] += 1
    _orig_paint(self, painter, option, widget)
ni.NoteItem.paint = _counting_paint

# render the scene 5 times
for i in range(5):
    paint_calls[0] = 0
    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    img.fill(0xFF15161A)
    p = QPainter(img)
    scene.render(p, QRectF(img.rect()), QRectF(-200, -200, 700, 600))
    p.end()
    print(f"scene.render frame {i+1}: NoteItem.paint called {paint_calls[0]} times")

ni.NoteItem.paint = _orig_paint

# Does drawBackground dominate? Render with and without it.

# Patch to disable background drawing:
orig_bg = w.scene.drawBackground
def no_bg(painter, rect):
    painter.fillRect(rect, QColor("#15161a"))
w.scene.drawBackground = no_bg

# re-run static 1:1 frames...