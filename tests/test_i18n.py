# SPDX-License-Identifier: GPL-3.0-or-later
"""English interface, translated type/attribute names and the language switch.

Run directly (``python tests/test_i18n.py``) or all together with ``python tests/run_all.py``.
The tests run Qt headless (QT_QPA_PLATFORM=offscreen) against a temporary
AUTHORBOARD_HOME, so they never touch your real library.
"""
import atexit
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

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, QSettings, QTimer

import i18n
import main as M
from main import MainWindow
from theme import apply_dark_palette
from models import attribute_value

# QSettings lives in the registry on Windows: use an own key so the test never
# touches the real "AuthorBoard" settings.  Do this *before* constructing the
# MainWindow — MainWindow reads QSettings("AuthorBoard", "AuthorBoard") for
# "reopen_book" and "language" during __init__.
M.SETTINGS_ORG = M.SETTINGS_APP = "AuthorBoardTest"


def _test_q():
    return QSettings("AuthorBoardTest", "AuthorBoardTest")


_test_q().clear()
atexit.register(lambda: _test_q().clear())

app = QApplication([])
app.setStyle("Fusion")
apply_dark_palette(app)

i18n.set_language("en")
assert i18n.tr("Speichern") == "Save" and i18n.tr("{n} Bücher", n=3) == "3 books"

w = MainWindow()
w.resize(1400, 900)
w.show()
app.processEvents()
M._windows.append(w)

print("menus:", [a.text() for a in w.menuBar().actions()])
assert [a.text() for a in w.menuBar().actions()] == ["File", "Edit", "View", "Help"]
assert w.lang_menu.title() == "Language" and set(w._lang_actions) == {"de", "en"}
assert "Novels" in [c.name for c in w.library.categories]

b = w.library.new_book()
assert b.title == "New notebook"
w.library.add_book(b)
w.open_book(b)

n = w.scene.create_note("character", QPointF(0, 0))
print("type:", n.type_info().label, "| attrs:", [a.name for a in n.model.attributes])
assert n.type_info().label == "Character" and n.model.attributes[0].name == "Age"

# Datum auf Englisch erkennen
n2 = w.scene.create_note("event", QPointF(300, 0))
n2.model.attributes[0].value = "12.05.1887"
assert n2.model.attributes[0].name == "Date"
assert attribute_value(n2.model, "Datum") == "12.05.1887"

w.timeline_dock.show()
w.refresh_timeline()
assert len(w.timeline.entries) == 1

print("tooltip:", n.tooltip_text().replace("<br>", " | ")[:100])
print("status:", w.statusBar().currentMessage()[:50], "|", w.stats_label.text())
w.checkpoint()


# --------------------------------------------------------------------------
# Language switch: the app restarts itself in a NEW PROCESS.  Never launch
# it for real in a test (the child would run this script again), so replace
# QProcess in main.py by a recorder.
#
# PySide6's QProcess.startDetached returns a plain ``bool`` (the PyQt5
# overload that returned (bool, pid) does not exist here).  The fake below
# mirrors that signature: it returns True on the success path.
# --------------------------------------------------------------------------
launched = []


class _FakeProcess:
    @staticmethod
    def startDetached(*args, **kwargs):
        launched.append(args)
        return True


M.QProcess = _FakeProcess


def click(text):
    """Click the first button of the currently active modal box that has ``text``."""
    def _do():
        box = QApplication.activeModalWidget()
        if box is None:
            return
        for bt in box.buttons():
            if bt.text() == text:
                bt.click()
                return
    QTimer.singleShot(150, _do)


# The board is dirty (we created two notes since the last checkpoint push).
assert w.dirty

# switch_language() → maybe_save() → modal "save?" → answer "Save".
# After that, startDetached() is called, which our fake records and returns
# True from, so switch_language closes the window via self.close().
click("Save")
w.switch_language("de")
app.processEvents()

assert len(launched) == 1, launched
assert w._closing_for_switch

q = _test_q()
assert q.value("language") == "de"
assert q.value("reopen_book") == b.id

print("switch ok; restart requested:", launched[0][0])


# --------------------------------------------------------------------------
# Failure path: startDetached returns False → the window must stay open,
# _closing_for_switch must stay False, and a warning box must be shown.
# --------------------------------------------------------------------------
class _FailingProcess:
    @staticmethod
    def startDetached(*args, **kwargs):
        launched.append(args)
        return False


M.QProcess = _FailingProcess

# A fresh window for the failure path (the previous one was closed).
_test_q().clear()
w2 = MainWindow()
w2.resize(1200, 800)
w2.show()
app.processEvents()
M._windows.append(w2)

# Create a note so the board is dirty and switch_language() would prompt to save.
n3 = w2.scene.create_note("note", QPointF(0, 0))
w2.checkpoint()
n3.setPos(10, 10)
w2.checkpoint()
assert w2.dirty


def dismiss_warning():
    """Close the warning dialog that switch_language() shows on failure."""
    box = QApplication.activeModalWidget()
    if box is not None:
        box.accept()


# save prompt (answer Save), then the failure warning (dismiss it).
QTimer.singleShot(150, lambda: click("Save")())
QTimer.singleShot(350, dismiss_warning)

w2.switch_language("de")
app.processEvents()

assert len(launched) == 2, launched
assert not w2._closing_for_switch, "_closing_for_switch must stay False on failure"
assert w2.isVisible(), "window must stay open when startDetached fails"
assert _test_q().value("language") == "de"

w2.close()
print("failure path ok")

print("ALL OK")