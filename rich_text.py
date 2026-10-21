# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Rich-text editing widget used by the Inspector and the full-size editor.

What this module provides
-------------------------
* :class:`RichTextEdit` - a ``QTextEdit`` with
    - inline images that are stored as note attachments (``attachment:<id>``),
    - clickable links (Ctrl+click opens them in the web browser),
    - spell checking (red squiggles, suggestions in the context menu),
    - *comments* on words/sentences with a hover pop-up.
* helper functions to analyse / clean rich-text documents.

How comments are anchored
-------------------------
A comment is attached to a text range by giving that range a character-format
**tool tip** of the form ``ab-comment:<comment id>``.  Qt writes this tool tip
as a ``title`` attribute into the HTML and reads it back, so the range survives
saving/loading *and* coexists with links, colours and fonts.  The comment text
itself is kept in :class:`models.CommentData` (``note.comments``).
"""

import base64
import re
from datetime import datetime

from PySide6.QtCore import QBuffer, QByteArray, QEvent, QIODevice, QPoint, QUrl, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QImage,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import QInputDialog, QTextEdit, QToolTip

from i18n import tr
from models import AttachmentData, CommentData
from spellcheck import WORD_RE, engine

COMMENT_PREFIX = "ab-comment:"
MAX_IMAGE_WIDTH = 520          # inserted images are scaled down to this width
SAFE_SCHEMES = ("http", "https", "mailto", "ftp")


# --------------------------------------------------------------------------
# Document helpers
# --------------------------------------------------------------------------

def comment_id_of(fmt):
    """Return the comment id stored in a character format (or None)."""
    tip = fmt.toolTip()
    if tip and tip.startswith(COMMENT_PREFIX):
        return tip[len(COMMENT_PREFIX):]
    return None


def comment_ranges(doc):
    """Map comment id -> list of (start, end) document positions."""
    ranges = {}
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            cid = comment_id_of(frag.charFormat()) if frag.isValid() else None
            if cid:
                start = frag.position()
                ranges.setdefault(cid, []).append((start, start + frag.length()))
            it += 1
        block = block.next()
    return ranges


def has_rich_content(doc):
    """True when the document contains anything beyond plain text.

    Used to decide whether a note needs to store HTML at all: plain notes keep
    ``rich == ""`` so they stay small and diff-friendly."""
    P = QTextFormat.Property
    block = doc.begin()
    while block.isValid():
        if block.textList() is not None:
            return True
        if block.blockFormat().alignment() not in (
                Qt.AlignmentFlag.AlignLeft,
                Qt.AlignmentFlag.AlignLeading | Qt.AlignmentFlag.AlignLeft,
                Qt.AlignmentFlag.AlignLeading):
            return True
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            f = frag.charFormat() if frag.isValid() else None
            if f is not None and (
                f.isAnchor() or f.isImageFormat() or comment_id_of(f)
                or f.fontWeight() > 450 or f.fontItalic() or f.fontUnderline()
                or f.fontStrikeOut()
                or f.hasProperty(P.ForegroundBrush) or f.hasProperty(P.BackgroundBrush)
                or f.hasProperty(P.FontFamilies) or f.hasProperty(P.FontFamily)
                or f.hasProperty(P.FontPointSize)
            ):
                return True
            it += 1
        block = block.next()
    return False


def _clear_marker(doc, cid):
    """Remove the comment marker ``cid`` from every fragment of ``doc``."""
    for start, end in comment_ranges(doc).get(cid, []):
        c = QTextCursor(doc)
        c.setPosition(start)
        c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat(c.charFormat())
        fmt.clearProperty(QTextFormat.Property.TextToolTip)
        c.setCharFormat(fmt)


def remove_comment_marker(html, cid):
    """Return ``html`` without the marker of comment ``cid``.

    Used when a comment is deleted from the comments panel while the note is
    not open in an editor."""
    doc = QTextDocument()
    doc.setHtml(html)
    _clear_marker(doc, cid)
    return doc.toHtml()


def html_body(html):
    """The inner part of the ``<body>`` element of a Qt-generated HTML page."""
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    return m.group(1) if m else html


def embed_images(html, store):
    """Replace ``attachment:<id>`` image sources by data URIs (for export)."""
    def repl(m):
        data = store.get(m.group(1))
        if not data:
            return m.group(0)
        img = store.image(m.group(1))
        mime = "image/png"
        return f"data:{mime};base64," + base64.b64encode(_png_bytes(img) if img else data).decode()
    return re.sub(r"attachment:([0-9A-Za-z\-]+)", repl, html)


def _png_bytes(image):
    """Encode a QImage as PNG bytes."""
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    return bytes(ba)


# --------------------------------------------------------------------------
# Syntax highlighter: spelling + comment marks (display only, not stored)
# --------------------------------------------------------------------------

class DocHighlighter(QSyntaxHighlighter):
    """Draws red squiggles under misspelled words and an amber mark over
    commented ranges.  These are *overlay* formats - they never end up in the
    saved HTML."""

    def __init__(self, document):
        """Create the overlay formats for spelling and comment marks."""
        super().__init__(document)

        self._spell = QTextCharFormat()
        self._spell.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        self._spell.setUnderlineColor(QColor("#ff5c5c"))

        self._comment = QTextCharFormat()
        self._comment.setBackground(QColor(255, 193, 7, 55))
        self._comment.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DashUnderline)
        self._comment.setUnderlineColor(QColor("#ffb300"))

    def highlightBlock(self, text):
        # 1) comment marks: look at the character formats of the block's fragments
        """Qt: format one text block (comment marks, then spelling)."""
        block = self.currentBlock()
        base = block.position()
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and comment_id_of(frag.charFormat()):
                self.setFormat(frag.position() - base, frag.length(), self._comment)
            it += 1

        # 2) spelling
        if engine.language() is None:
            return
        for m in WORD_RE.finditer(text):
            if engine.is_misspelled(m.group()):
                self.setFormat(m.start(), m.end() - m.start(), self._spell)


# --------------------------------------------------------------------------
# The widget
# --------------------------------------------------------------------------

class RichTextEdit(QTextEdit):
    """QTextEdit with images, links, spell check and comments.

    Typical use::

        edit = RichTextEdit(store)
        edit.bind(comments=note.comments, attachments=note.attachments)
        edit.set_content(note.content, note.rich)
        ...
        plain, html = edit.to_storage()
    """

    comments_changed = Signal()     # a comment was added / edited / deleted

    def __init__(self, store=None, parent=None):
        """Create the editor; ``store`` provides image attachments."""
        super().__init__(parent)
        self.store = store                  # AttachmentStore (for images)
        self._comments = []                 # list[CommentData], shared with the owner
        self._attachments = []              # list[AttachmentData], shared with the owner
        self.highlighter = DocHighlighter(self.document())
        self.setAcceptRichText(True)
        self.viewport().setMouseTracking(True)

    # ------------------------------------------------------------- binding

    def bind(self, comments, attachments):
        """Tell the editor which lists to update when comments / images change.

        The lists are *shared* with the data model (or with the editor dialog's
        working copy), so changes are visible to the owner immediately."""
        self._comments = comments
        self._attachments = attachments

    def set_content(self, plain, html):
        """Load a note: HTML when present, otherwise plain text."""
        if html:
            self.setHtml(html)
        else:
            self.setPlainText(plain)
        self.document().clearUndoRedoStacks()
        self.document().setModified(False)

    def to_storage(self):
        """Return ``(plain_text, html_or_empty)`` ready to store in the model."""
        plain = self.toPlainText().replace("\ufffc", "")      # drop image placeholders
        rich = self.toHtml() if self.has_rich_content() else ""
        return plain, rich

    def has_rich_content(self):
        """True when the document has any formatting."""
        return has_rich_content(self.document())

    def refresh_spelling(self):
        """Re-run the spell checker (after a language / dictionary change)."""
        self.highlighter.rehighlight()

    # --------------------------------------------------------------- images

    def loadResource(self, rtype, url):
        """Qt asks us for resources; ``attachment:<id>`` images come from the store."""
        if url.scheme() == "attachment" and self.store is not None:
            img = self.store.image(url.path() or url.toString().split(":", 1)[1])
            if img is not None:
                return img
        return super().loadResource(rtype, url)

    def insert_image_bytes(self, name, data):
        """Store ``data`` as attachment and insert it at the cursor."""
        if self.store is None:
            return None
        att = self.store.add_bytes(name, data, inline=True)
        self._attachments.append(att)
        self.insert_attachment_image(att)
        return att

    def insert_attachment_image(self, att):
        """Insert an already stored image attachment at the cursor."""
        img = self.store.image(att.id) if self.store else None
        if img is None:
            return
        fmt = self._image_format(att, img)
        self.document().addResource(
            QTextDocument.ResourceType.ImageResource, QUrl(fmt.name()), img)
        self.textCursor().insertImage(fmt)

    @staticmethod
    def _image_format(att, img):
        """QTextImageFormat for an attachment image, scaled to MAX_IMAGE_WIDTH."""
        from PySide6.QtGui import QTextImageFormat
        fmt = QTextImageFormat()
        fmt.setName("attachment:" + att.id)
        w = min(img.width(), MAX_IMAGE_WIDTH)
        fmt.setWidth(w)
        fmt.setHeight(img.height() * w / max(img.width(), 1))
        return fmt

    def canInsertFromMimeData(self, source):
        """Qt: accept dropped / pasted images and files."""
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        """Paste / drop: images become attachments, everything else is default."""
        if self.store is not None:
            if source.hasImage():
                img = source.imageData()
                if isinstance(img, QImage) and not img.isNull():
                    self.insert_image_bytes("pasted.png", _png_bytes(img))
                    return
            if source.hasUrls():
                handled = False
                for url in source.urls():
                    if url.isLocalFile() and url.toLocalFile().lower().endswith(
                            (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
                        with open(url.toLocalFile(), "rb") as f:
                            name = url.toLocalFile().replace("\\", "/").split("/")[-1]
                            self.insert_image_bytes(name, f.read())
                        handled = True
                if handled:
                    return
        super().insertFromMimeData(source)

    # ---------------------------------------------------------------- links

    def mouseReleaseEvent(self, event):
        """Ctrl+click on a link opens it in the web browser."""
        if (event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            href = self.anchorAt(event.pos())
            if href:
                self.open_link(href)
                return
        super().mouseReleaseEvent(event)

    @staticmethod
    def open_link(href):
        """Open ``href`` externally - only harmless URL schemes are allowed."""
        url = QUrl(href)
        if url.scheme().lower() in SAFE_SCHEMES:
            QDesktopServices.openUrl(url)

    def set_link(self, url):
        """Turn the selection (or the URL itself) into a hyperlink."""
        cursor = self.textCursor()
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setFontUnderline(True)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            cursor.insertText(url, fmt)

    # -------------------------------------------------------------- comments

    def comment_by_id(self, cid):
        """CommentData for an id (None if unknown)."""
        return next((c for c in self._comments if c.id == cid), None)

    def _comment_at(self, pos):
        """The comment under a viewport position, or None."""
        cursor = self.cursorForPosition(pos)
        rect = self.cursorRect(cursor)
        if not (rect.top() - 4 <= pos.y() <= rect.bottom() + 4) or abs(rect.x() - pos.x()) > 14:
            return None
        for offset in (0, 1):               # char before / char after the cursor
            c = QTextCursor(self.document())
            c.setPosition(min(cursor.position() + offset, self.document().characterCount() - 1))
            cid = comment_id_of(c.charFormat())
            if cid:
                return self.comment_by_id(cid)
        return None

    def add_comment_dialog(self):
        """Ask for a comment text and attach it to the current selection."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        quote = cursor.selectedText().replace("\u2029", " ")
        if not quote.strip():
            return None
        text, ok = QInputDialog.getMultiLineText(
            self, tr("Kommentar"), tr("Kommentar zu „{quote}“:", quote=quote[:60]), "")
        if not ok or not text.strip():
            return None

        comment = CommentData(text=text.strip(), quote=quote[:200],
                              created=datetime.now().isoformat(timespec="minutes"))
        self._comments.append(comment)

        fmt = QTextCharFormat()
        fmt.setToolTip(COMMENT_PREFIX + comment.id)
        cursor.mergeCharFormat(fmt)
        self.comments_changed.emit()
        return comment

    def edit_comment_dialog(self, comment):
        """Change the text of an existing comment."""
        text, ok = QInputDialog.getMultiLineText(
            self, tr("Kommentar"), tr("Kommentar zu „{quote}“:", quote=comment.quote[:60]),
            comment.text)
        if ok and text.strip():
            comment.text = text.strip()
            self.comments_changed.emit()

    def delete_comment(self, comment):
        """Remove a comment and its marker in the text."""
        _clear_marker(self.document(), comment.id)
        if comment in self._comments:
            self._comments.remove(comment)
        self.highlighter.rehighlight()
        self.comments_changed.emit()

    def prune_comments(self):
        """Drop comments whose text range was deleted by the user."""
        alive = set(comment_ranges(self.document()))
        self._comments[:] = [c for c in self._comments if c.id in alive]

    def focus_comment(self, cid):
        """Select and scroll to the commented text (used by the comments panel)."""
        ranges = comment_ranges(self.document()).get(cid)
        if not ranges:
            return False
        start, end = ranges[0][0], ranges[-1][1]
        c = QTextCursor(self.document())
        c.setPosition(start)
        c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(c)
        self.ensureCursorVisible()
        self.setFocus()
        return True

    # -------------------------------------------------------- tooltips / menu

    def viewportEvent(self, event):
        """Show the comment (or link hint) as a pop-up while hovering."""
        if event.type() == QEvent.Type.ToolTip:
            pos = event.pos()
            comment = self._comment_at(pos)
            if comment is not None:
                when = comment.created.replace("T", " ")
                QToolTip.showText(
                    event.globalPos(),
                    "<b>" + tr("Kommentar") + "</b>"
                    + (f" <small>· {when}</small>" if when else "")
                    + "<br>" + comment.text.replace("\n", "<br>"),
                    self)
                return True
            href = self.anchorAt(pos)
            if href:
                QToolTip.showText(event.globalPos(),
                                  href + "<br><i>" + tr("Strg+Klick öffnet den Link") + "</i>",
                                  self)
                return True
            QToolTip.hideText()
        return super().viewportEvent(event)

    def contextMenuEvent(self, event):
        """Standard menu + spelling suggestions + comment and link actions."""
        pos = event.pos()
        sel = self.textCursor()
        clicked = self.cursorForPosition(pos)

        # Right-click outside the selection: select the word under the pointer
        inside = sel.hasSelection() and sel.selectionStart() <= clicked.position() <= sel.selectionEnd()
        if not inside:
            clicked.select(QTextCursor.SelectionType.WordUnderCursor)
            self.setTextCursor(clicked)
        cursor = self.textCursor()

        menu = self.createStandardContextMenu(event.pos())
        first = menu.actions()[0] if menu.actions() else None

        extra = []

        # --- spelling -----------------------------------------------------
        word = cursor.selectedText() if not inside else ""
        if word and WORD_RE.fullmatch(word) and engine.is_misspelled(word):
            for s in engine.suggestions(word):
                a = menu.addAction(s)
                a.triggered.connect(lambda _=False, w=s, c=QTextCursor(cursor): c.insertText(w))
                extra.append(a)
            a = menu.addAction(tr("Zum Wörterbuch hinzufügen"))
            a.triggered.connect(lambda _=False, w=word: (engine.add_to_dictionary(w), self.refresh_spelling()))
            extra.append(a)
            a = menu.addAction(tr("Ignorieren"))
            a.triggered.connect(lambda _=False, w=word: (engine.ignore(w), self.refresh_spelling()))
            extra.append(a)

        # --- comments -----------------------------------------------------
        existing = self._comment_at(pos)
        if existing is not None:
            for text, fn in ((tr("Kommentar bearbeiten …"), lambda: self.edit_comment_dialog(existing)),
                             (tr("Kommentar löschen"), lambda: self.delete_comment(existing))):
                a = menu.addAction(text)
                a.triggered.connect(lambda _=False, f=fn: f())
                extra.append(a)
        elif cursor.hasSelection():
            a = menu.addAction(tr("Kommentar hinzufügen …"))
            a.triggered.connect(lambda _=False: self.add_comment_dialog())
            extra.append(a)

        # --- links --------------------------------------------------------
        href = self.anchorAt(pos)
        if href:
            a = menu.addAction(tr("Link im Browser öffnen"))
            a.triggered.connect(lambda _=False, h=href: self.open_link(h))
            extra.append(a)

        # Put our actions first, separated from the standard ones
        if extra and first is not None:
            for a in extra:
                menu.removeAction(a)
                menu.insertAction(first, a)
            menu.insertSeparator(first)

        menu.exec(event.globalPos())
