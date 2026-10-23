# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""State-based undo/redo with structural sharing (Optimization.md Phase 3).

A :class:`Snapshot` is ``{note_id: json_str}`` plus the connections/meta JSON.
Unchanged notes share the same string object between snapshots, so memory is
much lower and dirty detection is identity-based.  ``changed_note_ids`` lets
``MainWindow.apply_state`` add/remove/update only the changed notes.
"""


class Snapshot:
    """One board state: per-note JSON strings + connections/meta JSON."""

    __slots__ = ("notes", "connections", "meta")

    def __init__(self, notes, connections, meta):
        """Store the three parts of a snapshot."""
        self.notes = notes
        self.connections = connections
        self.meta = meta

    def equal(self, other):
        """True when both snapshots describe the same board (identity-based)."""
        if other is None:
            return False
        if self.connections != other.connections or self.meta != other.meta:
            return False
        if self.notes.keys() != other.notes.keys():
            return False
        for k, v in self.notes.items():
            if other.notes[k] is not v and other.notes[k] != v:
                return False
        return True

    def changed_note_ids(self, other):
        """Ids of notes whose JSON differs from ``other``."""
        if other is None:
            return set(self.notes)
        out = set(self.notes) ^ set(other.notes)
        for k in self.notes.keys() & other.notes.keys():
            if self.notes[k] is not other.notes[k] and self.notes[k] != other.notes[k]:
                out.add(k)
        return out


class UndoStack:
    """Zustandsbasierter Undo/Redo-Verlauf (Snapshots mit structural sharing)."""

    def __init__(self, limit=200):
        """Create an empty history (max ``limit`` states)."""
        self.limit = limit
        self.states = []
        self.index = -1

    def reset(self, state):
        """Start a new history with a single state."""
        self.states = [state]
        self.index = 0

    @property
    def current(self):
        """The state at the current index."""
        return self.states[self.index] if self.index >= 0 else None

    def push(self, state):
        """Neuen Zustand eintragen. False, wenn unverändert."""
        current = self.current
        if current is not None and current.equal(state):
            return False
        del self.states[self.index + 1:]
        self.states.append(state)
        if len(self.states) > self.limit:
            del self.states[0]
        self.index = len(self.states) - 1
        return True

    def can_undo(self):
        """True when an older state exists."""
        return self.index > 0

    def can_redo(self):
        """True when a newer state exists."""
        return 0 <= self.index < len(self.states) - 1

    def undo(self):
        """Move back and return that state."""
        if not self.can_undo():
            return None
        self.index -= 1
        return self.states[self.index]

    def redo(self):
        """Move forward and return that state."""
        if not self.can_redo():
            return None
        self.index += 1
        return self.states[self.index]