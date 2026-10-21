# SPDX-License-Identifier: GPL-3.0-or-later
"""The inspector dock keeps its width, so the board never shifts when a note is (de)selected.

Run directly (``python tests/test_inspector_stability.py``) or all together with ``python tests/run_all.py``.
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
import main as M
from main import MainWindow
from library import Library
from theme import apply_dark_palette
app = QApplication([]); app.setStyle("Fusion"); apply_dark_palette(app)
w = MainWindow(); w.resize(1400, 900); w.show(); app.processEvents()
b = w.library.new_book(); w.library.add_book(b); w.open_book(b); app.processEvents(); app.processEvents()
v, s = w.view, w.scene
n = s.create_note("note", QPointF(0, 0)); app.processEvents(); w.refresh_views(); app.processEvents()
def snap(): 
    app.processEvents()
    return (v.viewport().width(), round(v.mapToScene(v.viewport().rect().center()).x(),1), w.inspector_dock.width())
for i in range(3):
    s.clearSelection(); a = snap()
    n.setSelected(True); b2 = snap()
    print("deselected", a, "selected", b2, "SAME" if a == b2 else "CHANGED")
i = w.inspector
n.setSelected(True); app.processEvents()
print("selected: min", i.minimumSizeHint(), "hint", i.sizeHint(), "form min", i.form.minimumSizeHint(), "scroll hint", i._scroll.sizeHint())
s.clearSelection(); app.processEvents()
print("empty:    min", i.minimumSizeHint(), "hint", i.sizeHint(), "label hint", i.empty_label.sizeHint(), i.empty_label.minimumSizeHint())
