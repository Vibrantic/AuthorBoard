# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Application-wide settings.

Everything that is *not* specific to a single notebook lives here: spell
checker preferences, focus mode, autosave interval, the user dictionary and the
note types that are available in *every* book ("global note types").

The values are stored as JSON in ``<AuthorBoard home>/settings.json``
(see :func:`library.app_home`).  A module-level singleton ``settings`` is used
by all other modules so that a change is visible everywhere immediately.
"""

import json
import os

from library import app_home
from models import NoteTypeData

# Default values.  Unknown keys in the file are kept, missing keys fall back here.
DEFAULTS = {
    "spell_enabled": True,       # underline misspelled words
    "spell_language": "auto",    # "auto" (= UI language), "en", "de"
    "focus_mode": True,          # grey out notes that are not connected to the selection
    "autosave_minutes": 2,       # interval of the crash-recovery autosave
    "global_types": [],          # list of dicts, see NoteTypeData
    "user_words": [],            # words the user added to the spelling dictionary
}

# Keys of global note types start with this prefix so they can be told apart
# from book-specific ("custom_") and built-in types.
GLOBAL_PREFIX = "global_"


class AppSettings:
    """Small JSON-backed key/value store with typed helpers."""

    def __init__(self, path=None):
        """Load the settings file."""
        self.path = path or os.path.join(app_home(), "settings.json")
        self.data = dict(DEFAULTS)
        self.load()

    # ------------------------------------------------------------ persistence

    def load(self):
        """Read the settings file; a missing or damaged file yields the defaults."""
        self.data = dict(DEFAULTS)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self.data.update(stored)
        except (OSError, ValueError):
            pass

    def save(self):
        """Write the settings atomically (temp file + rename)."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    # ---------------------------------------------------------------- access

    def get(self, key):
        """Value of a setting (falls back to the default)."""
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value, save=True):
        """Change a setting and (by default) save immediately."""
        self.data[key] = value
        if save:
            self.save()

    # ----------------------------------------------------- global note types

    def global_types(self):
        """Return the global note types as :class:`NoteTypeData` objects."""
        out = []
        for t in self.get("global_types") or []:
            try:
                out.append(NoteTypeData(
                    key=t["key"], label=t.get("label", t["key"]),
                    color=t.get("color", "#fff176"),
                    attributes=list(t.get("attributes", [])),
                ))
            except (KeyError, TypeError):
                continue
        return out

    def set_global_types(self, types):
        """Store the global note types."""
        self.set("global_types", [
            {"key": t.key, "label": t.label, "color": t.color,
             "attributes": list(t.attributes)}
            for t in types
        ])


# The one shared instance.
settings = AppSettings()
