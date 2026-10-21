# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""HTML statistics report for the open notebook (View -> Statistics).
"""

from html import escape

from i18n import tr
from models import STATUS_INFO, count_words


def build_stats_html(notes, note_types, connection_count, book=None, today=None):
    """Statistik des Boards als HTML. notes: Liste von NoteItem."""

    total_words = sum(count_words(n.model.content) for n in notes)

    def table(rows, head=None):
        out = ['<table cellspacing="0" cellpadding="5" width="100%">']
        if head:
            out.append("<tr>" + "".join(
                f'<th align="{"left" if i == 0 else "right"}" '
                f'style="color:#8d8e9a">{escape(h)}</th>'
                for i, h in enumerate(head)) + "</tr>")
        for r in rows:
            out.append("<tr>" + "".join(
                f'<td align="{"left" if i == 0 else "right"}">{c}</td>'
                for i, c in enumerate(r)) + "</tr>")
        out.append("</table>")
        return "".join(out)

    def h(text):
        return f'<h3 style="color:#6c9cff;margin-top:18px">{escape(text)}</h3>'

    parts = []

    # Überblick
    rows = [
        (tr("Notizen"), str(len(notes))),
        (tr("Wörter (Inhalt)"), f"{total_words:,}".replace(",", ".")),
        (tr("Fäden"), str(connection_count)),
    ]
    if notes:
        rows.append((tr("Ø Wörter pro Notiz"), str(total_words // len(notes))))
    parts.append(h(tr("Überblick")) + table(rows))

    # Fortschritt
    if book is not None and book.target_words:
        pct = min(100, int(total_words * 100 / book.target_words))
        rest = max(0, book.target_words - total_words)
        rows = [
            (tr("Wortziel"), f"{book.target_words:,}".replace(",", ".")),
            (tr("Fortschritt"), f"{pct} %"),
            (tr("Noch zu schreiben"), f"{rest:,}".replace(",", ".")),
        ]
        if book.deadline:
            rows.append((tr("Abgabetermin"), escape(book.deadline)))
        if today is not None:
            rows.append((tr("Heute geschrieben"), f"{today:+d}"))
        parts.append(h(tr("Schreibziel")) + table(rows))
    elif today is not None:
        parts.append(h(tr("Heute")) + table([(tr("Heute geschrieben"), f"{today:+d}")]))

    # Nach Notizart
    by_type = {}
    for n in notes:
        c, w = by_type.get(n.model.note_type, (0, 0))
        by_type[n.model.note_type] = (c + 1, w + count_words(n.model.content))

    rows = []
    for key, (c, w) in sorted(by_type.items(), key=lambda kv: -kv[1][0]):
        info = note_types.get(key)
        color = info.color if info else "#888888"
        label = info.label if info else key
        rows.append((
            f'<span style="color:{color}">■</span> {escape(label)}',
            str(c), str(w),
        ))
    if rows:
        parts.append(h(tr("Nach Notizart")) + table(rows, (tr("Art"), tr("Notizen"), tr("Wörter"))))

    # Status
    counts = {}
    for n in notes:
        counts[n.model.status] = counts.get(n.model.status, 0) + 1
    rows = []
    for key, (label, col) in STATUS_INFO.items():
        if counts.get(key):
            rows.append((f'<span style="color:{col}">●</span> {tr(label)}',
                         str(counts[key])))
    if counts.get(""):
        rows.append((tr("Ohne Status"), str(counts[""])))
    if rows:
        parts.append(h(tr("Status")) + table(rows))

    # Tags
    tags = {}
    for n in notes:
        for t in n.model.tags:
            tags[t.lower()] = tags.get(t.lower(), 0) + 1
    rows = [(f"#{escape(t)}", str(c))
            for t, c in sorted(tags.items(), key=lambda kv: -kv[1])[:10]]
    if rows:
        parts.append(h(tr("Häufigste Tags")) + table(rows))

    # Längste Notizen
    longest = sorted(notes, key=lambda n: -count_words(n.model.content))[:5]
    rows = [(escape(n.model.title or tr("Ohne Titel")),
             str(count_words(n.model.content)))
            for n in longest if n.model.content.strip()]
    if rows:
        parts.append(h(tr("Längste Notizen")) + table(rows))

    # Am stärksten vernetzt
    linked = sorted(notes, key=lambda n: -len(n.links()))[:5]
    rows = [(escape(n.model.title or tr("Ohne Titel")), str(len(n.links())))
            for n in linked if n.links()]
    if rows:
        parts.append(h(tr("Am stärksten vernetzt")) + table(rows))

    return "".join(parts)
