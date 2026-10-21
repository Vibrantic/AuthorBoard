# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""The start page: a bookshelf drawn with QGraphicsScene.

Items: ``ShelfRow`` (wooden board), ``CategoryHeader`` (draggable shelf title),
``BookItem`` (spine) and ``AddBookItem`` (the "+" slot).  ``ShelfScene`` lays
everything out (``rebuild``) and handles drops; ``ShelfPage`` is the widget with
the toolbar and all dialogs/menus.
"""

import json
import os

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from book_dialog import BookInfoDialog
from models import count_words
from storage import Storage
from theme import ACCENT, color_icon, ideal_text_color
from i18n import tr, N_

MARGIN = 40
PLANK = 14

DEFAULT_SHELF_COLOR = "#86643f"

SHELF_COLORS = [
    (N_("Eiche"), "#a07a54"),
    (N_("Walnuss"), "#6b4a35"),
    (N_("Kirsche"), "#a0522d"),
    (N_("Ahorn"), "#d2a86a"),
    (N_("Schwarz"), "#3a3a42"),
    (N_("Weiß"), "#d8d3c8"),
    (N_("Blau"), "#4a6fa5"),
    (N_("Grün"), "#4f7a5a"),
    (N_("Rot"), "#a14a4a"),
]


def _hash_height(book):
    """Deterministic height variation (0-4) derived from the book id."""
    try:
        return int(book.id.replace("-", "")[:4], 16) % 5
    except ValueError:
        return 0


# ----------------------------------------------------------------- Items

class ShelfRow(QGraphicsItem):
    """Ein Regalbrett mit Rückwand (Farbe pro Kategorie einstellbar)."""

    def __init__(self, x, y, w, h, color="", cat_id=""):
        """A shelf board covering rectangle (x, y, w, h) in colour ``color``."""
        super().__init__()
        self._rect = QRectF(x, y, w, h)
        self._color = QColor(color) if color else QColor(DEFAULT_SHELF_COLOR)
        if not self._color.isValid():
            self._color = QColor(DEFAULT_SHELF_COLOR)
        self.cat_id = cat_id
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(0)

    def boundingRect(self):
        """Qt: the area (in item coordinates) this item may paint into."""
        return self._rect.adjusted(-8, -4, 8, 14)

    def paint(self, painter, option, widget=None):

        """Qt: draw the item."""
        r = self._rect
        c = self._color
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        back = QRectF(r.left(), r.top(), r.width(), r.height() - PLANK)
        g = QLinearGradient(0, back.top(), 0, back.bottom())
        g.setColorAt(0, c.darker(460))
        g.setColorAt(1, c.darker(380))
        painter.fillRect(back, g)

        # Seitenwände
        painter.fillRect(QRectF(r.left() - 8, r.top(), 8, r.height()),
                         c.darker(170))
        painter.fillRect(QRectF(r.right(), r.top(), 8, r.height()),
                         c.darker(200))

        # Brett
        plank = QRectF(r.left() - 8, r.bottom() - PLANK, r.width() + 16, PLANK)
        pg = QLinearGradient(0, plank.top(), 0, plank.bottom())
        pg.setColorAt(0, c.lighter(125))
        pg.setColorAt(0.25, c)
        pg.setColorAt(1, c.darker(150))
        painter.fillRect(plank, pg)
        painter.fillRect(QRectF(plank.left(), plank.bottom(), plank.width(), 5),
                         QColor(0, 0, 0, 70))


class CategoryHeader(QGraphicsItem):

    """Shelf title: drag = move the shelf with its books, double-click = rename, right-click = menu."""
    H = 34

    def __init__(self, category, count, width, scene):
        """Create the header for ``category`` holding ``count`` books."""
        super().__init__()
        self.category = category
        self.count = count
        self._w = width
        self._scene = scene
        self.setAcceptHoverEvents(True)
        self._hover = False
        self.setToolTip(tr("Ziehen: Regal samt Büchern verschieben\nDoppelklick: umbenennen\nRechtsklick: Menü (Farbe, Reihenfolge, Löschen)"))
        self.setZValue(2)

    def boundingRect(self):
        """Qt: the area (in item coordinates) this item may paint into."""
        return QRectF(0, 0, self._w, self.H)

    def hoverEnterEvent(self, e):
        """Qt event handler: the pointer entered the item."""
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, e):
        """Qt event handler: the pointer left the item."""
        self._hover = False
        self.update()

    def paint(self, painter, option, widget=None):
        """Qt: draw the item."""
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        f = QFont()
        f.setPointSizeF(14)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor(ACCENT) if self._hover else QColor("#e6e6ea"))
        painter.drawText(QPointF(2, 24), self.category.name)

        w = QFontMetrics(f).horizontalAdvance(self.category.name)
        f2 = QFont()
        f2.setPointSizeF(9)
        painter.setFont(f2)
        painter.setPen(QColor("#8d8e9a"))
        label = tr("1 Buch") if self.count == 1 else tr("{n} Bücher", n=self.count)
        painter.drawText(QPointF(w + 14, 24), label)

    # ---------- Regal samt Büchern verschieben ----------

    def mousePressEvent(self, event):
        """Qt event handler: a mouse button was pressed."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_y = event.scenePos().y()
            self._block = self._scene.block_items(self.category.id)
            self._moved = False
            for it, _pos in self._block:
                it.setZValue(it.zValue() + 50)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        """Qt event handler: the mouse moved."""
        if getattr(self, "_drag_y", None) is None:
            return
        dy = event.scenePos().y() - self._drag_y
        if abs(dy) > 4:
            self._moved = True
        if self._moved:
            for it, pos in self._block:
                it.setPos(pos.x(), pos.y() + dy)
        event.accept()

    def mouseReleaseEvent(self, event):
        """Qt event handler: a mouse button was released."""
        if getattr(self, "_drag_y", None) is None:
            event.accept()
            return
        dy = event.scenePos().y() - self._drag_y
        moved = self._moved
        self._drag_y = None
        self.unsetCursor()
        if moved:
            self._scene.drop_category(self.category, dy)
        else:
            for it, pos in self._block:
                it.setZValue(it.zValue() - 50)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        """Qt event handler: double click."""
        self._scene.page.rename_category(self.category)
        event.accept()

    def contextMenuEvent(self, event):
        """Qt event handler: context-menu request."""
        self._scene.page.show_category_menu(self.category, event.screenPos())
        event.accept()


