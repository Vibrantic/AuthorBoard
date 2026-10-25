# SPDX-License-Identifier: GPL-3.0-or-later
"""Attachments, comments panel, editor formatting, tags autocomplete, connection filters, global note types, save/load round trip.

Run directly (``python tests/test_integration.py``) or all together with ``python tests/run_all.py``.
The tests run Qt headless (QT_QPA_PLATFORM=offscreen) against a temporary
AUTHORBOARD_HOME, so they never touch your real library.
"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ab-test-")
home = os.path.join(TMP, "home"); os.makedirs(home); os.environ["AUTHORBOARD_HOME"] = home; os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, Qt, QTimer, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QColor, QTextCursor, QTextCharFormat
from PySide6.QtTest import QTest
import main as M
from main import MainWindow
from theme import apply_dark_palette
from models import CommentData, NoteTypeData
import rich_text as rt
from settings import settings
from storage import Storage
app = QApplication([]); app.setStyle("Fusion"); apply_dark_palette(app)
w = MainWindow(); w.resize(1500, 950); w.show(); app.processEvents()
b = w.library.new_book(); b.title = "T"; w.library.add_book(b); w.open_book(b); app.processEvents()
s, ins = w.scene, w.inspector
def png(color="#4da6ff"):
    img = QImage(60, 30, QImage.Format_ARGB32); img.fill(QColor(color)); ba = QByteArray(); bf = QBuffer(ba); bf.open(QIODevice.WriteOnly); img.save(bf, "PNG"); return bytes(ba)

n = s.create_note("character", QPointF(0, 0)); n.model.title = "Mira"; app.processEvents()
ins.set_note(n)
# ---- Anhaenge (Datei) + Undo
f = os.path.join(home, "map.txt"); open(f, "w").write("hello")
ins.attach_paths([f]); w.checkpoint(); assert len(n.model.attachments) == 1 and ins.attach_list.count() == 1
big = os.path.join(home, "pic.png"); open(big, "wb").write(png())
ins.attach_paths([big]); w.checkpoint(); assert ins.attach_list.count() == 2
w.undo(); n = list(s.note_lookup.values())[0]; assert len(n.model.attachments) == 1
w.redo(); n = list(s.note_lookup.values())[0]; assert len(n.model.attachments) == 2
assert w.attachments.blobs and len(w.attachments.blobs) == 2        # Bytes bleiben im Speicher (Undo-sicher)
# ---- Rich text im Inspector: Kommentar + Bild + Link
ins.set_note(n); e = ins.content_edit
e.setPlainText("Mira walks into the Aschenwald at dawn."); app.processEvents()
c = e.textCursor(); c.setPosition(11); c.setPosition(15, QTextCursor.KeepAnchor)
com = CommentData(text="Which road?", quote=c.selectedText()); n.model.comments.append(com)
fm = QTextCharFormat(); fm.setToolTip(rt.COMMENT_PREFIX + com.id); c.mergeCharFormat(fm); app.processEvents()
assert n.model.rich and rt.COMMENT_PREFIX + com.id in n.model.rich and n.model.content.startswith("Mira walks")
e.moveCursor(QTextCursor.End); att = e.insert_image_bytes("dot.png", png("#e8505b")); app.processEvents()
assert att.inline and "attachment:" + att.id in n.model.rich
w.checkpoint(); w.refresh_views(); app.processEvents()
assert w.comments_panel.list.count() == 1 and "(1)" in w.right_panel.tabText(1), w.right_panel.tabText(1)
# ---- Kommentar im Panel -> Editor mit Fokus
from editor_dialog import NoteEditorDialog
dlg = NoteEditorDialog(n.model, w.attachments, w, focus_comment=com.id); dlg.show(); app.processEvents()
QTest.qWait(150); sel = dlg.edit.textCursor().selectedText(); print("editor focus selection:", repr(sel)); assert sel == "into"
dlg.edit.selectAll(); dlg._toggle_bold(True); dlg._apply_text_color(QColor("#ff0000")); dlg._apply_highlight(QColor("#fff176"))
dlg.edit.moveCursor(QTextCursor.Start); dlg.edit.moveCursor(QTextCursor.EndOfWord, QTextCursor.KeepAnchor); dlg.edit.set_link("https://example.org")
dlg.accept(); assert dlg.result_rich() and "font-weight" in dlg.result_rich() and "https://example.org" in dlg.result_rich() and "background-color" in dlg.result_rich()
assert dlg.result_comments()[0].text == "Which road?"
# ---- Panel-Loeschen entfernt Marker
w.delete_comment(n, com.id); assert not n.model.comments and rt.COMMENT_PREFIX not in n.model.rich
w.undo(); n = list(s.note_lookup.values())[0]; assert n.model.comments and rt.COMMENT_PREFIX in n.model.rich
# ---- Tags: Merken + Autocomplete
ins.set_note(n); ins.tags_edit.setText("magic, hero, "); ins.tags_edit.textEdited.emit("magic, hero, ")
assert {"magic", "hero"} <= w.known_tags
ins.tags_edit.setText("ma"); ins.tags_edit.setCursorPosition(2); ins.tags_edit._update_completion()
assert "magic" in ins.tags_edit._model.stringList() and ins.tags_edit._completer.completionCount() == 1
ins.tags_edit._insert_completion("magic"); assert ins.tags_edit.text() == "magic, "
ins.tags_edit.setText("magic, he"); ins.tags_edit.setCursorPosition(9); ins.tags_edit._update_completion()
assert "magic" not in ins.tags_edit._model.stringList() and "hero" in ins.tags_edit._model.stringList()
# ---- Verbindungen: Suche/Filter
m2 = s.create_note("location", QPointF(300, 0)); m2.model.title = "Aschenwald"; m3 = s.create_note("idea", QPointF(0, 300)); m3.model.title = "Bridge"
p1, p2, p3 = n.add_pin(60, 60), m2.add_pin(60, 60), m3.add_pin(60, 60)
s.create_connection(p1, p2).set_label("lives in"); s.create_connection(p1, p3)
ins.set_note(n); print("links:", [ins.links_list.item(i).text() for i in range(ins.links_list.count())]); assert ins.links_list.count() >= 3
ins.links_search.setText("wald"); assert all("wald" in ins.links_list.item(i).text().lower() for i in range(ins.links_list.count())) and ins.links_list.count() >= 1
ins.links_search.setText(""); ins.links_kind.setCurrentIndex(ins.links_kind.findData("thread")); assert ins.links_list.count() == 2
ins.links_type.setCurrentIndex(ins.links_type.findData("idea")); assert ins.links_list.count() == 1
ins.links_type.setCurrentIndex(0); ins.links_kind.setCurrentIndex(0)
# ---- Sperren per Inspector
ins.lock_check.setChecked(True); assert n.model.locked and not (n.flags() & n.GraphicsItemFlag.ItemIsMovable)
w.toggle_lock_selected()  # nothing selected -> message only
# ---- Typen: global + Buch
settings.set_global_types([NoteTypeData("global_spell", "Spell", "#b2dfdb", ["Cost"])]); w.reset_types(w.book_type_list(), keep_unknown=True)
assert "global_spell" in w.note_types and w.note_types["global_spell"].attributes == ["Cost"]
sp = s.create_note("global_spell", QPointF(500, 500)); assert sp.model.attributes[0].name == "Cost"
w.checkpoint()
# ---- Speichern + neu Laden: alles zurueck, Blobs im File
w.save_project(); path = w.library.book_path(b)
data = open(path, encoding="utf-8").read(); import json; d = json.loads(data)
print("file keys:", sorted(d.keys())); assert len(d["attachment_data"]) == 3 and "magic" in d["known_tags"] and any(t["key"] == "global_spell" for t in d["custom_types"])
settings.set_global_types([])                       # Typ lokal nicht mehr definiert -> reist mit der Datei
w.show_shelf(); w.open_book(b); app.processEvents()
assert len(w.attachments.blobs) == 3 and "magic" in w.known_tags and "global_spell" in w.note_types
n2 = [x for x in w.scene.note_lookup.values() if x.model.title == "Mira"][0]
assert n2.model.locked and len(n2.model.attachments) == 3 and n2.model.comments and rt.COMMENT_PREFIX in n2.model.rich
w.inspector.set_note(n2); app.processEvents()
img = w.attachments.image(n2.model.attachments[-1].id); assert img is not None
url = QUrl("attachment:" + att.id)
resource = w.inspector.content_edit.document().resource(
    QTextDocument.ResourceType.ImageResource, url)
assert resource is not None, "image resource should resolve from the attachment store"
w.grab().save(os.path.join(TMP, "integration.png"))
print("ALL OK")
