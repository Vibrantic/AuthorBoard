# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Attachments: files and images that belong to a note.

Design
------
* The *metadata* (:class:`models.AttachmentData`) is stored with the note.
* The *bytes* live in an :class:`AttachmentStore` (``id -> bytes``) that is
  shared by the whole main window.  On save the bytes are embedded in the
  notebook file (base64) so a book stays one self-contained ``.json`` file.
* Undo snapshots never contain the bytes, so they stay small.  Unreferenced
  blobs are only dropped from the *saved file*, never from memory, so Undo can
  always bring an attachment back.
"""

import mimetypes
import os
import re
import tempfile

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QImage

from models import AttachmentData

MAX_BYTES = 40 * 1024 * 1024        # refuse single files larger than 40 MB
_REF_RE = re.compile(r"attachment:([0-9A-Za-z\-]+)")


class AttachmentTooLarge(Exception):
    """Raised when a file exceeds MAX_BYTES."""


class AttachmentStore:
    """In-memory blob storage for attachment bytes."""

    def __init__(self):
        """Create an empty store."""
        self.blobs = {}              # id -> bytes
        self._images = {}            # id -> QImage cache
        self._tmpdir = None          # created lazily for "open with system app"

    # ------------------------------------------------------------- content

    def replace_all(self, blobs):
        """Replace the content (used when a notebook is loaded)."""
        self.blobs.clear()
        self.blobs.update(blobs)
        self._images.clear()

    def add_bytes(self, name, data, mime=None, inline=False):
        """Store ``data`` and return the new :class:`AttachmentData`."""
        if len(data) > MAX_BYTES:
            raise AttachmentTooLarge(name)
        att = AttachmentData(
            name=name,
            mime=mime or mimetypes.guess_type(name)[0] or "application/octet-stream",
            size=len(data),
            inline=inline,
        )
        self.blobs[att.id] = bytes(data)
        return att

    def add_file(self, path, inline=False):
        """Read a file from disk and store it."""
        size = os.path.getsize(path)
        if size > MAX_BYTES:
            raise AttachmentTooLarge(os.path.basename(path))
        with open(path, "rb") as f:
            return self.add_bytes(os.path.basename(path), f.read(), inline=inline)

    def get(self, att_id):
        """Bytes of an attachment, or None."""
        return self.blobs.get(att_id)

    def image(self, att_id):
        """Return the attachment as QImage (None if missing / not an image)."""
        if att_id in self._images:
            return self._images[att_id]
        data = self.blobs.get(att_id)
        img = QImage.fromData(data) if data else None
        if img is not None and img.isNull():
            img = None
        self._images[att_id] = img
        return img

    # ------------------------------------------------------------- opening

    def export_to_temp(self, att):
        """Write the attachment into a temp folder and return its path."""
        data = self.blobs.get(att.id)
        if data is None:
            return None
        if self._tmpdir is None:
            self._tmpdir = tempfile.mkdtemp(prefix="authorboard-")
        folder = os.path.join(self._tmpdir, att.id)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, att.name or att.id)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def open(self, att):
        """Open the attachment with the operating system's default program."""
        path = self.export_to_temp(att)
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return bool(path)

    # ------------------------------------------------------------ saving

    @staticmethod
    def referenced_ids(notes):
        """Ids of all attachments that a list of notes still refers to.

        A reference is either an entry in ``note.attachments`` or an inline
        ``<img src="attachment:ID">`` inside the note's rich text."""
        ids = set()
        for n in notes:
            ids.update(a.id for a in n.attachments)
            ids.update(_REF_RE.findall(n.rich or ""))
        return ids

    def subset(self, ids):
        """Blobs restricted to ``ids`` (what gets written to the file)."""
        return {k: v for k, v in self.blobs.items() if k in ids}


def human_size(n):
    """Format a byte count like ``1.4 MB``."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
