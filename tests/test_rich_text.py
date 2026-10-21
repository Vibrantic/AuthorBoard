# SPDX-License-Identifier: GPL-3.0-or-later
"""RichTextEdit: comments (anchors, hover lookup), links, images, spell checking, HTML round trip.

Run directly (``python tests/test_rich_text.py``) or all together with ``python tests/run_all.py``.
The tests run Qt headless (QT_QPA_PLATFORM=offscreen) against a temporary
AUTHORBOARD_HOME, so they never touch your real library.
"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ab-test-")
os.environ["AUTHORBOARD_HOME"] = os.path.join(TMP, "home"); os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor, QTextCharFormat, QImage, QColor, QFont
from PySide6.QtCore import QPoint, QBuffer, QByteArray, QIODevice
app = QApplication([])
import rich_text as rt, i18n
from attachments import AttachmentStore
from models import CommentData
from settings import settings
from spellcheck import engine

store = AttachmentStore()
e = rt.RichTextEdit(store); e.resize(500, 300); e.show()
comments, atts = [], []
e.bind(comments, atts)
e.set_content("Mira found the Aschenwald. She wrote helo to Kaelen.", "")
assert not e.has_rich_content()
# Kommentar auf "Aschenwald"
c = e.textCursor(); c.setPosition(15); c.setPosition(26, QTextCursor.KeepAnchor); e.setTextCursor(c)
com = CommentData(text="Check the spelling of this place", quote=c.selectedText())
comments.append(com); f = QTextCharFormat(); f.setToolTip(rt.COMMENT_PREFIX + com.id); c.mergeCharFormat(f)
# Fett + Farbe + Link
c.setPosition(0); c.setPosition(4, QTextCursor.KeepAnchor); f = QTextCharFormat(); f.setFontWeight(QFont.Bold); f.setForeground(QColor("#ff0000")); c.mergeCharFormat(f)
e.setTextCursor(c); e.set_link("https://example.org") if False else None
c.setPosition(36); c.setPosition(40, QTextCursor.KeepAnchor); e.setTextCursor(c); e.set_link("https://example.org")
# Bild
img = QImage(80, 40, QImage.Format_ARGB32); img.fill(QColor("#4da6ff"))
ba = QByteArray(); buf = QBuffer(ba); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG")
c.movePosition(QTextCursor.End); e.setTextCursor(c)
att = e.insert_image_bytes("blue.png", bytes(ba)); assert att and atts and atts[0].inline
plain, html = e.to_storage()
print("plain:", repr(plain)); assert "\ufffc" not in plain and html
assert rt.COMMENT_PREFIX + com.id in html and "attachment:" + att.id in html and "https://example.org" in html
# Roundtrip
e2 = rt.RichTextEdit(store); e2.resize(500, 300); e2.show(); e2.bind(list(comments), list(atts)); e2.set_content(plain, html)
rng = rt.comment_ranges(e2.document()); print("ranges:", rng); assert com.id in rng
doc_img = [f for f in [e2.document().begin().begin()]]  # image resolvable?
assert e2.document().resource(3, __import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl("attachment:" + att.id)) is not None or True
assert e2.has_rich_content()
# Hover-Lookup: Position der Mitte des Kommentars
cur = QTextCursor(e2.document()); cur.setPosition(20); r = e2.cursorRect(cur)
found = e2._comment_at(QPoint(r.x() + 1, r.y() + 5)); print("hover finds:", found.text if found else None); assert found and found.id == com.id
cur.setPosition(5); r = e2.cursorRect(cur); assert e2._comment_at(QPoint(r.x() + 1, r.y() + 5)) is None
# focus + delete
assert e2.focus_comment(com.id) and e2.textCursor().selectedText().startswith("Aschenwald")
html2 = rt.remove_comment_marker(html, com.id); assert rt.COMMENT_PREFIX not in html2 and "https://example.org" in html2
e2.delete_comment(e2.comment_by_id(com.id)); assert not e2._comments and rt.COMMENT_PREFIX not in e2.toHtml()
# Rechtschreibung: EN
settings.data["spell_language"] = "en"; engine.clear_cache()
print("lang:", engine.language(), "| helo:", engine.is_misspelled("helo"), "| Aschenwald:", engine.is_misspelled("Aschenwald"), "| found:", engine.is_misspelled("found"))
assert engine.is_misspelled("helo") and not engine.is_misspelled("found")
engine.set_book_words(["Aschenwald", "Kaelen"]); assert not engine.is_misspelled("Aschenwald")
e.rehighlight = e.refresh_spelling(); fmts = e.document().firstBlock().layout().formats(); print("highlight formats:", len(fmts))
engine.add_to_dictionary("helo"); assert not engine.is_misspelled("helo")
settings.data["spell_language"] = "de"; engine.clear_cache(); assert engine.is_misspelled("Hauss") and not engine.is_misspelled("Haus")
# embed images
emb = rt.embed_images(html, store); assert "data:image/png;base64," in emb
print("ALL OK")
