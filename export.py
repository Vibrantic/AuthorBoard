# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Markdown outline export of a whole board (notes grouped by type).
"""

from i18n import tr
from models import STATUS_INFO, count_words, note_sort_key


def build_markdown(notes, note_types, title="AuthorBoard"):
    """Gliederung des Boards als Markdown. notes: Liste von NoteItem."""

    groups = {}
    for n in notes:
        groups.setdefault(n.model.note_type, []).append(n)

    order = list(note_types.keys()) + [k for k in groups if k not in note_types]

    words = sum(count_words(n.model.content) for n in notes)

    lines = [f"# {title}", "", "*" + tr("{n} Notizen · {words} Wörter", n=len(notes), words=words) + "*", ""]

    for key in order:
        items = groups.get(key)
        if not items:
            continue

        info = note_types.get(key)
        lines += [f"## {info.label if info else key}", ""]

        for note in sorted(items, key=lambda n: note_sort_key(n.model)):
            m = note.model

            head = f"### {m.title or tr('Ohne Titel')}"
            if m.status in STATUS_INFO:
                head += f"  _[{tr(STATUS_INFO[m.status][0])}]_"
            lines += [head, ""]

            for a in m.attributes:
                if a.value.strip():
                    name = a.name or tr("Attribut")
                    lines.append(f"- **{name}:** {a.value.strip()}")

            if m.tags:
                lines.append("- **" + tr("Tags") + ":** " + " ".join(f"#{t}" for t in m.tags))

            links = note.links()
            if links:
                parts = [
                    f"{o.model.title or tr('Ohne Titel')}"
                    + (f" ({lab})" if lab else "")
                    for o, lab in links
                ]
                lines.append("- **" + tr("Verbunden mit") + ":** " + ", ".join(parts))

            lines.append("")

            if m.content.strip():
                lines += [m.content.strip(), ""]

    return "\n".join(lines)
