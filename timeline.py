# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Horizontal timeline widget (a custom painted ``QWidget``).

Notes with the attribute *Date* become dots on an axis; clicking a dot opens an
information bubble.  Dates are converted to a single float ("days") by
``date_to_days`` so notes can be placed on a linear axis.
"""

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QTextOption,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QToolTip, QWidget

from i18n import tr
from theme import ACCENT

DAYS_PER_YEAR = 365.2425
MONTH_DAYS = 30.44

# Schrittweiten der Achsenbeschriftung in Monaten bzw. Jahren
MONTH_STEPS = [1, 3, 6]
YEAR_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000]


def date_to_days(key):
    """((Jahr, Monat, Tag), Minuten) -> fortlaufende Tageszahl."""

    (year, month, day), minutes = key
    return (
        year * DAYS_PER_YEAR
        + (max(month, 1) - 1) * MONTH_DAYS
        + (max(day, 1) - 1)
        + minutes / 1440.0
    )


class TimelineEntry:
    """One dated note on the timeline."""
    def __init__(self, note, x, date_text, type_label):
        """Remember note, position (days), date text and type label."""
        self.note = note
        self.x = x
        self.date_text = date_text
        self.type_label = type_label
        self.level = 0

    @property
    def color(self):
        """The note's colour."""
        c = QColor(self.note.model.color)
        return c if c.isValid() else QColor("#fff176")

    @property
    def title(self):
        """The note's title."""
        return self.note.model.title or tr("Ohne Titel")


