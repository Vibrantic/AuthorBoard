# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""
Einfache Übersetzung für AuthorBoard.

* Quellsprache ist Deutsch: Der deutsche Text im Code ist zugleich der Schlüssel.
* Übersetzungen liegen als JSON in  locales/<code>.json  ({"Deutscher Text": "Translation"}).
* Fehlt ein Eintrag (oder ist er leer), wird der deutsche Text angezeigt.

Neue Sprache hinzufügen:

    python i18n.py new fr "Français"      # legt locales/fr.json mit allen Schlüsseln an
    (Werte in locales/fr.json übersetzen, Programm neu starten – fertig.)

Nach Codeänderungen neue Texte ergänzen und Fehlendes anzeigen:

    python i18n.py update fr
    python i18n.py check fr
"""

import ast
import json
import os
import sys
from resource import resource_path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_DIR = resource_path("locales")
SOURCE_LANG = "de"

_current = SOURCE_LANG
_table = {}


def N_(text):
    """Markiert einen Text zur Übersetzung (ohne ihn sofort zu übersetzen)."""
    return text


def tr(text, **kwargs):
    """Text in der aktuellen Sprache; {platzhalter} werden mit kwargs gefüllt."""

    result = _table.get(text) or text

    if kwargs:
        try:
            return result.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text.format(**kwargs)

    return result


def _read(code):
    """Read ``locales/<code>.json`` (empty dict when missing)."""
    path = os.path.join(LOCALE_DIR, f"{code}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def available_languages():
    """dict Sprachcode -> Anzeigename (aus den Dateien in locales/)."""

    langs = {SOURCE_LANG: "Deutsch"}

    try:
        names = sorted(os.listdir(LOCALE_DIR))
    except OSError:
        names = []

    for fname in names:
        if fname.endswith(".json"):
            code = fname[:-5]
            langs[code] = _read(code).get("_name", code)

    return langs


def current_language():
    """Code of the active language."""
    return _current


def set_language(code):

    """Activate a language (falls back to German when unknown)."""
    global _current, _table

    if code not in available_languages():
        code = SOURCE_LANG

    _current = code
    _table = {} if code == SOURCE_LANG else {
        k: v for k, v in _read(code).items()
        if not k.startswith("_") and isinstance(v, str)
    }


# ---------------------------------------------------- Werkzeuge (CLI)

def extract_keys():
    """Alle Texte aus tr("…") / N_("…") im Quellcode (in Reihenfolge)."""

    keys = []
    seen = set()

    for fname in sorted(os.listdir(BASE_DIR)):
        if not fname.endswith(".py") or fname == "i18n.py":
            continue

        with open(os.path.join(BASE_DIR, fname), "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("tr", "N_")
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                text = node.args[0].value
                if text not in seen:
                    seen.add(text)
                    keys.append(text)

    return keys


def _write(code, data):
    """Write a locale file."""
    os.makedirs(LOCALE_DIR, exist_ok=True)
    with open(os.path.join(LOCALE_DIR, f"{code}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _cli(argv):
    """Command line interface: ``new`` / ``update`` / ``check``.

    Multiple language codes can be passed in one call::

        python i18n.py check fr de es
        python i18n.py update fr de es
        python i18n.py new fr de es

    ``new`` optionally takes a display name for each language, but only
    when exactly one code is given (it applies to that single language)::

        python i18n.py new fr "Français"
    """
    if len(argv) < 3 or argv[1] not in ("new", "update", "check"):
        print(__doc__)
        return 1

    cmd = argv[1]
    codes = argv[2:]
    # Only "new" can take a display name, and only when there is exactly
    # one language (otherwise the extra arg would be ambiguous — treat it
    # as another language code and let the caller sort it out).
    display_name = None
    if cmd == "new" and len(codes) == 2:
        second = codes[1]
        if not (second.isalpha() and len(second) <= 5 and second.islower()):
            display_name = second
            codes = [codes[0]]

    keys = extract_keys()
    exit_code = 0

    for code in codes:
        data = _read(code)

        if cmd == "new":
            if not data:
                data = {"_name": display_name if display_name and code == codes[0]
                        else code}

        if cmd in ("new", "update"):
            added = 0
            empty = 0
            for k in keys:
                if k not in data:
                    data[k] = ""
                    added += 1
                elif not data.get(k):
                    empty += 1
            _write(code, data)
            msg = f"locales/{code}.json: {added} neue Schlüssel, {len(keys)} insgesamt."
            if empty:
                msg += f"  ·  {empty} leer (noch zu übersetzen)."
            print(msg)

        if cmd == "check":
            missing = [k for k in keys if not data.get(k)]
            print(f"\n=== {code} ===")
            print(f"{len(missing)} von {len(keys)} Texten fehlen in '{code}':")
            for k in missing:
                print("  ", k.replace("\n", "\\n"))
            if missing:
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
