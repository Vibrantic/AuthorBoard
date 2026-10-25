# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Reading and writing notebook files (JSON).

``to_dict`` / ``from_dict`` convert between ``ProjectData`` and a plain dict
(also used for undo snapshots).  ``save`` writes atomically.  Older file
versions are read with defaults for the fields they lack.
"""

import base64
import json
import os

from models import (
    ProjectData,
    NoteData,
    NoteTypeData,
    PinData,
    ConnectionData,
    AttributeData,
    AttachmentData,
    CommentData,
    BUILTIN_NOTE_TYPES,
    DEFAULT_NOTE_COLOR,
    DEFAULT_PIN_COLOR,
    DEFAULT_THREAD_COLOR,
    GroupData,
)

FORMAT_VERSION = 4
_OLD_DEFAULT_NOTE_COLOR = "#2d2d2d"


class Storage:

    # ------------------------------------------------ dict <-> Projekt

    """Static helpers to (de)serialise ``ProjectData``."""
    @staticmethod
    def to_dict(project: ProjectData, with_blobs: bool = True) -> dict:
        """Serialise a project. Attachment bytes are included only when
        ``with_blobs`` is True (undo snapshots leave them out to stay small)."""

        data = {
            "groups": [Storage.group_to_dict(g) for g in project.groups],
            "version": FORMAT_VERSION,
            "custom_types": [
                {
                    "key": t.key,
                    "label": t.label,
                    "color": t.color,
                    "attributes": list(t.attributes),
                }
                for t in project.custom_types
            ],
            "known_tags": list(project.known_tags),
            "notes": [],
            "connections": [],
        }

        if with_blobs:
            data["attachment_data"] = {
                k: base64.b64encode(v).decode("ascii")
                for k, v in project.blobs.items()
            }

        for note in project.notes:
            data["notes"].append({
                "id": note.id,
                "title": note.title,
                "content": note.content,
                "x": note.x,
                "y": note.y,
                "width": note.width,
                "height": note.height,
                "color": note.color,
                "note_type": note.note_type,
                "status": note.status,
                "locked": note.locked,
                "rich": note.rich,
                "tags": list(note.tags),
                "attributes": [
                    {"name": a.name, "value": a.value}
                    for a in note.attributes
                ],
                "pins": [
                    {"id": p.id, "x": p.x, "y": p.y, "color": p.color,
                     "locked": p.locked}
                    for p in note.pins
                ],
                "attachments": [
                    {"id": a.id, "name": a.name, "mime": a.mime,
                     "size": a.size, "inline": a.inline}
                    for a in note.attachments
                ],
                "comments": [
                    {"id": c.id, "text": c.text, "quote": c.quote,
                     "created": c.created}
                    for c in note.comments
                ],
            })

        for c in project.connections:
            data["connections"].append({
                "id": c.id,
                "start_pin_id": c.start_pin_id,
                "end_pin_id": c.end_pin_id,
                "color": c.color,
                "label": c.label,
            })

        return data

    @staticmethod
    def from_dict(data: dict) -> ProjectData:

        """Build a ``ProjectData`` from a dict (tolerates missing fields of old versions)."""
        project = ProjectData()

        for t in data.get("custom_types", []):
            project.custom_types.append(NoteTypeData(
                key=t["key"],
                label=t.get("label", t["key"]),
                color=t.get("color", DEFAULT_NOTE_COLOR),
                attributes=list(t.get("attributes", [])),
            ))

        project.known_tags = list(data.get("known_tags", []))

        for key, b64 in data.get("attachment_data", {}).items():
            try:
                project.blobs[key] = base64.b64decode(b64)
            except (ValueError, TypeError):
                pass

        builtin = {t.key: t for t in BUILTIN_NOTE_TYPES}

        for nd in data.get("notes", []):

            note_type = nd.get("note_type", "note")

            color = nd.get("color") or ""
            if not color or color.lower() == _OLD_DEFAULT_NOTE_COLOR:
                # Dateien der alten Version: Typfarbe verwenden
                color = (
                    builtin[note_type].color
                    if note_type in builtin
                    else DEFAULT_NOTE_COLOR
                )

            note = NoteData(
                id=nd["id"],
                title=nd.get("title", ""),
                content=nd.get("content", ""),
                x=nd.get("x", 0.0),
                y=nd.get("y", 0.0),
                width=nd.get("width", 260),
                height=nd.get("height", 190),
                color=color,
                note_type=note_type,
                status=nd.get("status", ""),
                locked=bool(nd.get("locked", False)),
                rich=nd.get("rich", ""),
                tags=list(nd.get("tags", [])),
                attributes=[
                    AttributeData(a.get("name", ""), a.get("value", ""))
                    for a in nd.get("attributes", [])
                ],
            )

            for pd in nd.get("pins", []):
                note.pins.append(PinData(
                    id=pd["id"],
                    x=pd.get("x", 20.0),
                    y=pd.get("y", 20.0),
                    color=pd.get("color", DEFAULT_PIN_COLOR),
                    locked=bool(pd.get("locked", False)),
                ))

            for ad in nd.get("attachments", []):
                note.attachments.append(AttachmentData(
                    id=ad["id"], name=ad.get("name", ""), mime=ad.get("mime", ""),
                    size=int(ad.get("size", 0) or 0), inline=bool(ad.get("inline", False)),
                ))

            for cd in nd.get("comments", []):
                note.comments.append(CommentData(
                    id=cd["id"], text=cd.get("text", ""), quote=cd.get("quote", ""),
                    created=cd.get("created", ""),
                ))

            project.notes.append(note)

        for cd in data.get("connections", []):
            project.connections.append(ConnectionData(
                id=cd["id"],
                start_pin_id=cd["start_pin_id"],
                end_pin_id=cd["end_pin_id"],
                color=cd.get("color", DEFAULT_THREAD_COLOR),
                label=cd.get("label", ""),
            ))

        project.groups = [Storage.group_from_dict(g) for g in data.get("groups", [])]

        return project

    # ------------------------------------------------------- Dateien

    @staticmethod
    def save(project: ProjectData, filename: str):

        """Write a notebook file atomically (temp file + rename)."""
        data = Storage.to_dict(project)

        # Erst in temporäre Datei schreiben, dann ersetzen:
        # bei einem Fehler bleibt die alte Datei intakt.
        tmp = filename + ".tmp"

        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

        os.replace(tmp, filename)

    @staticmethod
    def load(filename: str) -> ProjectData:

        """Read a notebook file."""
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)

        return Storage.from_dict(data)

    @staticmethod
    def note_to_dict(note) -> dict:
        """Serialise a single NoteData to a dict (no blobs)."""
        return {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "x": note.x,
            "y": note.y,
            "width": note.width,
            "height": note.height,
            "color": note.color,
            "note_type": note.note_type,
            "status": note.status,
            "locked": note.locked,
            "rich": note.rich,
            "tags": list(note.tags),
            "attributes": [
                {"name": a.name, "value": a.value} for a in note.attributes
            ],
            "pins": [
                {"id": p.id, "x": p.x, "y": p.y, "color": p.color,
                 "locked": p.locked} for p in note.pins
            ],
            "attachments": [
                {"id": a.id, "name": a.name, "mime": a.mime,
                 "size": a.size, "inline": a.inline} for a in note.attachments
            ],
            "comments": [
                {"id": c.id, "text": c.text, "quote": c.quote,
                 "created": c.created} for c in note.comments
            ],
        }

    @staticmethod
    def snapshot_parts(project, note_cache=None):
        """Return ``(notes_json, connections_json, meta_json)`` for a Snapshot.

        ``note_cache`` maps note id -> (json_str, signature) from the previous
        snapshot; unchanged notes reuse the cached string (structural sharing).
        """
        import json as _json
        note_cache = note_cache or {}
        notes_json = {}
        for note in project.notes:
            data = Storage.note_to_dict(note)
            sig = _json.dumps(data, sort_keys=True, ensure_ascii=False)
            cached = note_cache.get(note.id)
            if cached is not None and cached[1] == sig:
                notes_json[note.id] = cached[0]
            else:
                notes_json[note.id] = sig
        connections_json = _json.dumps(
            [{"id": c.id, "start_pin_id": c.start_pin_id,
              "end_pin_id": c.end_pin_id, "color": c.color, "label": c.label}
             for c in project.connections],
            sort_keys=True, ensure_ascii=False,
        )
        meta_json = _json.dumps({
            "version": FORMAT_VERSION,
            "custom_types": [
                {"key": t.key, "label": t.label, "color": t.color,
                 "attributes": list(t.attributes)}
                for t in project.custom_types
            ],
            "known_tags": list(project.known_tags),
            "groups": [Storage.group_to_dict(g) for g in project.groups],
        }, sort_keys=True, ensure_ascii=False)
        return notes_json, connections_json, meta_json

    @staticmethod
    def group_to_dict(g) -> dict:
        """Serialise a GroupData."""
        return {"id": g.id, "title": g.title, "x": g.x, "y": g.y,
                "width": g.width, "height": g.height,
                "color": g.color, "locked": g.locked}

    @staticmethod
    def group_from_dict(d: dict):
        """Build a GroupData (tolerates missing fields)."""
        return GroupData(
            id=d["id"], title=d.get("title", ""),
            x=float(d.get("x", 0.0)), y=float(d.get("y", 0.0)),
            width=float(d.get("width", 400.0)), height=float(d.get("height", 300.0)),
            color=d.get("color", "#4da6ff"), locked=bool(d.get("locked", False)))
