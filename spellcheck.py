# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Spell checking for English and German.

The heavy lifting is done by the optional ``pyspellchecker`` package (pure
Python, dictionaries are bundled).  If it is not installed the editor still
works, spell checking is simply unavailable.

Words are *not* flagged when they are

* in the user dictionary (settings ``user_words``),
* in the book vocabulary (note titles, tags - so names like "Mira" are fine),
* ignored for this session ("Ignore" in the context menu).
"""

import re

from i18n import current_language
from settings import settings

# Unicode letters, optionally joined by an apostrophe ("don't", "l'été").
WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)

LANGUAGES = {"en": "English", "de": "Deutsch"}


class SpellEngine:
    """Wraps pyspellchecker with caching, custom words and language choice."""

    def __init__(self):
        """Create the engine (dictionaries are loaded lazily)."""
        self._checkers = {}
        self._cache = {}
        self.book_words = set()
        self.ignored = set()
        # Cached lowercase user-word set (Optimization.md 2.4)
        self._user_words_set = None
        self._user_words_snapshot = None

    @staticmethod
    def available():
        """True when pyspellchecker can be imported."""
        try:
            import spellchecker  # noqa: F401
            return True
        except ImportError:
            return False

    def language(self):
        if not settings.get("spell_enabled") or not self.available():
            return None

        lang = settings.get("spell_language")
        ui = current_language()

        if lang in LANGUAGES:
            # If the stored language is the UI language, use it — that's
            # almost certainly a follow-the-UI choice.  If it differs from
            # the UI language, respect it as an explicit choice.
            return lang

        # "auto" or unknown → follow the UI language.
        return ui if ui in LANGUAGES else "en"

    def _checker(self, lang):
        """Create the checker for a language on first use (loading takes a moment).

        If the checker cannot be constructed (e.g. its dictionary was not
        bundled), remember the failure and return ``None``; callers treat
        that as "spell checking unavailable".
        """
        if lang in self._checkers:
            return self._checkers[lang]
        try:
            from spellchecker import SpellChecker
            self._checkers[lang] = SpellChecker(language=lang)
        except Exception:
            self._checkers[lang] = None
        return self._checkers[lang]

    def _user_words(self):
        """Return the cached lowercase set of user words."""
        words = settings.get("user_words") or []
        # Cheap change detection: length + first/last item
        sig = (len(words), words[0] if words else None, words[-1] if words else None)
        if self._user_words_set is None or self._user_words_snapshot != sig:
            self._user_words_set = {w.lower() for w in words}
            self._user_words_snapshot = sig
        return self._user_words_set

    def is_misspelled(self, word):
        """True when ``word`` is unknown in the active language."""
        lang = self.language()
        if lang is None:
            return False

        w = word.lower().replace("’", "'")
        if len(w) < 2 or w in self.ignored or w in self.book_words:
            return False
        if w in self._user_words():
            return False

        checker = self._checker(lang)
        if checker is None:                  # dictionary missing → do not flag
            return False

        key = (lang, w)
        if key not in self._cache:
            base = w[:-2] if w.endswith("'s") else w
            self._cache[key] = not checker.known([base])
        return self._cache[key]

    def suggestions(self, word, limit=6):
        """Best corrections for ``word`` (most frequent first)."""
        lang = self.language()
        if lang is None:
            return []
        checker = self._checker(lang)
        if checker is None:
            return []
        cands = checker.candidates(word.lower()) or set()
        ranked = sorted(cands, key=lambda c: -checker.word_frequency[c])
        out = []
        for c in ranked[:limit]:
            # keep the capitalisation style of the original word
            if word.isupper() and len(word) > 1:
                c = c.upper()
            elif word[:1].isupper():
                c = c[:1].upper() + c[1:]
            out.append(c)
        return out

    # add_to_dictionary / remove_from_dictionary: also clear the cache of the set
    def add_to_dictionary(self, word):
        words = list(settings.get("user_words"))
        if word.lower() not in {w.lower() for w in words}:
            words.append(word)
            settings.set("user_words", words)
        self._user_words_set = None
        self._cache.clear()

    def remove_from_dictionary(self, word):
        words = [w for w in settings.get("user_words") if w != word]
        settings.set("user_words", words)
        self._user_words_set = None
        self._cache.clear()

    def set_book_words(self, words):
        """Replace the book vocabulary (note titles, tags)."""
        vocab = set()
        for text in words:
            for m in WORD_RE.finditer(text):
                vocab.add(m.group().lower())
        if vocab != self.book_words:
            self.book_words = vocab
            self._cache.clear()

    def ignore(self, word):
        """Ignore a word until the program is closed."""
        self.ignored.add(word.lower())

    def clear_cache(self):
        """Forget cached results (after a setting change)."""
        self._cache.clear()

# Shared engine instance
engine = SpellEngine()