class TimelineWidget(QWidget):
    """Horizontale Zeitleiste: Punkte in Notizfarbe, Klick öffnet eine Info-Blase."""

    note_activated = Signal(object)    # Notiz anspringen

    MARGIN = 40
    BUBBLE_W = 270

    def __init__(self, parent=None):
        """Create an empty timeline."""
        super().__init__(parent)

        self.entries = []
        self.undated = 0
        self.always = set()          # Notiz-IDs mit dauerhaftem Etikett
        self.active = None           # Eintrag mit geöffneter Blase
        self.hover = None

        self.view_min = 0.0
        self.ppd = 0.05              # Pixel pro Tag
        self._fitted = False

        self._press = None
        self._moved = False
        self._bubble_rects = {}

        self.setMouseTracking(True)
        self.setMinimumHeight(240)
        self.setToolTip("")

    # ------------------------------------------------------------ Daten

    def set_entries(self, entries, undated=0):
        """entries: Liste (note, tage, datum_text, art_label)."""

        active_id = self.active.note.model.id if self.active else None

        self.entries = [TimelineEntry(*e) for e in entries]
        self.entries.sort(key=lambda e: e.x)
        self.undated = undated

        self.active = None
        for e in self.entries:
            if e.note.model.id == active_id:
                self.active = e

        self.always &= {e.note.model.id for e in self.entries}

        if not self._fitted and self.entries:
            self.fit()

        self.update()

    def fit(self):
        """Alle Einträge sichtbar machen."""

        if not self.entries:
            return

        lo = self.entries[0].x
        hi = self.entries[-1].x
        span = hi - lo
        pad = max(span * 0.08, 60.0)

        usable = max(self.width() - 2 * self.MARGIN, 200)
        self.ppd = usable / (span + 2 * pad)
        self.view_min = lo - pad
        self._fitted = True
        self.update()

    # ------------------------------------------------------- Koordinaten

    def axis_y(self):
        """y coordinate of the time axis."""
        return self.height() - 56

    def sx(self, x):
        """Screen x of a position in days."""
        return self.MARGIN + (x - self.view_min) * self.ppd

    def point_pos(self, e):
        """Screen position of an entry's dot (incl. stacking level)."""
        return QPointF(self.sx(e.x), self.axis_y() - e.level * 17)

    def _assign_levels(self):
        """Überlappende Punkte übereinander staffeln."""

        placed = []
        for e in self.entries:
            px = self.sx(e.x)
            level = 0
            while level < 6 and any(
                abs(px - ox) < 17 and lv == level for ox, lv in placed
            ):
                level += 1
            e.level = level
            placed.append((px, level))

    # ------------------------------------------------------------ Ticks

    def _ticks(self):
        """Liste (tage, beschriftung) für den sichtbaren Bereich."""

        vmin = self.view_min
        vmax = self.view_min + (self.width() - 2 * self.MARGIN) / self.ppd

        ticks = []
        px_per_year = self.ppd * DAYS_PER_YEAR
        target_px = 120.0

        if px_per_year * 1.0 >= target_px * 1.5:
            # Monatsraster
            raw_months = target_px / (px_per_year / 12.0)
            step = next((m for m in MONTH_STEPS if m >= raw_months), 12)
            y0 = int(math.floor(vmin / DAYS_PER_YEAR)) - 1
            y1 = int(math.ceil(vmax / DAYS_PER_YEAR)) + 1
            for year in range(y0, y1 + 1):
                for month in range(1, 13, step):
                    x = year * DAYS_PER_YEAR + (month - 1) * MONTH_DAYS
                    if vmin <= x <= vmax:
                        ticks.append((x, f"{month:02d}.{year}"))
        else:
            raw_years = target_px / px_per_year
            step = next((s for s in YEAR_STEPS if s >= raw_years), YEAR_STEPS[-1])
            first = int(math.floor(vmin / DAYS_PER_YEAR / step)) * step
            year = first
            limit = int(math.ceil(vmax / DAYS_PER_YEAR)) + step
            while year <= limit:
                x = year * DAYS_PER_YEAR
                if vmin <= x <= vmax:
                    ticks.append((x, str(year)))
                year += step

        return ticks

    # ------------------------------------------------------------ Zeichnen

    def paintEvent(self, event):

        """Qt event handler: repaint the widget."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        p.fillRect(self.rect(), QColor("#1a1b20"))

        self._bubble_rects = {}

        if not self.entries:
            p.setPen(QColor("#7c7c88"))
            p.drawText(
                QRectF(self.rect()),
                self._t_empty(),
                QTextOption(Qt.AlignmentFlag.AlignCenter),
            )
            return

        self._assign_levels()

        ay = self.axis_y()

        # Achse
        p.setPen(QPen(QColor("#44454f"), 1.5))
        p.drawLine(QPointF(self.MARGIN - 20, ay), QPointF(self.width() - 20, ay))

        font = QFont("monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSizeF(8)
        p.setFont(font)

        for x, label in self._ticks():
            px = self.sx(x)
            p.setPen(QPen(QColor("#44454f"), 1))
            p.drawLine(QPointF(px, ay), QPointF(px, ay + 8))
            p.setPen(QColor("#8d8e9a"))
            p.drawText(QPointF(px - 4, ay + 24), label)

        # Hinweis
        hint_font = QFont()
        hint_font.setPointSizeF(8)
        p.setFont(hint_font)
        p.setPen(QColor("#5d5e69"))
        p.drawText(QPointF(12, self.height() - 10), self._t_hint())
        if self.undated:
            txt = self._t_undated(self.undated)
            w = QFontMetrics(hint_font).horizontalAdvance(txt)
            p.drawText(QPointF(self.width() - w - 12, self.height() - 10), txt)

        # Punkte
        for e in self.entries:
            self._paint_point(p, e)

        # Etiketten
        label_font = QFont()
        label_font.setPointSizeF(8.5)
        label_font.setBold(True)
        p.setFont(label_font)
        fm = QFontMetrics(label_font)

        for e in self.entries:
            if e.note.model.id in self.always and e is not self.active:
                pos = self.point_pos(e)
                text = fm.elidedText(e.title, Qt.TextElideMode.ElideRight, 180)
                rect = QRectF(pos.x() + 12, pos.y() - 11, fm.horizontalAdvance(text) + 16, 22)
                bg = QColor(e.color)
                bg.setAlpha(45)
                p.setPen(QPen(QColor(e.color.red(), e.color.green(), e.color.blue(), 120), 1))
                p.setBrush(bg)
                p.drawRoundedRect(rect, 6, 6)
                p.setPen(e.color.lighter(120))
                p.drawText(QPointF(rect.left() + 8, rect.bottom() - 7), text)

        # Blase
        if self.active is not None:
            self._paint_bubble(p, self.active)

    def _paint_point(self, p, e):

        """Draw one dot (with glow when hovered / active)."""
        pos = self.point_pos(e)
        c = e.color
        hot = e is self.active or e is self.hover

        if hot:
            p.setPen(Qt.PenStyle.NoPen)
            glow = QColor(c)
            glow.setAlpha(70)
            p.setBrush(glow)
            p.drawEllipse(pos, 12, 12)

        p.setPen(QPen(QColor("#ffffff") if e is self.active else c.darker(150), 2))
        p.setBrush(c)
        p.drawEllipse(pos, 6.5, 6.5)

    def _paint_bubble(self, p, e):

        """Draw the information bubble of the active entry and remember its click areas."""
        pos = self.point_pos(e)
        c = e.color

        w = self.BUBBLE_W
        header_h, body_h, footer_h = 32, 62, 30
        h = header_h + body_h + footer_h

        x = min(max(pos.x() - w / 2, 8), self.width() - w - 8)
        y = max(pos.y() - h - 16, 6)
        rect = QRectF(x, y, w, h)

        # Pfeil zum Punkt
        arrow = QPainterPath()
        ax = min(max(pos.x(), x + 16), x + w - 16)
        arrow.moveTo(ax - 8, rect.bottom())
        arrow.lineTo(ax + 8, rect.bottom())
        arrow.lineTo(ax, rect.bottom() + 9)
        arrow.closeSubpath()

        body = QPainterPath()
        body.addRoundedRect(rect, 9, 9)
        body = body.united(arrow)

        p.setPen(QPen(QColor("#3a3b45"), 1))
        p.setBrush(QColor("#1e1f24"))
        p.drawPath(body)

        # Kopfzeile in Notizfarbe
        head = QRectF(x + 6, y + 6, w - 12, header_h - 6)
        tint = QColor(c)
        tint.setAlpha(55)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(tint)
        p.drawRoundedRect(head, 5, 5)

        p.setBrush(c)
        p.drawEllipse(QPointF(head.left() + 13, head.center().y()), 5, 5)

        tf = QFont()
        tf.setPointSizeF(10)
        tf.setBold(True)
        p.setFont(tf)
        p.setPen(c.lighter(125))
        fm = QFontMetrics(tf)
        title = fm.elidedText(e.title, Qt.TextElideMode.ElideRight, int(head.width() - 60))
        p.drawText(QPointF(head.left() + 26, head.center().y() + fm.ascent() / 2 - 2), title)

        # Sprung-Schaltfläche ">"
        jump = QRectF(head.right() - 30, head.top(), 28, head.height())
        self._bubble_rects["jump"] = jump
        p.setPen(QColor("#e6e6ea"))
        p.drawText(jump, "›", QTextOption(Qt.AlignmentFlag.AlignCenter))

        # Inhalt
        sf = QFont()
        sf.setPointSizeF(8.5)
        p.setFont(sf)
        p.setPen(QColor("#8d8e9a"))
        TO = QTextOption
        p.drawText(QRectF(x, y + header_h + 6, w, 16), e.type_label, TO(Qt.AlignmentFlag.AlignCenter))

        df = QFont()
        df.setPointSizeF(12)
        df.setBold(True)
        p.setFont(df)
        p.setPen(QColor("#f1f1f4"))
        p.drawText(QRectF(x + 8, y + header_h + 24, w - 16, 30), e.date_text, TO(Qt.AlignmentFlag.AlignCenter))

        # Fußzeile
        foot_y = y + header_h + body_h
        p.setPen(QPen(QColor("#33343d"), 1))
        p.drawLine(QPointF(x, foot_y), QPointF(x + w, foot_y))

        foot = QRectF(x, foot_y, w, footer_h)
        self._bubble_rects["label"] = foot
        on = e.note.model.id in self.always
        p.setFont(sf)
        p.setPen(QColor(ACCENT) if on else QColor("#8d8e9a"))
        text = self._t_always()
        p.drawText(foot, ("✓ " if on else "") + text, TO(Qt.AlignmentFlag.AlignCenter))

        self._bubble_rects["bubble"] = rect

    # ----------------------------------------------------- Texte (übersetzbar)

    def _t_empty(self):
        """Text shown when there are no dated notes."""
        return tr("Notizen mit dem Attribut „Datum“ erscheinen hier chronologisch.")

    def _t_hint(self):
        """Usage hint at the bottom left."""
        return tr("Mausrad: Zoom  ·  Ziehen: verschieben  ·  Doppelklick: alles anzeigen")

    def _t_undated(self, n):
        """Text for the number of undated notes."""
        return tr("{n} Notizen ohne Datum", n=n)

    def _t_always(self):
        """Text of the 'always show label' toggle."""
        return tr("Beschriftung immer anzeigen")

    # ------------------------------------------------------------ Maus

    def _entry_at(self, pos):
        """The entry whose dot is within 11 px of ``pos`` (None if no dot is near)."""
        best, dist = None, 11.0
        for e in self.entries:
            pp = self.point_pos(e)
            d = math.hypot(pp.x() - pos.x(), pp.y() - pos.y())
            if d <= dist:
                best, dist = e, d
        return best

    def mousePressEvent(self, event):

        """Qt event handler: a mouse button was pressed."""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.position()
        self._press = pos
        self._moved = False
        self._pan_origin = (pos.x(), self.view_min)

        if self.active is not None:
            rects = self._bubble_rects
            if "jump" in rects and rects["jump"].contains(pos):
                self.note_activated.emit(self.active.note)
                self._press = None
                return
            if "label" in rects and rects["label"].contains(pos):
                nid = self.active.note.model.id
                if nid in self.always:
                    self.always.discard(nid)
                else:
                    self.always.add(nid)
                self._press = None
                self.update()
                return
            if "bubble" in rects and rects["bubble"].contains(pos):
                self._press = None
                return

    def mouseMoveEvent(self, event):

        """Qt event handler: the mouse moved."""
        pos = event.position()

        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if abs(pos.x() - self._press.x()) > 3:
                self._moved = True
            if self._moved:
                x0, vmin0 = self._pan_origin
                self.view_min = vmin0 - (pos.x() - x0) / self.ppd
                self._fitted = True
                self.update()
            return

        hover = self._entry_at(pos)
        if hover is not self.hover:
            self.hover = hover
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if hover else Qt.CursorShape.ArrowCursor
            )
            self.update()

    def mouseReleaseEvent(self, event):

        """Qt event handler: a mouse button was released."""
        if event.button() != Qt.MouseButton.LeftButton or self._press is None:
            return

        pos = event.position()
        moved = self._moved
        self._press = None

        if moved:
            return

        hit = self._entry_at(pos)
        self.active = hit if hit is not self.active else None
        self.update()

    def mouseDoubleClickEvent(self, event):
        """Qt event handler: double click."""
        if self._entry_at(event.position()) is None:
            self.active = None
            self.fit()

    def wheelEvent(self, event):

        """Qt event handler: mouse wheel."""
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        cx = event.position().x()

        anchor = self.view_min + (cx - self.MARGIN) / self.ppd
        self.ppd = min(max(self.ppd * factor, 0.0005), 40.0)
        self.view_min = anchor - (cx - self.MARGIN) / self.ppd

        self._fitted = True
        self.update()

    def event(self, ev):

        """Qt: generic event handler (used for tool-tips)."""
        if ev.type() == QEvent.Type.ToolTip:
            e = self._entry_at(ev.pos())
            if e is not None:
                QToolTip.showText(
                    ev.globalPos(),
                    f"{e.title}\n{e.type_label} · {e.date_text}",
                    self,
                )
            else:
                QToolTip.hideText()
            return True

        return super().event(ev)
