# SPDX-License-Identifier: GPL-3.0-or-later
"""FlowView: navigation, layout, editing, edge deletion, re-root."""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ab-test-")
os.environ["AUTHORBOARD_HOME"] = os.path.join(TMP, "home")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF
import i18n; i18n.set_language("en")
from theme import apply_dark_palette
from main import MainWindow
from flow_view import FlowViewDialog

app = QApplication([]); app.setStyle("Fusion"); apply_dark_palette(app)
w = MainWindow(); w.resize(1400, 900); w.show(); app.processEvents()
b = w.library.new_book(); w.library.add_book(b); w.open_book(b); app.processEvents()
s = w.scene

# chain A -> B -> C -> D
a = s.create_note("character", QPointF(0, 0));   a.model.title = "A"
bb = s.create_note("location", QPointF(400, 0));  bb.model.title = "B"
c = s.create_note("idea", QPointF(800, 0));      c.model.title = "C"
d = s.create_note("note", QPointF(1200, 0));     d.model.title = "D"
pa, pb, pc, pd = a.add_pin(100, 60), bb.add_pin(60, 60), c.add_pin(60, 60), d.add_pin(60, 60)
s.create_connection(pa, pb); s.create_connection(pb, pc); s.create_connection(pc, pd)

for i in range(300):
    n = s.create_note("note", QPointF(i * 20, 0))
    n.model.title = f"n{i}"
    if i == 0:
        s.create_connection(root_pin, n.add_pin(10, 10))
    else:
        prev = [x for x in s.note_lookup.values() if x.model.title == f"n{i-1}"][0]
        s.create_connection(prev.pins[0], n.add_pin(10, 10))

dlg.set_root(root)
app.processEvents()
assert dlg.minimap._silhouette is not None
assert dlg.minimap._focus_count <= 1 + len(dlg.board_scene.direct_neighbours(root))

# ---- layout ----
dlg = FlowViewDialog(s, w.attachments, a, parent=w); dlg.show(); app.processEvents()
titles = sorted(n.model().title for n in dlg._scene.nodes)
print("A view:", titles)
assert titles == ["A", "B"], titles

# ---- re-root ----
dlg.set_root(bb); app.processEvents()
titles = sorted(n.model().title for n in dlg._scene.nodes)
print("B view:", titles)
assert titles == ["A", "B", "C"], titles

# ---- edit content ----
dlg.inspector.note = bb
bb.model.title = "B2"; bb.model_changed(); app.processEvents()
node_b = [n for n in dlg._scene.nodes if n.model() is bb.model][0]
assert node_b.model().title == "B2"

# ---- delete edge from FlowView ----
edge_bc = [e for e in dlg._scene.edges
           if {e.source_node.note.model.title, e.target_node.note.model.title} == {"B2", "C"}][0]
dlg._scene.request_delete_edge(edge_bc.connection, edge_bc)
app.processEvents()
titles = sorted(n.model().title for n in dlg._scene.nodes)
print("B after delete:", titles)
assert titles == ["A", "B2"], titles

# ---- single-instance reuse ----
dlg2 = w.open_flow_view  # method reference
w._flow_view = dlg
w.open_flow_view(a); app.processEvents()
assert w._flow_view is dlg
print("ALL OK")