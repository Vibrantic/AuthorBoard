#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Create the screenshots used by README.md and the docs (docs/images/*.png).

    python tools/make_screenshots.py

Runs headless against a temporary library and the English showcase notebook.
"""
import glob
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="ab-shots-")
os.environ["AUTHORBOARD_HOME"] = os.path.join(TMP, "home")
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPoint, QPointF, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, os.path.join(TMP, "qs"))

import i18n
i18n.set_language("en")
import main as M
from about_dialog import AboutDialog
from editor_dialog import NoteEditorDialog
from help_dialog import HelpDialog
from settings import settings
from settings_dialog import SettingsDialog
from spellcheck import engine
from theme import apply_dark_palette

OUT = os.path.join(ROOT, "docs", "images")
os.makedirs(OUT, exist_ok=True)

app = QApplication([])
app.setStyle("Fusion")
apply_dark_palette(app)
settings.data["spell_language"] = "en"


def pump(ms=150):
    QTest.qWait(ms)
    app.processEvents()


def shot(widget, name):
    widget.grab().save(os.path.join(OUT, name))
    print("saved", name)


w = M.MainWindow()
w.resize(1700, 1000)
w.show()
pump()

# ---------------------------------------------------------------- library
src = glob.glob(os.path.join(ROOT, "showcase", "*Ashwood*.json"))[0]
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([src], ""))
w.shelf.import_files()
lib = w.library
for title, cat, color in (("Harbor Lights", 0, "#26a69a"), ("Paper Moons", 0, "#ef5350"),
                          ("Short Story Drafts", 1, "#5c6bc0"), ("Ideas 2027", 2, "#ffa726")):
    b = lib.new_book(lib.categories[cat].id)
    b.title, b.color, b.word_count = title, color, 12000 * (1 + cat)
    lib.add_book(b)
lib.set_category_color(lib.categories[1].id, "#4a6fa5")
lib.save()
w.shelf.refresh()
pump(300)
shot(w, "shelf.png")

# ------------------------------------------------------------------ board
book = [b for b in lib.books if "Ashwood" in b.title][0]
w.open_book(book)
pump(400)
w.view.fit_all()
pump()
shot(w, "board.png")

# ------------------------------------------------- focus mode + inspector
s = w.scene
mira = [n for n in s.note_lookup.values() if n.model.title.startswith("Mira")][0]
s.clearSelection()
mira.setSelected(True)
w.view.resetTransform()
w.view.scale(0.75, 0.75)
w.view.centerOn(mira.sceneBoundingRect().center() + QPointF(380, 80))
pump(300)
shot(w, "focus-mode.png")
w.right_panel.setCurrentIndex(0)
pump()
shot(w.right_panel, "inspector.png")

# ---------------------------------------------------------------- comments
w.right_panel.setCurrentIndex(1)
pump()
shot(w.right_panel, "comments.png")
w.right_panel.setCurrentIndex(0)

# ------------------------------------------------------ timeline + bubble
w.view.fit_all()
s.clearSelection()
w.timeline_dock.show()
pump()
w.timeline.resize(1400, 260)
w.timeline.fit()
tl = w.timeline
entry = [e for e in tl.entries if "Spring" in e.title or "Fire" in e.title][0]
tl.view_min = entry.x - 600
tl.ppd = 0.9
tl.active = entry
tl.always.add(entry.note.model.id)
tl.update()
pump()
shot(tl, "timeline.png")
w.timeline_dock.hide()

# ------------------------------------------------------------------ editor
ch1 = [n for n in s.note_lookup.values() if n.model.title.startswith("Chapter 1")][0]
dlg = NoteEditorDialog(ch1.model, w.attachments, w, focus_comment=ch1.model.comments[0].id)
dlg.resize(1150, 640)
dlg.show()
pump(300)
shot(dlg, "editor.png")
dlg.close()

# --------------------------------------------------- settings / help / about
sd = SettingsDialog(w.book_type_list(), settings.global_types(), {}, [], True, w)
sd.resize(800, 520)
sd.show()
pump()
shot(sd, "settings.png")
sd.close()

hd = HelpDialog(w)
hd.show()
hd.search.setText("comment")
pump(300)
shot(hd, "help.png")
hd.close()

ad = AboutDialog(w)
ad.show()
pump()
shot(ad, "about.png")
ad.close()
print("done ->", OUT)
