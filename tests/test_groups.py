# SPDX-License-Identifier: GPL-3.0-or-later
"""Group frames: creation, geometric membership, nesting, move, undo, save/load.

Run directly (``python tests/test_groups.py``) or all together with ``python tests/run_all.py``.
The tests run Qt headless (QT_QPA_PLATFORM=offscreen) against a temporary
AUTHORBOARD_HOME, so they never touch your real library.
"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ab-test-")
os.environ["AUTHORBOARD_HOME"] = os.path.join(TMP, "home"); os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF
from main import MainWindow
from theme import apply_dark_palette
app = QApplication([]); app.setStyle("Fusion"); apply_dark_palette(app)
w = MainWindow(); w.resize(1400, 900); w.show(); app.processEvents()
b = w.library.new_book(); w.library.add_book(b); w.open_book(b); app.processEvents()
s = w.scene
a = s.create_note("note", QPointF(0, 0)); c = s.create_note("note", QPointF(400, 0)); d = s.create_note("note", QPointF(3000, 0))
c.resize_to(260, 300)
w.checkpoint()

# ---- create a frame around a and c
s.clearSelection(); a.setSelected(True); c.setSelected(True)
g = s.create_group_from_selection(); w.checkpoint()
assert g is not None and len(s.group_lookup) == 1
frames, notes = s.group_members(g)
assert set(notes) == {a, c} and d not in notes and frames == {g}

# ---- moving the frame moves its notes, not d
before = (a.pos(), c.pos(), d.pos())
s.move_block(s.group_block(g), QPointF(100, 50))
assert a.pos() == before[0] + QPointF(100, 50) and c.pos() == before[1] + QPointF(100, 50)
assert d.pos() == before[2]

# ---- a locked note stays while the frame moves
a.set_locked(True)
p = a.pos(); s.move_block(s.group_block(g), QPointF(10, 10)); assert a.pos() == p
a.set_locked(False)
a.setPos(p + QPointF(30, 30))          # bring a back well inside the moved frame

# ---- top frame wins: a smaller, newer frame takes over note a
s.clearSelection(); a.setSelected(True)
g2 = s.create_group_from_selection()
assert s.note_group(a) is g2 and s.note_group(c) is g
assert g2 in s.group_members(g)[0]            # nested frame moves with its parent

# ---- undo / redo / save / load
w.checkpoint()
w.undo(); assert len(s.group_lookup) == 1
w.undo(); assert len(s.group_lookup) == 0
w.redo(); w.redo(); assert len(s.group_lookup) == 2
w.save_project(); w.show_shelf(); w.open_book(b); app.processEvents()
assert len(w.scene.group_lookup) == 2
print("ALL OK")