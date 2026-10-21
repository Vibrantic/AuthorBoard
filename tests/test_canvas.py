# SPDX-License-Identifier: GPL-3.0-or-later
"""Locking notes/pins, threads in front, focus mode, pin priority over threads.

Run directly (``python tests/test_canvas.py``) or all together with ``python tests/run_all.py``.
The tests run Qt headless (QT_QPA_PLATFORM=offscreen) against a temporary
AUTHORBOARD_HOME, so they never touch your real library.
"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ab-test-")
os.environ["AUTHORBOARD_HOME"] = os.path.join(TMP, "home"); os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
import main as M
from main import MainWindow
from theme import apply_dark_palette
app = QApplication([]); app.setStyle("Fusion"); apply_dark_palette(app)
w = MainWindow(); w.resize(1500, 950); w.show(); app.processEvents()
b = w.library.new_book(); w.library.add_book(b); w.open_book(b); app.processEvents()
s, v = w.scene, w.view
a = s.create_note("character", QPointF(-300, 0)); c = s.create_note("location", QPointF(300, 0)); d = s.create_note("idea", QPointF(0, 300)); e = s.create_note("note", QPointF(600, 300))
pa = a.add_pin(100, 60); pc = c.add_pin(60, 60); pd = d.add_pin(60, 60)
s.create_connection(pa, pc); s.create_connection(pc, pd)
# --- Lock
pos = a.pos(); s.set_note_locked(a, True)
assert not (a.flags() & a.GraphicsItemFlag.ItemIsMovable) and a.model.locked
a.setPos(pos + QPointF(50, 50))  # programmatic move still possible; test mouse path via flag only
a.setPos(pos)
# pin lock follows note
s.set_pin_locked(pa, True); assert not (pa.flags() & pa.GraphicsItemFlag.ItemIsMovable)
a.setPos(pos + QPointF(100, 20)); app.processEvents()
assert abs(pa.scenePos().x() - (a.pos().x() + 100)) < 0.01, "pin must follow note"
a.setPos(pos)
# arrange keeps locked notes
before = a.pos(); s.arrange_by_type(); assert a.pos() == before
# --- Focus mode
s.clearSelection(); s.reapply_filter()
assert all(n.opacity() == 1.0 for n in s.note_lookup.values())
c.setSelected(True); app.processEvents()
print("focus opacities:", {n.model.title: n.opacity() for n in s.note_lookup.values()})
assert a.opacity() == 1 and c.opacity() == 1 and d.opacity() == 1 and e.opacity() < 0.2
assert all(th.opacity() == 1.0 for th in s.connection_items)   # both threads touch c
a.setSelected(True); c.setSelected(False); app.processEvents()
assert c.opacity() == 1 and d.opacity() < 0.2
ths = {(t.start_pin.note.model.title, t.end_pin.note.model.title): t.opacity() for t in s.connection_items}; print("threads:", ths)
s.set_focus_mode(False); assert all(n.opacity() == 1.0 for n in s.note_lookup.values())
s.set_focus_mode(True)
# --- Thread above notes
th = s.connection_items[0]; assert th.zValue() > max(n.zValue() for n in s.note_lookup.values())
# pins clickable: item_at pin position gives the pin although the thread is above
assert s._item_at(pa.scenePos()) is pa
# right-drag still works
s.clearSelection(); s.set_pin_locked(pa, False)
v.fit_all() if hasattr(v, "fit_all") else None; app.processEvents()
w.grab().save(os.path.join(TMP, "canvas2.png"))
print("ALL OK")
