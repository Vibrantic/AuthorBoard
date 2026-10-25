#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Create the screenshots used by README.md and the docs (docs/images/*.png).

    python tools/make_screenshots.py

Runs headless against a temporary library and the English showcase notebook.

Notes
-----
*   The Qt ``offscreen`` platform plugin does not ship fonts and warns about
    missing ``PySide6/lib/fonts``.  On Windows we point it at the system font
    directory so the rendered text matches what real users see.
*   The offscreen plugin also emits ``propagateSizeHints`` chatter on every
    ``QDialog.show()``.  A small message handler swallows just that line so
    the run's stderr stays readable.
*   Screenshots are written to ``docs/images/`` and correspond to the file
    names used by ``README.md`` and the developer docs.
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

# Windows + offscreen font directory — must come after TMP exists.
if sys.platform == "win32" and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    import shutil
    _fonts_tmp = os.path.join(TMP, "fonts")
    os.makedirs(_fonts_tmp, exist_ok=True)
    for _name in ("segoeui.ttf", "arial.ttf", "tahoma.ttf", "calibri.ttf"):
        _src = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", _name)
        if os.path.isfile(_src):
            try:
                shutil.copy2(_src, os.path.join(_fonts_tmp, _name))
                os.environ["QT_QPA_FONTDIR"] = _fonts_tmp
            except OSError:
                pass
            break

from PySide6.QtCore import QPointF, QSettings, Qt, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

QSettings.setPath(
    QSettings.Format.NativeFormat,
    QSettings.Scope.UserScope,
    os.path.join(TMP, "qs"),
)

import i18n
i18n.set_language("en")
import main as M
from about_dialog import AboutDialog
from editor_dialog import NoteEditorDialog
from help_dialog import HelpDialog
from settings import settings
from settings_dialog import SettingsDialog
from theme import apply_dark_palette

OUT = os.path.join(ROOT, "docs", "images")
os.makedirs(OUT, exist_ok=True)

app = QApplication([])
app.setStyle("Fusion")
apply_dark_palette(app)
settings.data["spell_language"] = "en"


# --------------------------------------------------------------------------
# Quiet the offscreen plugin's "propagateSizeHints" chatter.  It fires every
# time a QDialog is shown and is not a real warning (the offscreen platform
# has no window manager to honour size hints; the widget still renders
# correctly and grab() captures it fine).
# --------------------------------------------------------------------------
def _quiet_qt(typ, ctx, msg):
    if "propagateSizeHints" in msg:
        return
    sys.stderr.write(msg + "\n")


qInstallMessageHandler(_quiet_qt)


def pump(ms=150):
    QTest.qWait(ms)
    app.processEvents()


def shot(widget, name):
    path = os.path.join(OUT, name)
    widget.grab().save(path)
    print("saved", name)


# --------------------------------------------------------------------------
# Build the demo library: the English showcase plus a few fake books so the
# shelf page has something to look at.
# --------------------------------------------------------------------------
w = M.MainWindow()
w.resize(1700, 1000)
w.show()
pump()

src = glob.glob(os.path.join(ROOT, "showcase", "*Ashwood*.json"))[0]
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([src], ""))
w.shelf.import_files()
lib = w.library
for title, cat, color in (
    ("Harbor Lights", 0, "#26a69a"),
    ("Paper Moons", 0, "#ef5350"),
    ("Short Story Drafts", 1, "#5c6bc0"),
    ("Ideas 2027", 2, "#ffa726"),
):
    b = lib.new_book(lib.categories[cat].id)
    b.title, b.color, b.word_count = title, color, 12000 * (1 + cat)
    lib.add_book(b)
lib.set_category_color(lib.categories[1].id, "#4a6fa5")
lib.save()
w.shelf.refresh()
pump(300)
shot(w, "shelf.png")


# --------------------------------------------------------------------------
# Board: open the showcase notebook and fit-all.
# --------------------------------------------------------------------------
book = [b for b in lib.books if "Ashwood" in b.title][0]
w.open_book(book)
pump(400)
w.view.fit_all()
pump()
shot(w, "board.png")


# --------------------------------------------------------------------------
# Focus mode + inspector.
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Comments tab.
# --------------------------------------------------------------------------
w.right_panel.setCurrentIndex(1)
pump()
shot(w.right_panel, "comments.png")
w.right_panel.setCurrentIndex(0)


# --------------------------------------------------------------------------
# Timeline with one information bubble open.
# --------------------------------------------------------------------------
w.view.fit_all()
s.clearSelection()
w.timeline_dock.show()
pump()
w.timeline.resize(1500, 300)
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


# --------------------------------------------------------------------------
# Groups: select the group's members so the group frame is visibly
# highlighted, then frame just the group's bounding rect so the shot shows
# the group in context instead of "board at slightly different pan".
# --------------------------------------------------------------------------
cast = next(g for g in s.group_lookup.values() if g.model.title == "Cast")
s.clearSelection()

# GroupData does not carry a list of member notes — the group/member
# relationship lives elsewhere (either a group id on each NoteData or an
# id set on the group, depending on the exact storage).  To avoid binding
# the screenshot script to that detail, select every note that lies inside
# the group's rectangle: that is exactly what the user perceives as "in
# the group".
group_rect = cast.sceneBoundingRect()
for note_item in s.note_lookup.values():
    if group_rect.contains(note_item.sceneBoundingRect()):
        note_item.setSelected(True)

w.view.fitInView(
    group_rect.adjusted(-40, -40, 40, 40),
    Qt.AspectRatioMode.KeepAspectRatio,
)
pump(300)
shot(w, "groups.png")
w.view.fit_all()


# --------------------------------------------------------------------------
# FlowView (default view, no path selected).
# --------------------------------------------------------------------------
s.clearSelection()
w.open_flow_view(mira)
fv = w._flow_view
assert fv is not None, "FlowView was not created — check open_flow_view()"
fv.resize(1400, 860)
pump(500)
shot(fv, "flowview.png")


# --------------------------------------------------------------------------
# FlowView with a path highlighted to a two-hop note.
# --------------------------------------------------------------------------
spring = next(
    n for n in s.note_lookup.values()
    if n.model.title.startswith("The Ash Spring")
)
fv._on_note_list_selected(id(spring))
pump(400)
shot(fv, "flowview-path.png")

fv.close()
pump()
w.view.fit_all()


# --------------------------------------------------------------------------
# Full-size editor with a comment focused.
# --------------------------------------------------------------------------
ch1 = [
    n for n in s.note_lookup.values()
    if n.model.title.startswith("Chapter 1")
][0]
dlg = NoteEditorDialog(
    ch1.model, w.attachments, w,
    focus_comment=ch1.model.comments[0].id,
)
dlg.resize(1150, 640)
dlg.show()
pump(300)
shot(dlg, "editor.png")
dlg.close()


# --------------------------------------------------------------------------
# Settings dialog.
# --------------------------------------------------------------------------
sd = SettingsDialog(
    w.book_type_list(), settings.global_types(), {}, [], True, w,
)
sd.resize(800, 520)
sd.show()
pump()
shot(sd, "settings.png")
sd.close()


# --------------------------------------------------------------------------
# Help dialog with a search that exists in every language.
# --------------------------------------------------------------------------
hd = HelpDialog(w)
hd.show()
hd.search.setText("FlowView")
pump(300)
shot(hd, "help.png")
hd.close()


# --------------------------------------------------------------------------
# About dialog.
# --------------------------------------------------------------------------
ad = AboutDialog(w)
ad.show()
pump()
shot(ad, "about.png")
ad.close()

print("done ->", OUT)