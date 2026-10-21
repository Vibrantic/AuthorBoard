# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""The library: shelves (categories) and notebooks (books).

Storage layout (see ``app_home``)::

    ~/.authorboard/library.json     shelves + book metadata
    ~/.authorboard/books/<id>.json  one board file per book
    ~/.authorboard/backups/<id>/    timestamped copies made on save

The ``Library`` class has no GUI code; the shelf page and the main window call
it and then ``save()`` it.
"""

import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List

from i18n import N_, tr
from models import AttributeData, generate_id

BOOK_COLORS = [
    "#8d6e63", "#5c6bc0", "#26a69a", "#ab47bc",
    "#ef5350", "#ffa726", "#66bb6a", "#42a5f5",
]

DEFAULT_CATEGORIES = [N_("Romane"), N_("Kurzgeschichten"), N_("Ideen & Projekte")]


def app_home() -> str:
    """Folder that holds all AuthorBoard data (``AUTHORBOARD_HOME`` or ``~/.authorboard``)."""
    return os.environ.get("AUTHORBOARD_HOME") or os.path.join(
        os.path.expanduser("~"), ".authorboard"
    )


def _now() -> str:
    """Current time as ISO string."""
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Book:
    """Ein Notizbuch (= ein Board) im Regal."""
    id: str = field(default_factory=generate_id)
    title: str = "Neues Notizbuch"
    author: str = ""
    genre: str = ""
    description: str = ""
    color: str = "#8d6e63"
    category_id: str = ""
    target_words: int = 0
    deadline: str = ""
    attributes: List[AttributeData] = field(default_factory=list)

    created: str = field(default_factory=_now)
    modified: str = ""

    # Zwischengespeicherte Statistik (wird beim Speichern aktualisiert)
    note_count: int = 0
    word_count: int = 0

    # Tagesfortschritt: Wortzahl zu Beginn des heutigen Tages
    baseline_date: str = ""
    baseline_words: int = 0


@dataclass
class Category:
    """A shelf.  ``color`` is empty for the default wood."""
    id: str = field(default_factory=generate_id)
    name: str = "Kategorie"
    color: str = ""      # Regalfarbe ("" = Standard-Holz)


class Library:
    """Regal mit Kategorien und Notizbüchern (library.json + books/<id>.json)."""

    BACKUP_KEEP = 20
    BACKUP_MIN_INTERVAL = 300   # Sekunden zwischen zwei Sicherungen

    def __init__(self, home=None):
        """Open (or create) the library in ``home``."""
        self.home = home or app_home()
        self.path = os.path.join(self.home, "library.json")
        self.books_dir = os.path.join(self.home, "books")
        self.backup_dir = os.path.join(self.home, "backups")

        self.categories: List[Category] = []
        self.books: List[Book] = []

        self.load()

    # ------------------------------------------------------ Laden/Speichern

    def load(self):

        """Read library.json; creates default shelves on first start."""
        os.makedirs(self.books_dir, exist_ok=True)

        data = None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = None

        self.categories, self.books = [], []

        if isinstance(data, dict):
            for c in data.get("categories", []):
                self.categories.append(
                    Category(id=c["id"], name=c.get("name", "Kategorie"),
                             color=c.get("color", ""))
                )

            for b in data.get("books", []):
                self.books.append(Book(
                    id=b["id"],
                    title=b.get("title", "Notizbuch"),
                    author=b.get("author", ""),
                    genre=b.get("genre", ""),
                    description=b.get("description", ""),
                    color=b.get("color", BOOK_COLORS[0]),
                    category_id=b.get("category_id", ""),
                    target_words=int(b.get("target_words", 0) or 0),
                    deadline=b.get("deadline", ""),
                    attributes=[
                        AttributeData(a.get("name", ""), a.get("value", ""))
                        for a in b.get("attributes", [])
                    ],
                    created=b.get("created", _now()),
                    modified=b.get("modified", ""),
                    note_count=int(b.get("note_count", 0) or 0),
                    word_count=int(b.get("word_count", 0) or 0),
                    baseline_date=b.get("baseline_date", ""),
                    baseline_words=int(b.get("baseline_words", 0) or 0),
                ))

        if not self.categories:
            self.categories = [Category(name=tr(n)) for n in DEFAULT_CATEGORIES]

        ids = {c.id for c in self.categories}
        for b in self.books:
            if b.category_id not in ids:
                b.category_id = self.categories[0].id

    def save(self):

        """Write library.json atomically."""
        data = {
            "version": 1,
            "categories": [
                {"id": c.id, "name": c.name, "color": c.color}
                for c in self.categories
            ],
            "books": [
                {
                    "id": b.id,
                    "title": b.title,
                    "author": b.author,
                    "genre": b.genre,
                    "description": b.description,
                    "color": b.color,
                    "category_id": b.category_id,
                    "target_words": b.target_words,
                    "deadline": b.deadline,
                    "attributes": [
                        {"name": a.name, "value": a.value}
                        for a in b.attributes
                    ],
                    "created": b.created,
                    "modified": b.modified,
                    "note_count": b.note_count,
                    "word_count": b.word_count,
                    "baseline_date": b.baseline_date,
                    "baseline_words": b.baseline_words,
                }
                for b in self.books
            ],
        }

        os.makedirs(self.home, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    # --------------------------------------------------------- Kategorien

    def category(self, cat_id):
        """Shelf by id (None if unknown)."""
        for c in self.categories:
            if c.id == cat_id:
                return c
        return None

    def books_in(self, cat_id):
        """Books of a shelf in display order."""
        return [b for b in self.books if b.category_id == cat_id]

    def add_category(self, name):
        """Add a new shelf at the end."""
        cat = Category(name=name.strip() or tr("Kategorie"))
        self.categories.append(cat)
        return cat

    def rename_category(self, cat_id, name):
        """Rename a shelf."""
        c = self.category(cat_id)
        if c is not None and name.strip():
            c.name = name.strip()

    def set_category_color(self, cat_id, color):
        """Set the shelf colour ('' = default)."""
        c = self.category(cat_id)
        if c is not None:
            c.color = color

    def move_category_to(self, cat_id, index):
        """Kategorie (samt Büchern) an eine neue Position im Regal setzen."""

        cat = self.category(cat_id)
        if cat is None:
            return

        self.categories.remove(cat)
        index = max(0, min(index, len(self.categories)))
        self.categories.insert(index, cat)

    def delete_category(self, cat_id):
        """Bücher wandern in die erste andere Kategorie. False, wenn letzte."""

        if len(self.categories) <= 1:
            return False

        target = next(c for c in self.categories if c.id != cat_id)

        for b in self.books:
            if b.category_id == cat_id:
                b.category_id = target.id

        self.categories = [c for c in self.categories if c.id != cat_id]
        return True

    def move_category(self, cat_id, delta):
        """Move a shelf up (-1) or down (+1)."""
        for i, c in enumerate(self.categories):
            if c.id == cat_id:
                j = i + delta
                if 0 <= j < len(self.categories):
                    self.categories[i], self.categories[j] = (
                        self.categories[j], self.categories[i]
                    )
                return

    # ------------------------------------------------------------- Bücher

    def new_book(self, category_id=""):
        """Create (but do not yet add) a book on a shelf with the next spine colour."""
        book = Book()
        book.title = tr("Neues Notizbuch")
        book.category_id = category_id or self.categories[0].id
        book.color = BOOK_COLORS[len(self.books) % len(BOOK_COLORS)]
        return book

    def add_book(self, book):
        """Put a book into the library."""
        if book not in self.books:
            self.books.append(book)

    def book_path(self, book):
        """Path of the book's board file."""
        return os.path.join(self.books_dir, f"{book.id}.json")

    def move_book(self, book, cat_id, index):
        """Buch in Kategorie cat_id an Position index (innerhalb der Kategorie)."""

        if book in self.books:
            self.books.remove(book)

        book.category_id = cat_id
        others = self.books_in(cat_id)

        if index >= len(others):
            if others:
                self.books.insert(self.books.index(others[-1]) + 1, book)
            else:
                self.books.append(book)
        else:
            self.books.insert(self.books.index(others[max(index, 0)]), book)

    def delete_book(self, book):

        """Delete a book with its file, autosave and backups."""
        for p in (self.book_path(book), self.book_path(book) + ".autosave"):
            try:
                os.remove(p)
            except OSError:
                pass

        shutil.rmtree(os.path.join(self.backup_dir, book.id), ignore_errors=True)

        if book in self.books:
            self.books.remove(book)

    def duplicate_book(self, book):

        """Copy a book including its board file."""
        copy = Book(
            title=tr("{title} (Kopie)", title=book.title),
            author=book.author,
            genre=book.genre,
            description=book.description,
            color=book.color,
            category_id=book.category_id,
            target_words=book.target_words,
            deadline=book.deadline,
            attributes=[AttributeData(a.name, a.value) for a in book.attributes],
            note_count=book.note_count,
            word_count=book.word_count,
        )

        src = self.book_path(book)
        if os.path.exists(src):
            shutil.copy2(src, self.book_path(copy))

        self.move_book(copy, copy.category_id, len(self.books_in(copy.category_id)))
        return copy

    def import_file(self, filename, category_id, title, note_count=0, word_count=0):

        """Copy an existing board file into the library as a new book."""
        book = self.new_book(category_id)
        book.title = title
        book.note_count = note_count
        book.word_count = word_count
        book.modified = _now()

        shutil.copy2(filename, self.book_path(book))
        self.add_book(book)
        return book

    def apply_meta(self, book, meta):
        """Buchinfos aus einem importierten Board ("book"-Eintrag) übernehmen."""

        if not isinstance(meta, dict):
            return

        for key in ("title", "author", "genre", "description", "color", "deadline"):
            if isinstance(meta.get(key), str) and meta[key].strip():
                setattr(book, key, meta[key])

        try:
            book.target_words = int(meta.get("target_words", book.target_words) or 0)
        except (TypeError, ValueError):
            pass

        attrs = meta.get("attributes")
        if isinstance(attrs, list):
            book.attributes = [
                AttributeData(str(a.get("name", "")), str(a.get("value", "")))
                for a in attrs if isinstance(a, dict)
            ]

        cat_name = str(meta.get("category", "")).strip().lower()
        if cat_name:
            for c in self.categories:
                if c.name.lower() == cat_name:
                    book.category_id = c.id
                    break

    # ------------------------------------------------ Statistik / Sitzung

    def update_stats(self, book, note_count, word_count):
        """Store note / word counts shown on the shelf."""
        book.note_count = note_count
        book.word_count = word_count
        book.modified = _now()

    def begin_session(self, book, words):
        """Remember the word count at the start of today (for 'Today +n')."""
        today = date.today().isoformat()
        if book.baseline_date != today:
            book.baseline_date = today
            book.baseline_words = words

    def today_delta(self, book, words):
        """Words added today (current - word count at the start of the day)."""
        if book.baseline_date != date.today().isoformat():
            return 0
        return words - book.baseline_words

    # ---------------------------------------------------------- Sicherung

    def backup_folder(self, book):
        """Folder with the backups of a book."""
        return os.path.join(self.backup_dir, book.id)

    def backup(self, book):
        """Vor dem Überschreiben eine Kopie ablegen (höchstens alle 5 Min.)."""

        src = self.book_path(book)
        if not os.path.exists(src):
            return None

        folder = self.backup_folder(book)
        os.makedirs(folder, exist_ok=True)

        existing = self.list_backups(book)
        if existing and time.time() - os.path.getmtime(existing[0]) < self.BACKUP_MIN_INTERVAL:
            return None

        name = datetime.now().strftime("%Y%m%d-%H%M%S") + ".json"
        dest = os.path.join(folder, name)
        shutil.copy2(src, dest)

        for old in self.list_backups(book)[self.BACKUP_KEEP:]:
            try:
                os.remove(old)
            except OSError:
                pass

        return dest

    def list_backups(self, book):
        """Backup files of a book, newest first."""
        folder = self.backup_folder(book)
        if not os.path.isdir(folder):
            return []
        files = [
            os.path.join(folder, f) for f in os.listdir(folder)
            if f.endswith(".json")
        ]
        return sorted(files, reverse=True)
