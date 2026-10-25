# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Plain data classes (no Qt) describing a notebook, plus small helper functions.

Everything the program saves is built from these classes: notes with pins,
attributes, tags, attachments and comments; threads between pins; note types.
``storage.py`` converts them to / from JSON.
"""

from dataclasses import dataclass, field
from typing import Dict, List
import uuid

from i18n import N_, tr


def generate_id() -> str:
    """A new random id (uuid4 string)."""
    return str(uuid.uuid4())


DEFAULT_PIN_COLOR = "#4da6ff"
DEFAULT_THREAD_COLOR = "#d4a373"
DEFAULT_NOTE_COLOR = "#fff176"
DEFAULT_GROUP_COLOR = "#4da6ff"



@dataclass
class AttributeData:
    """Freies Attribut einer Notiz (Name + Wert), z.B. Datum: 12.05.1887"""
    name: str = ""
    value: str = ""


@dataclass
class AttachmentData:
    """Metadata of a file attached to a note (the bytes live in the AttachmentStore)."""
    id: str = field(default_factory=generate_id)
    name: str = ""          # original file name
    mime: str = ""          # e.g. "image/png"
    size: int = 0           # bytes
    inline: bool = False    # True when the file was inserted into the text as an image


@dataclass
class CommentData:
    """A comment anchored to a word/sentence of a note's rich text.

    The anchor itself is stored in the note's HTML as a character-format
    tool-tip ``ab-comment:<id>`` (see rich_text.py)."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    text: str = ""          # the comment
    quote: str = ""         # the commented passage (for the comments list)
    created: str = ""       # ISO timestamp


@dataclass
class NoteTypeData:
    """Notizart (Charakter, Ort, Kapitel ...)."""
    key: str
    label: str
    color: str
    attributes: List[str] = field(default_factory=list)  # Vorschlags-Attribute


BUILTIN_NOTE_TYPES: List[NoteTypeData] = [
    NoteTypeData("note", N_("Notiz"), "#fff176"),
    NoteTypeData("character", N_("Charakter"), "#ffb3c1",
                 [N_("Alter"), N_("Rolle"), N_("Beruf")]),
    NoteTypeData("location", N_("Ort"), "#a5d6a7", [N_("Region"), N_("Typ")]),
    NoteTypeData("chapter", N_("Kapitel"), "#90caf9",
                 [N_("Nummer"), N_("Status"), N_("Wortzahl")]),
    NoteTypeData("scene", N_("Szene"), "#ce93d8",
                 [N_("Datum"), N_("Uhrzeit"), N_("Ort"), N_("Perspektive")]),
    NoteTypeData("event", N_("Ereignis"), "#ffcc80",
                 [N_("Datum"), N_("Uhrzeit"), N_("Ort")]),
    NoteTypeData("plot", N_("Handlung"), "#80deea", [N_("Akt"), N_("Status")]),
    NoteTypeData("item", N_("Gegenstand"), "#d7ccc8",
                 [N_("Besitzer"), N_("Herkunft")]),
    NoteTypeData("idea", N_("Idee"), "#e6ee9c"),
    NoteTypeData("research", N_("Recherche"), "#b0bec5",
                 [N_("Quelle"), N_("Link")]),
]


def builtin_note_types():
    """Eingebaute Notizarten mit Bezeichnungen in der aktuellen Sprache."""

    return [
        NoteTypeData(t.key, tr(t.label), t.color, [tr(a) for a in t.attributes])
        for t in BUILTIN_NOTE_TYPES
    ]


BUILTIN_TYPE_KEYS = {t.key for t in BUILTIN_NOTE_TYPES}

# Bearbeitungsstatus einer Notiz (key -> (Anzeigename, Farbe))
STATUS_INFO = {
    "draft": (N_("Entwurf"), "#ffb74d"),
    "revise": (N_("Überarbeiten"), "#e57373"),
    "done": (N_("Fertig"), "#81c784"),
}


@dataclass
class PinData:
    """A pin on a note; coordinates are relative to the note."""
    id: str = field(default_factory=generate_id)

    # Position relative to parent note
    x: float = 20.0
    y: float = 20.0

    color: str = DEFAULT_PIN_COLOR
    locked: bool = False     # a locked pin cannot be dragged, but still follows its note


@dataclass
class NoteData:
    """Everything stored about one note (position, text, attributes, pins …)."""
    id: str = field(default_factory=generate_id)

    title: str = "Neue Notiz"
    content: str = ""

    x: float = 0.0
    y: float = 0.0

    width: float = 260.0
    height: float = 190.0

    color: str = DEFAULT_NOTE_COLOR
    note_type: str = "note"
    status: str = ""

    locked: bool = False     # a locked note cannot be moved or resized
    rich: str = ""           # HTML of the formatted text ("" = plain note, see `content`)

    tags: List[str] = field(default_factory=list)
    attributes: List[AttributeData] = field(default_factory=list)
    pins: List[PinData] = field(default_factory=list)
    attachments: List[AttachmentData] = field(default_factory=list)
    comments: List[CommentData] = field(default_factory=list)

    # ---- Caches (not serialised, recomputed on load) ----
    # Word count of ``content`` (None = not computed yet).
    _word_cache: int = field(default=None, repr=False, compare=False)
    # Bumped whenever the model changes; used by the incremental tree.
    _revision: int = field(default=0, repr=False, compare=False)

    def touch(self):
        """Mark the model as changed: bump the revision, drop caches.

        Called by ``NoteItem.model_changed``.  UI code that mutates the model
        directly (e.g. inspector, dialog) should call this too, otherwise
        caches keyed on ``_revision`` will be stale."""
        self._revision += 1
        self._word_cache = None

