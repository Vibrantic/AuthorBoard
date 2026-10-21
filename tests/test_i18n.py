# SPDX-License-Identifier: GPL-3.0-or-later
"""English interface, translated type/attribute names and live language switching.

Run directly (``python tests/test_i18n.py``) or all together with ``python tests/run_all.py``.
The tests run Qt headless (QT_QPA_PLATFORM=offscreen) against a temporary
AUTHORBOARD_HOME, so they never touch your real library.
"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ab-test-")
home = os.path.join(TMP, "home"); os.makedirs(home); os.environ["AUTHORBOARD_HOME"] = home; os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, QSettings
QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, os.path.join(TMP, 'qsettings'))
QSettings("AuthorBoard", "AuthorBoard").remove("language")
import i18n, main as M
from main import MainWindow
from theme import apply_dark_palette
from models import attribute_value

app = QApplication([]); app.setStyle("Fusion"); apply_dark_palette(app)
i18n.set_language("en")
assert i18n.tr("Speichern") == "Save" and i18n.tr("{n} Bücher", n=3) == "3 books"
w = MainWindow(); w.resize(1400, 900); w.show(); app.processEvents()
M._windows.append(w)
print("menus:", [a.text() for a in w.menuBar().actions()])
assert [a.text() for a in w.menuBar().actions()] == ["File", "Edit", "View", "Help"]
assert w.lang_menu.title() == "Language" and set(w._lang_actions) == {"de", "en"}
assert "Novels" in [c.name for c in w.library.categories]
b = w.library.new_book(); assert b.title == "New notebook"; w.library.add_book(b); w.open_book(b)
n = w.scene.create_note("character", QPointF(0, 0))
print("type:", n.type_info().label, "| attrs:", [a.name for a in n.model.attributes])
assert n.type_info().label == "Character" and n.model.attributes[0].name == "Age"
# Datum auf Englisch erkennen
n2 = w.scene.create_note("event", QPointF(300, 0)); n2.model.attributes[0].value = "12.05.1887"
assert n2.model.attributes[0].name == "Date" and attribute_value(n2.model, "Datum") == "12.05.1887"
w.timeline_dock.show(); w.refresh_timeline(); assert len(w.timeline.entries) == 1
print("tooltip:", n.tooltip_text().replace("<br>", " | ")[:100])
print("status:", w.statusBar().currentMessage()[:50], "|", w.stats_label.text())
w.checkpoint()
# Live-Wechsel nach Deutsch (mit ungespeicherten Änderungen -> Dialog)
from PySide6.QtCore import QTimer
def click(text):
    def f():
        box = QApplication.activeModalWidget()
        for bt in box.buttons():
            if bt.text() == text: bt.click()
    QTimer.singleShot(150, f)
assert w.dirty
click("Save"); w.switch_language("de"); app.processEvents()
assert i18n.current_language() == "de"
new = M._windows[-1]; assert new is not w and not new.on_shelf() and new.current_book.id == b.id
assert len(new.scene.note_lookup) == 2
assert [a.text() for a in new.menuBar().actions()] == ["Datei", "Bearbeiten", "Ansicht", "Hilfe"]
assert QSettings("AuthorBoard", "AuthorBoard").value("language") == "de"
print("after switch:", new.windowTitle(), "| types:", sorted({n.type_info().label for n in new.scene.note_lookup.values()}))
QSettings("AuthorBoard", "AuthorBoard").remove("language")
print("ALL OK")
