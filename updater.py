# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""In-app update checker and downloader.

Uses the GitHub Releases API (``/repos/<owner>/<repo>/releases/latest``)
to discover the newest release, its notes (``body``) and the platform
asset.  Downloading is asynchronous and writes through ``QSaveFile`` so a
crash never leaves a half-written zip.

The actual file replacement is done by a separate process
(``updater_main.py``) — see that module for the reason.
"""

import hashlib
import os
import sys

from PySide6.QtCore import (
    QObject, Signal, QUrl, QSaveFile, QIODevice, QDateTime, Qt,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from version import (
    __version__, GITHUB_OWNER, GITHUB_REPO,
    UPDATE_ASSET_WINDOWS, UPDATE_ASSET_LINUX, UPDATE_ASSET_MACOS,
)

API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


def _platform_asset_name(version: str) -> str:
    """The asset filename this platform expects for ``version``."""
    v = version.lstrip("v")
    if sys.platform == "win32":
        return UPDATE_ASSET_WINDOWS.format(version=v)
    if sys.platform == "darwin":
        return UPDATE_ASSET_MACOS.format(version=v)
    return UPDATE_ASSET_LINUX.format(version=v)


def _parse_version(tag: str):
    """'v1.2.2' -> (1, 2, 2).  Returns None for unparsable tags."""
    try:
        return tuple(int(p) for p in tag.lstrip("v").split(".")[:3])
    except (ValueError, AttributeError):
        return None


class ReleaseInfo:
    """The subset of the GitHub release JSON the app needs."""

    __slots__ = ("tag", "version", "body", "asset_url", "asset_name", "asset_size", "sha256")

    def __init__(self, tag, body, asset_url, asset_name, asset_size=0, sha256=""):
        self.tag = tag
        self.version = tag.lstrip("v")
        self.body = body or ""
        self.asset_url = asset_url
        self.asset_name = asset_name
        self.asset_size = asset_size
        self.sha256 = sha256


class UpdateChecker(QObject):
    """Async GitHub release check and asset download."""

    update_available = Signal(object)   # ReleaseInfo
    up_to_date = Signal()
    check_failed = Signal(str)

    download_progress = Signal(int, int)   # received, total (-1 if unknown)
    download_finished = Signal(str)        # local path to the downloaded file
    download_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._check_reply = None
        self._download_reply = None
        self._save_file = None
        self._sha256 = None

    # ------------------------------------------------------------- checking

    def check(self):
        """Fire a GET to the GitHub API.  Emits exactly one of the three signals."""
        if self._check_reply is not None:
            return  # a check is already in flight
        request = QNetworkRequest(QUrl(API_URL))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", f"AuthorBoard/{__version__}".encode())
        self._check_reply = self._manager.get(request)
        self._check_reply.finished.connect(self._on_check_finished)

    def _on_check_finished(self):
        reply = self._check_reply
        self._check_reply = None
        if reply is None:
            return
        reply.deleteLater()

        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.check_failed.emit(reply.errorString())
            return

        try:
            import json
            data = json.loads(bytes(reply.readAll()).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            self.check_failed.emit(f"Invalid JSON: {exc}")
            return

        tag = data.get("tag_name", "")
        remote = _parse_version(tag)
        local = _parse_version(__version__)
        if remote is None or local is None or remote <= local:
            self.up_to_date.emit()
            return

        asset_name = _platform_asset_name(tag)
        asset = None
        for a in data.get("assets", []):
            if a.get("name") == asset_name:
                asset = a
                break
        if asset is None:
            # Release exists but this platform has no build yet.
            self.check_failed.emit(
                f"Release {tag} has no build for this platform ({asset_name}).")
            return

        info = ReleaseInfo(
            tag=tag,
            body=data.get("body", ""),
            asset_url=asset["browser_download_url"],
            asset_name=asset["name"],
            asset_size=int(asset.get("size", 0) or 0),
        )
        self.update_available.emit(info)

    # ------------------------------------------------------------ downloading

    def download(self, info: ReleaseInfo, target_dir: str):
        """Download ``info.asset_url`` into ``target_dir/<asset_name>``."""
        if self._download_reply is not None:
            return
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, info.asset_name)
        self._save_file = QSaveFile(path)
        if not self._save_file.open(QIODevice.OpenModeFlag.WriteOnly):
            self.download_failed.emit(
                f"Cannot open {path}: {self._save_file.errorString()}")
            self._save_file = None
            return

        request = QNetworkRequest(QUrl(info.asset_url))
        request.setRawHeader(b"User-Agent", f"AuthorBoard/{__version__}".encode())
        self._download_reply = self._manager.get(request)
        self._download_reply.downloadProgress.connect(self.download_progress)
        self._download_reply.readyRead.connect(self._on_ready_read)
        self._download_reply.finished.connect(self._on_download_finished)

    def _on_ready_read(self):
        if self._download_reply is not None and self._save_file is not None:
            self._save_file.write(self._download_reply.readAll())

    def _on_download_finished(self):
        reply = self._download_reply
        self._download_reply = None
        if reply is None:
            return
        reply.deleteLater()

        save = self._save_file
        self._save_file = None
        if save is None:
            return

        if reply.error() != QNetworkReply.NetworkError.NoError:
            save.cancelWriting()
            self.download_failed.emit(reply.errorString())
            return

        if not save.commit():
            self.download_failed.emit(f"Commit failed: {save.errorString()}")
            return

        self.download_finished.emit(save.fileName())


# --------------------------------------------------------------------------
# Skip-until state (QSettings)
# --------------------------------------------------------------------------

SKIP_KEY = "updates/skip_until"
SKIPPED_VERSION_KEY = "updates/skipped_version"


def should_prompt(info: ReleaseInfo, qsettings) -> bool:
    """True when the user should be offered this update.

    A skip suppresses *this* version until ``skip_until``, but never
    suppresses a *newer* release — if 1.2.2 was skipped for a week and
    1.2.3 drops tomorrow, the user is offered 1.2.3 immediately.
    """
    skipped = qsettings.value(SKIPPED_VERSION_KEY, "")
    if skipped and skipped != info.version:
        return True  # different version — ignore the skip
    until = qsettings.value(SKIP_KEY, "")
    if not until:
        return True
    when = QDateTime.fromString(until, Qt.DateFormat.ISODate)
    return not when.isValid() or when <= QDateTime.currentDateTime()


def set_skip(info: ReleaseInfo, days: int, qsettings):
    """Record a skip.  ``days=0`` means 'until next start' (delete the keys)."""
    if days <= 0:
        qsettings.remove(SKIP_KEY)
        qsettings.remove(SKIPPED_VERSION_KEY)
    else:
        qsettings.setValue(SKIPPED_VERSION_KEY, info.version)
        qsettings.setValue(
            SKIP_KEY,
            QDateTime.currentDateTime().addDays(days).toString(Qt.DateFormat.ISODate),
        )
    qsettings.sync()