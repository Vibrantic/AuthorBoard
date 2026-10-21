# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""State-based undo/redo: a list of JSON snapshots with a moving index.
"""

class UndoStack:
    """Zustandsbasierter Undo/Redo-Verlauf (Snapshots als JSON-Strings)."""

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

        if self.current == state:
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
