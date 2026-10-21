# SPDX-License-Identifier: GPL-3.0-or-later
"""Reordering shelves by dragging their title (with books), shelf colours and the horizontal timeline widget.

Run directly (``python tests/test_shelf_timeline.py``) or all together with ``python tests/run_all.py``.
The tests run Qt headless (QT_QPA_PLATFORM=offscreen) against a temporary
AUTHORBOARD_HOME, so they never touch your real library.
"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ab-test-")
home = os.path.join(TMP, "home"); os.makedirs(home); os.environ["AUTHORBOARD_HOME"] = home; os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, Qt, QPoint
from PySide6.QtTest import QTest
import main as M
from main import MainWindow
from theme import apply_dark_palette
from models import AttributeData
from shelf import CategoryHeader
app = QApplication([]); app.setStyle("Fusion"); apply_dark_palette(app)
w = MainWindow(); w.resize(1500, 950); w.show(); app.processEvents()
lib = w.library

# --- Regal verschieben (Header ziehen) + Farbe
sc = w.shelf.scene
c0, c1, c2 = [c.id for c in lib.categories]
hdr = [i for i in sc.items() if isinstance(i, CategoryHeader) and i.category.id == c0][0]
y0, y1 = sc.cat_ranges[c0]
class Ev:  # simple Fake-Events
    def __init__(s, y): s._y = y
    def scenePos(s): return QPointF(100, s._y)
    def button(s): return Qt.LeftButton
    def accept(s): pass
start = hdr.pos().y()
hdr.mousePressEvent(Ev(start))
hdr.mouseMoveEvent(Ev(start + 330))     # unter die zweite Kategorie ziehen
moved_items = [it for it, p in hdr._block if it.pos().y() != p.y()]
assert len(moved_items) >= 3, len(moved_items)
hdr.mouseReleaseEvent(Ev(start + 330)); app.processEvents(); app.processEvents()
assert [c.id for c in lib.categories] == [c1, c0, c2], [c.name for c in lib.categories]
print("shelf reorder ok:", [c.name for c in lib.categories])
w.shelf.set_category_color(lib.category(c0), "#4a6fa5")
from library import Library
assert [c.color for c in Library(home).categories] == ["", "#4a6fa5", ""]
w.grab().save(os.path.join(TMP, "shelf2.png"))

# --- Zeitleiste
b = lib.new_book(c0); b.title = "Zeit"; lib.add_book(b); w.open_book(b)
s = w.scene
for title, typ, datum, uhr in [("John – Geburtstag", "event", "18.11.2004", ""), ("Krieg", "event", "1914", ""),
                               ("Gründung", "scene", "12.05.1887", "14:30"), ("Zweite", "scene", "12.05.1887", "15:00"),
                               ("Ohne", "note", "", "")]:
    n = s.create_note(typ, QPointF(0, 0)); n.model.title = title
    for a in n.model.attributes:
        if a.name == "Datum": a.value = datum
        if a.name == "Uhrzeit": a.value = uhr
    if typ == "event": n.model.color = "#ffb74d" if title.startswith("John") else "#e57373"
w.timeline_dock.show(); app.processEvents(); w.refresh_timeline(); app.processEvents()
tl = w.timeline
assert len(tl.entries) == 4 and tl.undated == 1, (len(tl.entries), tl.undated)
tl.resize(1400, 260); tl.fit(); app.processEvents()
john = [e for e in tl.entries if e.title.startswith("John")][0]
pos = tl.point_pos(john); QTest.mouseClick(tl, Qt.LeftButton, Qt.NoModifier, QPoint(int(pos.x()), int(pos.y())))
assert tl.active is john
tl.update(); app.processEvents()
QTest.mouseClick(tl, Qt.LeftButton, Qt.NoModifier, tl._bubble_rects["label"].center().toPoint())
assert john.note.model.id in tl.always
tl.grab().save(os.path.join(TMP, "timeline.png"))
# Sprung
got = []; tl.note_activated.connect(got.append)
QTest.mouseClick(tl, Qt.LeftButton, Qt.NoModifier, tl._bubble_rects["jump"].center().toPoint())
assert got and got[0] is john.note and john.note.isSelected()
# Zoom/Pan
ppd = tl.ppd; QTest.mouseDClick(tl, Qt.LeftButton, Qt.NoModifier, QPoint(5, 20)); 
print("timeline ok; ticks:", [l for _, l in tl._ticks()][:6])
print("ALL OK")
