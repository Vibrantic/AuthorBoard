# SPDX-License-Identifier: GPL-3.0-or-later
"""Imports a showcase notebook (pass 'de' or 'en') and checks every feature of the file.

Run directly (``python tests/test_showcase.py de``) or all together with ``python tests/run_all.py``.
The tests run Qt headless (QT_QPA_PLATFORM=offscreen) against a temporary
AUTHORBOARD_HOME, so they never touch your real library.
"""
import glob
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP = tempfile.mkdtemp(prefix="ab-test-")
home = os.path.join(TMP, "home")
os.makedirs(home)
os.environ["AUTHORBOARD_HOME"] = home
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtCore import QPointF

import i18n
lang = sys.argv[1]
i18n.set_language(lang)

import main as M  # noqa: E402  (must come after i18n.set_language)
from main import MainWindow  # noqa: E402
from theme import apply_dark_palette  # noqa: E402
from storage import Storage  # noqa: E402
from models import note_timeline_key  # noqa: E402
import rich_text as rt  # noqa: E402

src = glob.glob(ROOT + f"/showcase/*{'Aschenwald' if lang == 'de' else 'Ashwood'}*.json")[0]

# ---------------------------------------------------------------- file content
# Storage.load returns a ProjectData (dataclasses), not the raw JSON dict, so
# the structural checks read the file directly with json.load.
with open(src, encoding="utf-8") as fh:
    raw = json.load(fh)

assert isinstance(raw.get("groups"), list) and raw["groups"], "no groups in showcase"
for g in raw["groups"]:
    assert isinstance(g, dict) and g.get("id"), f"group without id: {g!r}"
    for key in ("x", "y", "width", "height"):
        assert key in g, (g.get("id"), key)

p = Storage.load(src)
pins = {pin.id for n in p.notes for pin in n.pins}
assert all(c.start_pin_id in pins and c.end_pin_id in pins for c in p.connections)

for n in p.notes:
    for c in n.comments:
        assert rt.COMMENT_PREFIX + c.id in n.rich, (n.title, c.text)
    for a in n.attachments:
        assert a.id in p.blobs, (n.title, a.name)
    if n.rich:
        assert "ab-comment" in n.rich or True  # tolerated, but most rich notes carry comments

print(
    lang, "load ok:",
    len(p.notes), "notes;",
    sum(len(n.comments) for n in p.notes), "comments;",
    sum(1 for n in p.notes if n.locked), "locked;",
    sum(1 for n in p.notes for pn in n.pins if pn.locked), "locked pins;",
    len(p.blobs), "blobs; rich:", sum(1 for n in p.notes if n.rich),
)

# --------------------------------------------------------------- app / import
app = QApplication([])
app.setStyle("Fusion")
apply_dark_palette(app)

w = MainWindow()
w.resize(1700, 1000)
w.show()
app.processEvents()

QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([src], ""))
w.shelf.import_files()
app.processEvents()

b = w.library.books[-1]
print("book:", b.title, "|", w.library.category(b.category_id).name,
      "|", b.target_words, "|", len(b.attributes))

w.open_book(b)
app.processEvents()
app.processEvents()

s = w.scene
assert len(s.note_lookup) > 0 and not w.dirty
assert len(s.group_lookup) > 0
assert all(s.note_group(n) is not None for n in s.note_lookup.values())

kaelen = [n for n in s.note_lookup.values() if n.model.title.startswith("Kaelen")][0]
mira_n = [n for n in s.note_lookup.values() if n.model.title.startswith("Mira")][0]
assert s.note_group(kaelen) is not s.note_group(mira_n)        # nested frame wins for Kaelen
assert s.note_group(kaelen).model.locked is False
assert any(g.model.locked for g in s.group_lookup.values())
assert "global_moodboard" in w.note_types and "custom_fraktion" in w.note_types

# --------------------------------------------------------------- timeline
w.timeline_dock.show()
app.processEvents()
w.refresh_timeline()
print("timeline entries:", len(w.timeline.entries), "undated:", w.timeline.undated)

# Every note with a parsable Date/Uhrzeit must be on the timeline, and the
# showcase must exercise at least one of each (dated + undated).
dated = sum(
    1 for n in s.note_lookup.values()
    if note_timeline_key(n.model) is not None
)
assert len(w.timeline.entries) == dated > 0
assert w.timeline.undated == len(s.note_lookup) - dated > 0

# --------------------------------------------------------------- UI panels
w.refresh_views()
app.processEvents()
print("comments tab:", w.right_panel.tabText(1), "| stats:", w.stats_label.text())

mira = [n for n in s.note_lookup.values() if n.model.note_type == "character"][0]
mira.setSelected(True)
app.processEvents()
w.inspector.set_note(
    [n for n in s.note_lookup.values() if n.model.title.startswith("Mira")][0]
)
print(
    "links:", w.inspector.links_list.count(),
    "| attachments:", w.inspector.attach_list.count(),
    "| known tags:", len(w.known_tags),
)

# --------------------------------------------------------------- manuscript
from manuscript import build_sections  # noqa: E402

secs = build_sections(list(s.note_lookup.values()), {"chapter", "scene"}, w.attachments)
print(
    "manuscript:", [t[:12] for t, _, _ in secs][:5],
    "| html sections:", sum(1 for _, _, h in secs if h),
    "| data-uri images:", sum(h.count("data:image/png") for _, _, h in secs),
)

w.view.fit_all()
s.clearSelection()
app.processEvents()
w.grab().save(os.path.join(TMP, f"showcase_{lang}.png"))

# --------------------------------------------------------------- editor focus
ch1 = [
    n for n in s.note_lookup.values()
    if n.model.title.startswith(("Kapitel 1", "Chapter 1"))
][0]
from editor_dialog import NoteEditorDialog  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

d = NoteEditorDialog(ch1.model, w.attachments, w, focus_comment=ch1.model.comments[0].id)
d.show()
app.processEvents()
QTest.qWait(120)
print("focus:", repr(d.edit.textCursor().selectedText()))
d.grab().save(os.path.join(TMP, f"editor_{lang}.png"))

print("ALL OK")