class AddBookItem(QGraphicsItem):
    """Platzhalter am Ende jedes Regalbretts: neues Notizbuch."""

    W, H = 46, 150

    def __init__(self, category, scene):
        """Create the '+' slot of a shelf."""
        super().__init__()
        self.category = category
        self._scene = scene
        self._hover = False
        self.setAcceptHoverEvents(True)
        self.setToolTip(tr("Neues Notizbuch in dieser Kategorie"))
        self.setZValue(1)

    def boundingRect(self):
        """Qt: the area (in item coordinates) this item may paint into."""
        return QRectF(0, 0, self.W, self.H)

    def hoverEnterEvent(self, e):
        """Qt event handler: the pointer entered the item."""
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, e):
        """Qt event handler: the pointer left the item."""
        self._hover = False
        self.update()

    def paint(self, painter, option, widget=None):
        """Qt: draw the item."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = QColor(ACCENT) if self._hover else QColor("#6a6b75")
        painter.setPen(QPen(col, 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(2, 2, self.W - 4, self.H - 4), 4, 4)
        painter.setPen(col)
        painter.drawLine(QPointF(self.W / 2 - 7, self.H / 2),
                         QPointF(self.W / 2 + 7, self.H / 2))
        painter.drawLine(QPointF(self.W / 2, self.H / 2 - 7),
                         QPointF(self.W / 2, self.H / 2 + 7))

    def mousePressEvent(self, event):
        """Qt event handler: a mouse button was pressed."""
        event.accept()

    def mouseReleaseEvent(self, event):
        """Qt event handler: a mouse button was released."""
        if (event.button() == Qt.MouseButton.LeftButton
                and self.boundingRect().contains(event.pos())):
            self._scene.page.new_book_requested.emit(self.category.id)
        event.accept()


class BookItem(QGraphicsItem):
    """Notizbuch als Buchrücken im Regal."""

    def __init__(self, book, scene):
        """Create the spine; width grows with the word count."""
        super().__init__()
        self.book = book
        self._scene = scene
        self._hover = False
        self._home = QPointF(0, 0)
        self.row = 0

        self.W = 44 + min(book.word_count // 1500, 36)
        self.H = 150 + _hash_height(book) * 8

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        self.setToolTip(self._tooltip())

    def _tooltip(self):
        """HTML tool-tip with author, genre, counts, goal, deadline."""
        b = self.book
        lines = [f"<b>{b.title}</b>"]
        if b.author:
            lines.append(tr("von {author}", author=b.author))
        if b.genre:
            lines.append(tr("Genre: {genre}", genre=b.genre))
        lines.append(tr("{n} Notizen · {words} Wörter", n=b.note_count, words=b.word_count))
        if b.target_words:
            pct = min(100, int(b.word_count * 100 / b.target_words))
            lines.append(tr("Ziel: {target} Wörter ({pct} %)", target=b.target_words, pct=pct))
        if b.deadline:
            lines.append(tr("Abgabe: {date}", date=b.deadline))
        return "<br>".join(lines)

    def boundingRect(self):
        """Qt: the area (in item coordinates) this item may paint into."""
        return QRectF(-4, -12, self.W + 10, self.H + 14)

    def set_home(self, pos):
        """Remember the layout position the book returns to when dropped nowhere."""
        self._home = QPointF(pos)
        self.setPos(pos)

    def hoverEnterEvent(self, e):
        """Qt event handler: the pointer entered the item."""
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, e):
        """Qt event handler: the pointer left the item."""
        self._hover = False
        self.update()

    # ---------- Zeichnen ----------

    def paint(self, painter, option, widget=None):

        """Qt: draw the item."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        W, H = self.W, self.H
        base = QColor(self.book.color)
        if not base.isValid():
            base = QColor("#8d6e63")

        painter.save()
        if self._hover and not self.isSelected():
            painter.translate(0, -7)

        rect = QRectF(0, 0, W, H)

        # Schatten
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawRoundedRect(rect.translated(4, 0), 3, 3)

        # Rücken
        g = QLinearGradient(0, 0, W, 0)
        g.setColorAt(0, base.lighter(118))
        g.setColorAt(0.4, base)
        g.setColorAt(1, base.darker(130))
        painter.setBrush(g)
        painter.setPen(QPen(base.darker(160), 1))
        painter.drawRoundedRect(rect, 3, 3)

        text_col = ideal_text_color(base)
        band = QColor(text_col)
        band.setAlpha(110)

        # Zierlinien
        painter.setPen(QPen(band, 1.2))
        for y in (10, 15, H - 26, H - 21):
            painter.drawLine(QPointF(5, y), QPointF(W - 5, y))

        # Fortschritt (Wortziel)
        if self.book.target_words > 0:
            pct = min(1.0, self.book.word_count / self.book.target_words)
            bar = QRectF(10, H - 14, W - 20, 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 80))
            painter.drawRoundedRect(bar, 2, 2)
            painter.setBrush(QColor("#81c784"))
            painter.drawRoundedRect(
                QRectF(bar.left(), bar.top(), bar.width() * pct, bar.height()),
                2, 2
            )

        # Titel (senkrecht, von oben nach unten)
        font = QFont()
        font.setPointSizeF(9.5)
        font.setBold(True)
        fm = QFontMetrics(font)
        avail = H - 26 - 34
        title = fm.elidedText(
            self.book.title or tr("Unbenannt"),
            Qt.TextElideMode.ElideRight,
            int(avail)
        )

        painter.setFont(font)
        painter.setPen(text_col)
        painter.save()
        ox = W / 2 - (fm.ascent() - fm.descent()) / 2
        painter.translate(ox, 30)
        painter.rotate(90)
        painter.drawText(QPointF(0, 0), title)
        painter.restore()

        if self.isSelected():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(ACCENT), 2.5))
            painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 3, 3)

        painter.restore()

    # ---------- Maus ----------

    def mousePressEvent(self, event):
        """Qt event handler: a mouse button was pressed."""
        self.setZValue(100)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Qt event handler: a mouse button was released."""
        super().mouseReleaseEvent(event)
        self.setZValue(1)

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if (self.pos() - self._home).manhattanLength() < 6:
            self.setPos(self._home)
            return

        self._scene.drop_book(self)

    def mouseDoubleClickEvent(self, event):
        """Qt event handler: double click."""
        self._scene.page.open_requested.emit(self.book)
        event.accept()

    def contextMenuEvent(self, event):
        """Qt event handler: context-menu request."""
        self._scene.page.show_book_menu(self.book, event.screenPos())
        event.accept()


# ----------------------------------------------------------------- Szene

class ShelfScene(QGraphicsScene):

    """Lays out shelves and books and handles drops."""
    def __init__(self, page):
        """Create the scene for a ShelfPage."""
        super().__init__(page)
        self.page = page
        self.library = page.library
        self.width_hint = 900
        self.filter_text = ""
        self.rows = {}   # category_id -> [(y0, y1)]
        self.cat_ranges = {}   # category_id -> (y_oben, y_unten)

    def block_items(self, cat_id):
        """Alle Items eines Regals (Überschrift, Bretter, Bücher) mit Startposition."""

        out = []
        for it in self.items():
            if getattr(it, "cat_id", None) == cat_id:
                out.append((it, QPointF(it.pos())))
            elif isinstance(it, CategoryHeader) and it.category.id == cat_id:
                out.append((it, QPointF(it.pos())))
        return out

    def drop_category(self, category, dy):
        """Regal wurde losgelassen: neue Position in der Reihenfolge bestimmen."""

        lib = self.library
        y0, y1 = self.cat_ranges.get(category.id, (0, 0))
        center = (y0 + y1) / 2 + dy

        index = 0
        for other in lib.categories:
            if other.id == category.id:
                continue
            o0, o1 = self.cat_ranges.get(other.id, (0, 0))
            if (o0 + o1) / 2 < center:
                index += 1

        lib.move_category_to(category.id, index)
        lib.save()

        QTimer.singleShot(0, self.rebuild)

    def rebuild(self):

        """Clear and lay out all shelves, rows and books again."""
        self.clear()
        self.rows = {}
        self.cat_ranges = {}

        lib = self.library
        W = max(self.width_hint, 480)
        inner_w = W - 2 * MARGIN

        y = 20

        for cat in lib.categories:

            books = lib.books_in(cat.id)

            cat_top = y

            header = CategoryHeader(cat, len(books), inner_w, self)
            header.setPos(MARGIN, y)
            self.addItem(header)
            y += CategoryHeader.H + 6

            items = [BookItem(b, self) for b in books]
            items.append(AddBookItem(cat, self))

            # in Reihen umbrechen
            rows = [[]]
            x = 14
            for it in items:
                if x + it.W > inner_w - 10 and rows[-1]:
                    rows.append([])
                    x = 14
                rows[-1].append(it)
                x += it.W + 5

            self.rows[cat.id] = []

            for ri, row in enumerate(rows):
                row_h = max(it.H for it in row) + 18

                self.addItem(ShelfRow(
                    MARGIN, y, inner_w, row_h + PLANK, cat.color, cat.id
                ))
                self.rows[cat.id].append((y, y + row_h + PLANK))

                x = MARGIN + 14
                for it in row:
                    it.row = ri
                    it.cat_id = cat.id
                    self.addItem(it)
                    if isinstance(it, BookItem):
                        it.set_home(QPointF(x, y + row_h - it.H))
                    else:
                        it.setPos(x, y + row_h - it.H)
                    x += it.W + 5

                y += row_h + PLANK + 22

            self.cat_ranges[cat.id] = (cat_top, y)
            y += 18

        self.setSceneRect(0, 0, W, y + 10)
        self.apply_filter()

    def apply_filter(self):

        """Dim books that do not match the search text."""
        words = self.filter_text.lower().split()

        for it in self.items():
            if not isinstance(it, BookItem):
                continue

            b = it.book
            hay = " ".join([
                b.title, b.author, b.genre, b.description,
                " ".join(f"{a.name} {a.value}" for a in b.attributes),
            ]).lower()

            ok = all(w in hay for w in words)
            it.setOpacity(1.0 if ok else 0.25)

    def drop_book(self, item):
        """Buch wurde losgelassen: Kategorie/Position bestimmen."""

        lib = self.library
        cx = item.pos().x() + item.W / 2
        cy = item.pos().y() + item.H / 2

        best_cat, best_row, best_dist = None, 0, 1e18

        for cat in lib.categories:
            for ri, (y0, y1) in enumerate(self.rows.get(cat.id, [])):
                d = 0 if y0 <= cy <= y1 else min(abs(cy - y0), abs(cy - y1))
                if d < best_dist:
                    best_cat, best_row, best_dist = cat, ri, d

        if best_cat is None:
            self.rebuild()
            return

        index = 0
        for other in self.items():
            if (
                isinstance(other, BookItem)
                and other is not item
                and getattr(other, "cat_id", None) == best_cat.id
            ):
                ocx = other.pos().x() + other.W / 2
                if other.row < best_row or (other.row == best_row and ocx < cx):
                    index += 1

        lib.move_book(item.book, best_cat.id, index)
        lib.save()

        QTimer.singleShot(0, self.rebuild)

    def contextMenuEvent(self, event):

        """Qt event handler: context-menu request."""
        super().contextMenuEvent(event)

        if not event.isAccepted():
            self.page.show_background_menu(event.screenPos())
            event.accept()


class ShelfView(QGraphicsView):

    """View of the shelf scene; re-layouts on resize (debounced)."""
    def __init__(self, scene):
        """Configure rendering and the debounce timer."""
        super().__init__(scene)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._rebuild)

    def _rebuild(self):
        """Relayout with the current viewport width."""
        self.scene().width_hint = self.viewport().width()
        self.scene().rebuild()

    def resizeEvent(self, event):
        """Qt event handler: the widget was resized."""
        super().resizeEvent(event)
        self._timer.start()

    def drawBackground(self, painter, rect):
        """Qt: paint the scene/view background (the grid)."""
        g = QLinearGradient(0, rect.top(), 0, rect.bottom())
        g.setColorAt(0, QColor("#16171b"))
        g.setColorAt(1, QColor("#1b1a1f"))
        painter.fillRect(rect, g)


# ------------------------------------------------------------------ Seite

class ShelfPage(QWidget):
    """Startseite: Bücherregal mit Kategorien."""

    open_requested = Signal(object)        # Book
    new_book_requested = Signal(str)       # category_id ("" = erste)
    library_changed = Signal()

    def __init__(self, library, parent=None):
        """Build the toolbar, the shelf view and connect everything."""
        super().__init__(parent)

        self.library = library

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QWidget()
        bar.setObjectName("ShelfBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(40, 18, 40, 14)
        bl.setSpacing(10)

        title = QLabel(tr("Meine Bibliothek"))
        title.setObjectName("ShelfTitle")
        bl.addWidget(title)
        bl.addStretch(1)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Notizbücher suchen …"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        bl.addWidget(self.search)

        b_new = QPushButton(tr("＋ Notizbuch"))
        b_cat = QPushButton(tr("＋ Kategorie"))
        b_imp = QPushButton(tr("Importieren …"))
        for b in (b_new, b_cat, b_imp):
            bl.addWidget(b)

        layout.addWidget(bar)

        self.scene = ShelfScene(self)
        self.view = ShelfView(self.scene)
        layout.addWidget(self.view, 1)

        hint = QLabel(
            tr("Doppelklick öffnet ein Notizbuch  ·  Bücher und Regale per Drag & Drop "
            "verschieben  ·  Rechtsklick: Menü")
        )
        hint.setObjectName("Hint")
        hint.setContentsMargins(40, 6, 40, 8)
        layout.addWidget(hint)

        self.search.setToolTip(tr("Titel, Autor, Genre, Beschreibung und eigene Felder durchsuchen"))
        b_new.setToolTip(tr("Neues Notizbuch anlegen (Strg+N)"))
        b_cat.setToolTip(tr("Neues Regal (Kategorie) anlegen"))
        b_imp.setToolTip(tr("Vorhandene Board-Dateien ins Regal übernehmen"))

        b_new.clicked.connect(lambda: self.new_book_requested.emit(""))
        b_cat.clicked.connect(self.add_category)
        b_imp.clicked.connect(self.import_files)
        self.search.textChanged.connect(self._on_search)

        self.refresh()

    # ---------------------------------------------------------------

    def refresh(self):
        """Relayout the shelves."""
        self.scene.width_hint = max(self.view.viewport().width(), 900)
        self.scene.rebuild()

    def _on_search(self, text):
        """Search box changed."""
        self.scene.filter_text = text
        self.scene.apply_filter()

    def _changed(self):
        """Save the library and relayout after a modification."""
        self.library.save()
        self.scene.rebuild()
        self.library_changed.emit()

    # ------------------------------------------------------- Kategorien

    def add_category(self):
        """Ask for a name and add a shelf."""
        name, ok = QInputDialog.getText(
            self, tr("Neue Kategorie"), tr("Name der Kategorie:")
        )
        if ok and name.strip():
            self.library.add_category(name)
            self._changed()

    def rename_category(self, category):
        """Ask for a new shelf name."""
        name, ok = QInputDialog.getText(
            self, tr("Kategorie umbenennen"), tr("Neuer Name:"), text=category.name
        )
        if ok and name.strip():
            self.library.rename_category(category.id, name)
            self._changed()

    def set_category_color(self, category, color):
        """Set a shelf colour."""
        self.library.set_category_color(category.id, color)
        self._changed()

    def pick_category_color(self, category):
        """Choose a custom shelf colour."""
        c = QColorDialog.getColor(
            QColor(category.color or DEFAULT_SHELF_COLOR), self, tr("Regalfarbe")
        )
        if c.isValid():
            self.set_category_color(category, c.name())

    def delete_category(self, category):

        """Delete a shelf (its books move to another shelf)."""
        if len(self.library.categories) <= 1:
            QMessageBox.information(
                self, tr("Kategorie löschen"),
                tr("Die letzte Kategorie kann nicht gelöscht werden.")
            )
            return

        n = len(self.library.books_in(category.id))
        text = tr("Kategorie „{name}“ löschen?", name=category.name)
        if n:
            text += "\n" + tr("{n} Notizbücher werden in eine andere Kategorie verschoben.", n=n)

        if QMessageBox.question(
            self, tr("Kategorie löschen"), text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.library.delete_category(category.id)
            self._changed()

    def show_category_menu(self, category, pos):

        """Context menu of a shelf title."""
        menu = QMenu(self)
        menu.addAction(tr("Umbenennen …")).triggered.connect(
            lambda: self.rename_category(category)
        )
        menu.addAction(tr("Neues Notizbuch hier …")).triggered.connect(
            lambda: self.new_book_requested.emit(category.id)
        )
        color_menu = menu.addMenu(tr("Regalfarbe"))
        for name, hex_color in SHELF_COLORS:
            act = color_menu.addAction(color_icon(hex_color), tr(name))
            act.triggered.connect(
                lambda _=False, c=hex_color: self.set_category_color(category, c)
            )
        color_menu.addSeparator()
        color_menu.addAction(tr("Eigene Farbe …")).triggered.connect(
            lambda: self.pick_category_color(category)
        )
        color_menu.addAction(tr("Standard")).triggered.connect(
            lambda: self.set_category_color(category, "")
        )

        menu.addSeparator()
        menu.addAction(tr("Nach oben")).triggered.connect(
            lambda: (self.library.move_category(category.id, -1), self._changed())
        )
        menu.addAction(tr("Nach unten")).triggered.connect(
            lambda: (self.library.move_category(category.id, 1), self._changed())
        )
        menu.addSeparator()
        menu.addAction(tr("Kategorie löschen …")).triggered.connect(
            lambda: self.delete_category(category)
        )
        menu.exec(pos)

    def show_background_menu(self, pos):
        """Context menu of the empty shelf area."""
        menu = QMenu(self)
        menu.addAction(tr("Neues Notizbuch …")).triggered.connect(
            lambda: self.new_book_requested.emit("")
        )
        menu.addAction(tr("Neue Kategorie …")).triggered.connect(self.add_category)
        menu.exec(pos)

    # ----------------------------------------------------------- Bücher

    def edit_book(self, book):

        """Edit a book's information."""
        dialog = BookInfoDialog(book, self.library.categories, self)

        if dialog.exec() != BookInfoDialog.DialogCode.Accepted:
            return

        old_cat = book.category_id
        dialog.apply(book)

        if book.category_id != old_cat:
            self.library.move_book(
                book, book.category_id, len(self.library.books_in(book.category_id))
            )

        self._changed()

    def delete_book(self, book):

        """Delete a book after confirmation."""
        answer = QMessageBox.question(
            self,
            tr("Notizbuch löschen"),
            tr("„{title}“ wirklich löschen?\nAlle Notizen darin gehen unwiderruflich verloren.",
               title=book.title),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if answer == QMessageBox.StandardButton.Yes:
            self.library.delete_book(book)
            self._changed()

    def show_book_menu(self, book, pos):

        """Context menu of a book."""
        menu = QMenu(self)
        menu.addAction(tr("Öffnen")).triggered.connect(
            lambda: self.open_requested.emit(book)
        )
        menu.addAction(tr("Info bearbeiten …")).triggered.connect(
            lambda: self.edit_book(book)
        )

        def pick_color():
            c = QColorDialog.getColor(QColor(book.color), self, tr("Buchfarbe"))
            if c.isValid():
                book.color = c.name()
                self._changed()

        menu.addAction(tr("Buchfarbe …")).triggered.connect(pick_color)

        move = menu.addMenu(tr("In Kategorie verschieben"))
        for cat in self.library.categories:
            act = move.addAction(cat.name)
            act.setEnabled(cat.id != book.category_id)
            act.triggered.connect(
                lambda _=False, c=cat: (
                    self.library.move_book(
                        book, c.id, len(self.library.books_in(c.id))
                    ),
                    self._changed(),
                )
            )

        menu.addAction(tr("Duplizieren")).triggered.connect(
            lambda: (self.library.duplicate_book(book), self._changed())
        )
        menu.addSeparator()
        menu.addAction(tr("Löschen …")).triggered.connect(
            lambda: self.delete_book(book)
        )
        menu.exec(pos)

    def import_files(self):

        """Import board files (``.json``); an optional ``book`` entry supplies title, author …"""
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("Boards importieren"), "", "AuthorBoard (*.json)"
        )

        added = 0
        for f in files:
            try:
                project = Storage.load(f)
            except Exception as error:
                QMessageBox.critical(
                    self, tr("Import fehlgeschlagen"), f"{os.path.basename(f)}:\n{error}"
                )
                continue

            words = sum(count_words(n.content) for n in project.notes)
            title = os.path.splitext(os.path.basename(f))[0]
            book = self.library.import_file(
                f, self.library.categories[0].id, title,
                len(project.notes), words
            )

            # Optionaler "book"-Eintrag (Titel, Autor, Genre, Wortziel …)
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self.library.apply_meta(book, raw.get("book"))
            except (OSError, ValueError, AttributeError):
                pass

            added += 1

        if added:
            self._changed()
