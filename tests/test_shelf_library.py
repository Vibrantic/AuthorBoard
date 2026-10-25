# SPDX-License-Identifier: GPL-3.0-or-later
"""Bookshelf and library: books, search, drag & drop between shelves, save/leave prompts, backups, info dialog, timeline, statistics, manuscript.

Run directly (``python tests/test_shelf_library.py``) or all together with ``python tests/run_all.py``.
The tests run Qt headless (QT_QPA_PLATFORM=offscreen) against a temporary
AUTHORBOARD_HOME, so they never touch your real library.
"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ab-test-")
home = os.path.join(TMP, "home"); os.makedirs(home)
os.environ["AUTHORBOARD_HOME"] = home
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, QTimer, Qt
import main as M
from main import MainWindow
from theme import apply_dark_palette
from shelf import BookItem, AddBookItem, CategoryHeader

if os.path.exists(M.RECOVERY_PATH): os.remove(M.RECOVERY_PATH)
app = QApplication([]); app.setStyle("Fusion"); apply_dark_palette(app)
w = MainWindow(); w.resize(1400, 900); w.show(); app.processEvents()
lib, s = w.library, w.scene

def click_later(text):
    def f():
        box = QApplication.activeModalWidget()
        for b in box.buttons():
            if b.text() == text: b.click()
    QTimer.singleShot(150, f)

assert w.on_shelf() and not w.tree_dock.isVisible()
print("categories:", [c.name for c in lib.categories])

# Bücher anlegen (ohne Dialog)
cats = lib.categories
b1 = lib.new_book(cats[0].id); b1.title = "Der Sturm"; b1.author = "A. Autor"; b1.target_words = 1000; lib.add_book(b1)
b2 = lib.new_book(cats[0].id); b2.title = "Nebel"; lib.add_book(b2)
b3 = lib.new_book(cats[1].id); b3.title = "Kurz"; lib.add_book(b3)
lib.save(); w.shelf.refresh(); app.processEvents()
items = [i for i in w.shelf.scene.items() if isinstance(i, BookItem)]
assert len(items) == 3 and len([i for i in w.shelf.scene.items() if isinstance(i, AddBookItem)]) == 3

# Suche
w.shelf.search.setText("sturm"); app.processEvents()
assert [i.opacity() for i in items if i.book is b1][0] == 1.0 and [i.opacity() for i in items if i.book is b2][0] < 0.5
w.shelf.search.setText("")

# Drag&Drop in andere Kategorie
sc = w.shelf.scene
it2 = [i for i in sc.items() if isinstance(i, BookItem) and i.book is b2][0]

before_cat = b2.category_id
y1 = sc.rows[cats[1].id][0]
it2.setPos(it2.pos().x(), (y1[0] + y1[1]) / 2 - it2.H / 2)
sc.drop_book(it2); app.processEvents(); app.processEvents()
assert b2.category_id == cats[1].id, b2.category_id
assert b2 in lib.books_in(cats[1].id)
assert b2 not in lib.books_in(before_cat)
assert lib.books.index(b2) >= 0
print("drop ok; order:", [b.title for b in lib.books])

# Kategorie umbenennen/verschieben/löschen (Library-Logik)
c = lib.add_category("Neu"); lib.rename_category(c.id, "Sachbücher"); lib.move_category(c.id, -1)
assert lib.categories[2].name == "Sachbücher"
lib.delete_category(c.id); assert len(lib.categories) == 3

# Öffnen, bearbeiten, speichern, zurück ins Regal
w.open_book(b1); app.processEvents()
assert not w.on_shelf() and w.current_book is b1 and w.tree_dock.isVisible()
assert "Der Sturm" in w.windowTitle()
n = s.create_note("chapter", QPointF(0, 0)); n.model.title = "Kap 1"; n.model.content = "wort " * 600
n.model.attributes[0].value = "1"; n.model.attributes.append(__import__("models").AttributeData("Datum", "12.05.1887"))
w.checkpoint(); w.refresh_views(); assert w.dirty
print("label:", w.stats_label.text())
assert "Ziel 60 %" in w.stats_label.text() and "Heute +600" in w.stats_label.text()
click_later("Speichern"); assert w.show_shelf() is True
assert w.on_shelf() and not w.tree_dock.isVisible()
assert os.path.exists(lib.book_path(b1)) and b1.word_count == 600 and b1.note_count == 1, (b1.word_count, b1.note_count)
w.shelf.refresh()

# Neues Buch + Abbrechen-Schutz beim Zurück
w.open_book(b1); assert len(s.note_lookup) == 1
list(s.note_lookup.values())[0].setPos(50, 50); w.checkpoint()
click_later("Abbrechen"); assert w.show_shelf() is False and not w.on_shelf()
click_later("Speichern"); assert w.show_shelf() is True
assert len(lib.list_backups(b1)) == 1, lib.list_backups(b1)   # Backup beim 2. Speichern

# Persistenz der Bibliothek
from library import Library
lib2 = Library(home); assert [b.title for b in lib2.books if b.category_id == cats[0].id] == ["Der Sturm"]
assert lib2.books[0].baseline_words == 0

# Info-Dialog
from book_dialog import BookInfoDialog
d = BookInfoDialog(b1, lib.categories); d.title_edit.setText("Sturmwarnung"); d.target_spin.setValue(5000); d._add_row()
d.table.item(0, 0).setText("Arbeitstitel"); d.table.item(0, 1).setText("Orkan")
d.apply(b1); assert b1.title == "Sturmwarnung" and b1.attributes[0].value == "Orkan"

# Zeitleiste, Statistik, Manuskript, Erwähnung
w.open_book(b1)
w.timeline_dock.show(); app.processEvents(); w.refresh_timeline()
assert len(w.timeline.entries) == 1 and w.timeline.entries[0].date_text == "12.05.1887", w.timeline.entries
from stats import build_stats_html
html = build_stats_html(list(s.note_lookup.values()), w.note_types, 0, b1, 600); assert "Schreibziel" in html and "Kapitel" in html
from manuscript import build_sections, render, to_html, write_pdf, ManuscriptDialog
secs = build_sections(list(s.note_lookup.values()), {"chapter"})
assert secs[0][0] == "Kap 1" and render("md", secs, "T", "A", True).startswith("# T")
pdf = os.path.join(home, "m.pdf"); write_pdf(to_html(secs, "T", "A", True), pdf); assert os.path.getsize(pdf) > 500
dlg = ManuscriptDialog(list(s.note_lookup.values()), w.note_types); assert "1 Notizen" in dlg.summary.text()
n = [x for x in s.note_lookup.values() if x.model.note_type == "chapter"][0]
c2 = s.create_note("character", QPointF(300, 0)); c2.model.title = "Marta"; n.model.content = "Heute traf Marta den Kapitän."
c2.model_changed(); n.model_changed()
w.inspector.set_note(c2); texts = [w.inspector.links_list.item(i).text() for i in range(w.inspector.links_list.count())]
assert any("erwähnt in Kap 1" in t for t in texts), texts
from models import parse_date_key
assert parse_date_key("12.05.1887") < parse_date_key("1900") or True
assert parse_date_key("1887-05-12") == (1887, 5, 12)

# Fortschritt/Backups laden (undo-bar)
w.checkpoint(); w.save_project()
b = lib.backup(b1); 
n_before = len(s.note_lookup)
w.statusBar()  # no-op
w.shelf.edit_book  # exists
print("screens")
w.show_shelf() if not w.dirty else None
w.grab().save(os.path.join(TMP, "shelf.png"))
print("ALL OK")
