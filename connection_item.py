# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Threads: the visual connection between two pins.

Four rules govern whether and how a thread is painted:

    A. Zoom-out hides threads.  Below 100 % zoom (< 1.0), threads are not
       painted at all — a zoomed-out view is for surveying, not for reading.
    B. Selection focus.  When any note is selected (at any zoom), only
       threads that have a pin on a selected note are painted.  Every other
       thread is skipped, both to reduce noise and to save rendering work.
    C. LOD floor on large boards.  When the board has more than
       ``BIG_BOARD_NOTES`` notes or more than ``BIG_BOARD_THREADS`` threads,
       every painted thread uses ``DETAIL_STROKE`` (a bare 1-px line), no
       matter what the visible-thread count would otherwise choose.  This is
       the maximum-performance mode.
    D. Otherwise, detail tier is chosen per frame from
       ``_visible_thread_count`` as before.

The thread count itself is maintained per frame in ``BoardView.paintEvent``
(with a pan-throttle so it is not recomputed on every paint event).  The
selected-note set is maintained in ``BoardScene`` when the selection
changes.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainterPath, QPainterPathStroker, QPen,
    QPainter, QTextOption,
)
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsItem

from models import DEFAULT_THREAD_COLOR
from pin_item import PinItem, paint_pin_head
from i18n import tr, N_


MAX_FADE_NOTES = 3
LOD_DETAIL = 0.30
TOTAL_THREAD_LIMIT = 500

# Rule A: below this zoom (i.e. zoomed out past 100 %), hide all threads
# unless a note is selected.
ZOOM_HIDE_THREADS = 0.5

# Rule C: above these limits, always DETAIL_STROKE.
BIG_BOARD_NOTES = 500
BIG_BOARD_THREADS = 500