@dataclass
class ConnectionData:
    """A thread between two pins (by pin id), with colour and label."""
    id: str = field(default_factory=generate_id)

    start_pin_id: str = ""
    end_pin_id: str = ""

    color: str = DEFAULT_THREAD_COLOR
    label: str = ""   # Beziehung, z.B. "Bruder von"

@dataclass
class GroupData:
    """A group frame on the board (geometric membership, see group_item.py)."""
    id: str = field(default_factory=generate_id)
    title: str = "Gruppe"
    x: float = 0.0
    y: float = 0.0
    width: float = 400.0
    height: float = 300.0
    color: str = DEFAULT_GROUP_COLOR
    locked: bool = False

@dataclass
class ProjectData:
    """A whole notebook in memory.  ``blobs`` (attachment bytes) are not part of undo snapshots."""
    notes: List[NoteData] = field(default_factory=list)
    connections: List[ConnectionData] = field(default_factory=list)
    groups: List[GroupData] = field(default_factory=list)
    custom_types: List[NoteTypeData] = field(default_factory=list)
    known_tags: List[str] = field(default_factory=list)       # tag autocomplete (per book)
    blobs: Dict[str, bytes] = field(default_factory=dict)     # attachment id -> bytes


def note_matches(note: NoteData, text: str = "", type_key: str = "",
                 tag: str = "", type_label: str = "",
                 status: str = "") -> bool:
    """Filter-/Suchlogik. Alle Suchwörter müssen irgendwo vorkommen."""

    if type_key and note.note_type != type_key:
        return False

    if status and note.status != status:
        return False

    if tag and tag.lower() not in [t.lower() for t in note.tags]:
        return False

    words = [w.lstrip("#") for w in text.lower().split()]
    words = [w for w in words if w]

    if not words:
        return True

    haystack = " ".join([
        note.title,
        note.content,
        type_label,
        " ".join(note.tags),
        " ".join(f"{a.name} {a.value}" for a in note.attributes),
    ]).lower()

    return all(w in haystack for w in words)


def count_words(text: str) -> int:
    """Number of whitespace separated words."""
    return len(text.split())


def note_word_count(note: NoteData) -> int:
    """Word count of ``note.content``, cached on the note.

    Cleared by ``NoteData.touch()``."""
    if note._word_cache is None:
        note._word_cache = count_words(note.content)
    return note._word_cache


_ATTR_SYNONYMS = {
    "Datum": {"datum", "date"},
    "Uhrzeit": {"uhrzeit", "time"},
    "Nummer": {"nummer", "nr", "nr.", "number", "no."},
}


def attribute_matches(name: str, canonical: str) -> bool:
    """Passt der Attributname zu "Datum", "Uhrzeit" oder "Nummer" (in jeder Sprache)?"""

    n = name.strip().lower()
    return (
        n in _ATTR_SYNONYMS.get(canonical, {canonical.lower()})
        or n == tr(canonical).lower()
    )


def attribute_value(note: NoteData, canonical: str) -> str:
    """Value of the first non-empty attribute named ``canonical`` (in any language)."""
    for a in note.attributes:
        if attribute_matches(a.name, canonical) and a.value.strip():
            return a.value.strip()
    return ""


def note_sort_key(note: NoteData):
    """Sortierung: Notizen mit Attribut "Nummer" zuerst (numerisch), dann Titel."""

    value = attribute_value(note, "Nummer")

    if value:
        try:
            return (0, float(value.replace(",", ".")), note.title.lower())
        except ValueError:
            pass

    return (1, 0.0, note.title.lower())


def _intval(s):
    """int() or None."""
    try:
        return int(s)
    except ValueError:
        return None


def parse_date_key(text: str):
    """Datum (TT.MM.JJJJ, JJJJ-MM-TT, MM.JJJJ, JJJJ) -> sortierbares Tupel oder None."""

    import re

    t = text.strip()
    if not t:
        return None

    m = re.fullmatch(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(-?\d{1,5})", t)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))

    m = re.fullmatch(r"(-?\d{1,5})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.fullmatch(r"(\d{1,2})\.\s*(-?\d{1,5})", t)
    if m:
        return (int(m.group(2)), int(m.group(1)), 0)

    m = re.fullmatch(r"-?\d{1,5}", t)
    if m:
        return (int(t), 0, 0)

    return None


def parse_time_key(text: str) -> int:
    """'14:30' -> minutes since midnight (0 when not parsable)."""
    import re

    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})(?:\s*Uhr)?", text.strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0


def note_timeline_key(note: NoteData):
    """(Datum, Uhrzeit) aus den Attributen 'Datum'/'Uhrzeit' oder None."""

    date_key = parse_date_key(attribute_value(note, "Datum"))

    if date_key is None:
        return None

    return (date_key, parse_time_key(attribute_value(note, "Uhrzeit")))