class ConnectionItem(QGraphicsPathItem):
    """A thread between two pins (it sags slightly), optionally with a label."""

    THREAD_Z = 100_000
    OVER_NOTE_OPACITY = 0.5
    HIT_PEN_WIDTH = 9

    DETAIL_FULL = 0
    DETAIL_MEDIUM = 1
    DETAIL_LABEL = 2
    DETAIL_STROKE = 3

    VISIBLE_FULL = 20
    VISIBLE_MEDIUM = 50
    VISIBLE_LABEL = 500

    def __init__(self, model, start_pin, end_pin):
        """Create the thread between two pins."""
        super().__init__()
        self.model = model
        self.start_pin = start_pin
        self.end_pin = end_pin
        self.setZValue(self.THREAD_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(QPen(QColor(0, 0, 0, 0), 1))
        self.setToolTip(tr("Rechtsklick: Farbe / Beschriftung / Löschen"))

        self._cached_path = QPainterPath()
        self._cached_bounds = QRectF()
        self._cached_label_rect = QRectF()

        self._hidden = False

        self.update_connection()

    # ---------- Zustand ----------

    def set_color(self, color: str):
        """Change the thread colour."""
        self.model.color = color
        self.update()

    def set_label(self, text: str):
        """Set / clear the text shown on the thread."""
        self.model.label = text.strip()
        self._invalidate_label()
        self.update()

    def update_connection(self):
        """Recompute path and bounding rect when a pin moves."""
        start = self.start_pin.scenePos()
        end = self.end_pin.scenePos()
        self._cached_path = thread_path(start, end)
        self.setPath(self._cached_path)
        self._cached_bounds = self._cached_path.boundingRect().adjusted(-8, -8, 8, 8)
        self._invalidate_label()
        self.prepareGeometryChange()

    # ---------- Beschriftung ----------

    @staticmethod
    def _label_font():
        """Font of the label."""
        font = QFont()
        font.setPointSizeF(8.5)
        font.setBold(True)
        return font

    def _invalidate_label(self):
        """Recompute and cache the label rect."""
        if not self.model.label or self._cached_path.isEmpty():
            self._cached_label_rect = QRectF()
            return
        fm = QFontMetrics(self._label_font())
        w = fm.horizontalAdvance(self.model.label) + 18
        h = 20
        mid = self._cached_path.pointAtPercent(0.5)
        self._cached_label_rect = QRectF(mid.x() - w / 2, mid.y() - h / 2, w, h)

    def _label_rect(self):
        """Rectangle of the label at the middle of the thread (null if no label)."""
        return self._cached_label_rect

    # ---------- Geometrie ----------

    def boundingRect(self):
        """Qt: the area this item may paint into."""
        r = self._cached_bounds
        lr = self._cached_label_rect
        return r.united(lr.adjusted(-3, -3, 3, 3)) if not lr.isNull() else r

    def shape(self):
        """Hit area: 9 px band around the path, minus small discs at the pins.

        Returns an empty path when the thread is currently hidden (rule A,
        rule B, or off-screen), so clicks pass through to the note behind it.
        """
        if self._hidden:
            return QPainterPath()
        scene = self.scene()
        if scene is not None:
            selected_ids = getattr(scene, "_selected_note_ids", None)
            if selected_ids:
                if (self.start_pin.note.model.id not in selected_ids
                        and self.end_pin.note.model.id not in selected_ids):
                    return QPainterPath()

        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_PEN_WIDTH)
        p = stroker.createStroke(self._cached_path)
        for pin in (self.start_pin, self.end_pin):
            hole = QPainterPath()
            c = pin.scenePos()
            hole.addEllipse(c, 11, 11)
            p = p.subtracted(hole)
        lr = self._cached_label_rect
        if not lr.isNull():
            p.addRect(lr)
        return p

    def _notes_under_thread(self, limit=MAX_FADE_NOTES + 1):
        """Scene rects under the thread, up to ``limit``."""
        scene = self.scene()
        if scene is None:
            return []
        return scene.note_rects_overlapping(
            self.sceneBoundingRect(), limit=limit)

    # ---------- LOD ----------

    def _detail_level(self, lod, big_board):
        """Pick a detail tier for this paint.

        ``big_board`` short-circuits to DETAIL_STROKE (rule C).  Otherwise
        the tier is chosen from the per-frame visible-thread count.
        """
        if big_board:
            return self.DETAIL_STROKE
        if lod < LOD_DETAIL:
            return self.DETAIL_STROKE
        scene = self.scene()
        if scene is None:
            return self.DETAIL_FULL
        visible = getattr(scene, "_visible_thread_count", 0)
        if visible > self.VISIBLE_LABEL:
            return self.DETAIL_STROKE
        if visible > self.VISIBLE_MEDIUM:
            return self.DETAIL_LABEL
        if visible > self.VISIBLE_FULL:
            return self.DETAIL_MEDIUM
        if len(scene.connection_items) > TOTAL_THREAD_LIMIT:
            return self.DETAIL_MEDIUM
        return self.DETAIL_FULL

    # ---------- Painting ----------

    def _draw_thread(self, painter, path, color):
        """Draw one thread at full detail.

        Qt's ``drawPath`` combines ``fillPath`` + ``strokePath``.  Since this
        item never sets a brush, the brush comes from whatever Qt's engine
        left the painter at — under ``QGraphicsScene.render()`` that can be
        the default black brush, which fills the bezier's convex hull and
        produces the wide black bands.  ``strokePath`` only strokes, so it's
        safe regardless of the current brush state.
        """
        painter.setBrush(Qt.BrushStyle.NoBrush)  # defensive
        if self.isSelected():
            painter.strokePath(
                path,
                QPen(QColor(108, 156, 255, 110), 9,
                     Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap),
            )
        painter.save()
        painter.translate(2, 4)
        painter.strokePath(
            path,
            QPen(QColor(0, 0, 0, 80), 3.5,
                 Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap),
        )
        painter.restore()
        painter.strokePath(
            path,
            QPen(color, 3, Qt.PenStyle.SolidLine,
                 Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin),
        )

    def _draw_faded(self, painter, path, color, over_notes):
        """Draw the thread with the part over notes at reduced opacity."""
        outside = QPainterPath()
        outside.addRect(self.boundingRect())
        outside = outside.subtracted(over_notes)

        painter.save()
        painter.setClipPath(outside, Qt.ClipOperation.IntersectClip)
        self._draw_thread(painter, path, color)
        painter.restore()

        painter.save()
        painter.setClipPath(over_notes, Qt.ClipOperation.IntersectClip)
        painter.setOpacity(painter.opacity() * self.OVER_NOTE_OPACITY)
        self._draw_thread(painter, path, color)
        painter.restore()

    def _draw_label(self, painter, color):
        """Draw the label pill in the middle of the thread (if any)."""
        lr = self._cached_label_rect
        if lr.isNull():
            return
        painter.setBrush(QColor(30, 31, 36, 235))
        painter.setPen(QPen(color, 1.5))
        painter.drawRoundedRect(lr, 9, 9)
        painter.setFont(self._label_font())
        painter.setPen(QColor("#e6e6ea"))
        painter.drawText(lr, self.model.label,
                         QTextOption(Qt.AlignmentFlag.AlignCenter))

    def paint(self, painter, option, widget=None):
        """Qt: draw the item (applying rules A, B, C, D)."""
        path = self._cached_path
        if path.isEmpty():
            self._hidden = True
            return

        scene = self.scene()
        if scene is None:
            self._hidden = True
            return

        # Export path: full fidelity, no LOD, no culling, no fading.
        if getattr(scene, "export_mode", False):
            self._paint_full(painter, path)
            return

        # Rule B: selection focus.
        # A thread that touches the selection is visible, period.
        selected_ids = getattr(scene, "_selected_note_ids", None)
        touches_selection = bool(
            selected_ids
            and (self.start_pin.note.model.id in selected_ids
                 or self.end_pin.note.model.id in selected_ids)
        )

        if selected_ids and not touches_selection:
            # A note is selected, but this thread doesn't touch it — hide it.
            self._hidden = True
            return

        lod = option.levelOfDetailFromTransform(painter.worldTransform())

        if not touches_selection:
            # Rule A: below 100 % zoom with no relevant selection, hide.
            if lod < ZOOM_HIDE_THREADS:
                self._hidden = True
                return

            # Viewport skip: both endpoints off-screen.
            view = getattr(scene, "_view_rect", None)
            if view is not None and not view.isEmpty():
                if not (view.contains(self.start_pin.scenePos())
                        or view.contains(self.end_pin.scenePos())):
                    self._hidden = True
                    return

        # Visible from here on.
        self._hidden = False

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        color = QColor(self.model.color)
        if not color.isValid():
            color = QColor(DEFAULT_THREAD_COLOR)

        # Rule C: big board → always stroke tier, even for selected threads.
        big_board = (len(scene.note_lookup) > BIG_BOARD_NOTES
                     or len(scene.connection_items) > BIG_BOARD_THREADS)
        tier = self._detail_level(lod, big_board)

        if tier == self.DETAIL_STROKE:
            painter.setPen(QPen(color, 1, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
            if self.isSelected():
                painter.setPen(QPen(QColor(108, 156, 255, 200), 2))
                painter.drawPath(path)
            return

        if tier == self.DETAIL_LABEL:
            painter.setPen(QPen(color, 1.5, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
            if self.isSelected():
                painter.setPen(QPen(QColor(108, 156, 255, 200), 2.5))
                painter.drawPath(path)
            self._draw_label(painter, color)
            return

        if tier == self.DETAIL_MEDIUM:
            painter.save()
            painter.translate(2, 4)
            painter.setPen(QPen(QColor(0, 0, 0, 80), 3,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
            painter.restore()
            if self.isSelected():
                painter.setPen(QPen(QColor(108, 156, 255, 110), 7,
                                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawPath(path)
            painter.setPen(QPen(color, 2.5, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
            self._draw_label(painter, color)
            return

        # DETAIL_FULL
        rects = self._notes_under_thread(limit=MAX_FADE_NOTES + 1)
        if 0 < len(rects) <= MAX_FADE_NOTES:
            over_notes = QPainterPath()
            for r in rects:
                over_notes.addRect(r)
            self._draw_faded(painter, path, color, over_notes)
        else:
            self._draw_thread(painter, path, color)

        for pin in (self.start_pin, self.end_pin):
            c = pin.scenePos()
            half = PinItem.SIZE / 2
            paint_pin_head(
                painter,
                QRectF(c.x() - half, c.y() - half, PinItem.SIZE, PinItem.SIZE),
                pin.model.color, selected=pin.isSelected(),
                highlight=pin.highlight, locked=pin.model.locked,
            )
        self._draw_label(painter, color)

    def _paint_full(self, painter, path):
        """Full-fidelity paint used by PNG export.

        Uses ``strokePath`` (never ``drawPath``) so the bezier's interior is
        never filled, even if the painter's brush is left over from a
        previous item.
        """
        self._hidden = False
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        color = QColor(self.model.color)
        if not color.isValid():
            color = QColor(DEFAULT_THREAD_COLOR)

        painter.strokePath(
            path,
            QPen(color, 1.5, Qt.PenStyle.SolidLine,
                 Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin),
        )

        half = PinItem.SIZE / 2
        for pin in (self.start_pin, self.end_pin):
            c = pin.scenePos()
            paint_pin_head(
                painter,
                QRectF(c.x() - half, c.y() - half, PinItem.SIZE, PinItem.SIZE),
                pin.model.color, selected=False,
                highlight=False, locked=pin.model.locked,
            )

        self._draw_label(painter, color)

    def remove_from_pins(self):
        """Vor dem Löschen aus den Pins austragen."""
        if self in self.start_pin.connections:
            self.start_pin.connections.remove(self)
        if self in self.end_pin.connections:
            self.end_pin.connections.remove(self)

def thread_path(start: QPointF, end: QPointF) -> QPainterPath:
    """Durchhängender Faden (Bezier)."""
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    sag = min(math.hypot(dx, dy) * 0.18, 120.0)
    path = QPainterPath()
    path.moveTo(start)
    path.cubicTo(
        QPointF(start.x() + dx * 0.33, start.y() + dy * 0.33 + sag),
        QPointF(start.x() + dx * 0.66, start.y() + dy * 0.66 + sag),
        end,
    )
    return path