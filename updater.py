# AuthorBoard - notebooks for authors
# SPDX-License-Identifier: GPL-3.0-or-later
"""In-app update checker and downloader."""

import json
import os
import re
import shutil
import subprocess
import sys
import time

from PySide6.QtCore import (
    QObject, Signal, QUrl, QSaveFile, QIODevice, QDateTime, Qt, QTimer,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from version import (
    __version__, GITHUB_OWNER, GITHUB_REPO,
    UPDATE_ASSET_WINDOWS, UPDATE_ASSET_LINUX, UPDATE_ASSET_MACOS,
)

API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

_CURL_STALL_SECONDS = 30
_NET_STALL_SECONDS = 60


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


def _find_curl() -> str | None:
    """Return a usable ``curl`` executable path, or None."""
    exe = shutil.which("curl")
    if exe:
        return exe
    if sys.platform == "win32":
        candidate = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                 "System32", "curl.exe")
        if os.path.isfile(candidate):
            return candidate
    return None


class ReleaseInfo:
    """The subset of the GitHub release JSON the app needs."""

    __slots__ = ("tag", "version", "body", "asset_url", "asset_name", "asset_size")

    def __init__(self, tag, body, asset_url, asset_name, asset_size=0):
        self.tag = tag
        self.version = tag.lstrip("v")
        self.body = body or ""
        self.asset_url = asset_url
        self.asset_name = asset_name
        self.asset_size = asset_size


class UpdateChecker(QObject):
    """Async GitHub release check and asset download."""

    update_available = Signal(object)
    up_to_date = Signal()
    check_failed = Signal(str)

    download_progress = Signal(int, int)
    download_finished = Signal(str)
    download_failed = Signal(str)

    log = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._check_reply = None
        self._download_reply = None
        self._save_file = None
        self._user_cancelled = False
        self._write_error = ""
        self._expected_size = 0

        self._curl_proc: subprocess.Popen | None = None
        self._curl_stop: bool = False
        self._curl_poll: QTimer | None = None
        self._curl_path: str = ""
        self._stall_timer: QTimer | None = None

    def _log(self, message: str):
        print(f"[updater] {message}", file=sys.stderr, flush=True)
        self.log.emit(message)

    def check(self):
        if self._check_reply is not None:
            return
        self._log(f"GET {API_URL}")
        request = QNetworkRequest(QUrl(API_URL))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", f"AuthorBoard/{__version__}".encode())
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        self._check_reply = self._manager.get(request)
        self._check_reply.finished.connect(self._on_check_finished)

    def _on_check_finished(self):
        reply = self._check_reply
        self._check_reply = None
        if reply is None:
            return
        try:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            self._log(f"check finished: error={reply.error()} status={status} "
                      f"bytes={reply.bytesAvailable()}")
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.check_failed.emit(
                    f"{reply.errorString()} (error code {int(reply.error())})")
                return
            try:
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                self.check_failed.emit(f"Invalid JSON: {exc}")
                return

            tag = data.get("tag_name", "")
            self._log(f"latest release tag: {tag!r}")
            remote = _parse_version(tag)
            local = _parse_version(__version__)
            self._log(f"version compare: remote={remote} local={local}")
            if remote is None or local is None or remote <= local:
                self.up_to_date.emit()
                return

            asset_name = _platform_asset_name(tag)
            self._log(f"looking for asset: {asset_name}")
            asset = None
            for a in data.get("assets", []):
                if a.get("name") == asset_name:
                    asset = a
                    break
            if asset is None:
                available = [a.get("name") for a in data.get("assets", [])]
                self._log(f"no matching asset; available: {available}")
                self.check_failed.emit(
                    f"Release {tag} has no build for this platform "
                    f"(looked for {asset_name}).")
                return

            info = ReleaseInfo(
                tag=tag,
                body=data.get("body", ""),
                asset_url=asset["browser_download_url"],
                asset_name=asset["name"],
                asset_size=int(asset.get("size", 0) or 0),
            )
            self._log(f"asset selected: {info.asset_name} "
                      f"({info.asset_size} bytes) at {info.asset_url}")
            self.update_available.emit(info)
        finally:
            reply.deleteLater()

    def download(self, info: ReleaseInfo, target_dir: str):
        if self._download_reply is not None or self._curl_proc is not None:
            self._log("download already in progress; ignoring request")
            return

        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError as exc:
            self.download_failed.emit(f"Cannot create {target_dir}: {exc}")
            return

        self._expected_size = info.asset_size
        self._user_cancelled = False
        self._write_error = ""

        curl = _find_curl()
        if curl is not None:
            self._log(f"using curl at {curl}")
            self._download_with_curl(curl, info, target_dir)
            return

        self._log("curl not found; falling back to QNetworkAccessManager")
        self._download_with_network(info, target_dir)

    def _download_with_curl(self, curl: str, info: ReleaseInfo, target_dir: str):
        path = os.path.join(target_dir, info.asset_name)
        self._curl_path = path
        self._curl_stop = False

        args = [
            curl,
            "--location",
            "--fail",
            "--silent",
            "--show-error",
            # We removed --progress-bar because Python can't read \r on Windows.
            "--user-agent", f"AuthorBoard/{__version__}",
            "--output", path,
            info.asset_url,
        ]
        self._log(f"curl {' '.join(args)}")

        creationflags = 0
        if sys.platform == "win32":
            creationflags = 0x08000000  # CREATE_NO_WINDOW

        try:
            self._curl_proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError as exc:
            self._curl_proc = None
            self.download_failed.emit(f"Cannot start curl: {exc}")
            return

        self._curl_poll = QTimer(self)
        self._curl_poll.setInterval(100)  # Check every 100ms
        self._curl_poll.timeout.connect(self._poll_curl)
        self._curl_poll.start()

        self.download_progress.emit(0, info.asset_size)
        self._log(f"target file: {path}")
        self._log(f"expected size: {info.asset_size} bytes")

    def _poll_curl(self):
        if self._curl_proc is None:
            return

        # --- THE FIX: Read the file size directly from disk instead of stdout ---
        try:
            if os.path.exists(self._curl_path):
                received = os.path.getsize(self._curl_path)
                self.download_progress.emit(received, self._expected_size)
        except OSError:
            pass

        # Check if curl has finished
        code = self._curl_proc.poll()
        if code is not None:
            self._finish_curl(code)

    def _finish_curl(self, code: int):
        if self._curl_poll is not None:
            self._curl_poll.stop()
            self._curl_poll = None
        self._curl_proc = None
        self._log(f"curl exited with code {code}")

        if self._user_cancelled:
            self._cleanup_curl_file()
            self._log("download cancelled by user")
            return

        if code != 0:
            self._cleanup_curl_file()
            self.download_failed.emit(
                f"curl exited with code {code}. "
                f"Check that the file can be downloaded in a browser.")
            return

        try:
            actual = os.path.getsize(self._curl_path)
        except OSError:
            actual = 0
        if self._expected_size > 0 and actual != self._expected_size:
            self._cleanup_curl_file()
            self.download_failed.emit(
                f"Incomplete download ({actual} of "
                f"{self._expected_size} bytes)")
            return

        # Final 100% update
        self.download_progress.emit(self._expected_size or actual,
                                    self._expected_size or actual)
        self._log(f"download complete: {self._curl_path} ({actual} bytes)")
        self.download_finished.emit(self._curl_path)

    def _cleanup_curl_file(self):
        try:
            if os.path.exists(self._curl_path):
                os.remove(self._curl_path)
        except OSError:
            pass

    def _download_with_network(self, info: ReleaseInfo, target_dir: str):
        path = os.path.join(target_dir, info.asset_name)
        self._save_file = QSaveFile(path)
        if not self._save_file.open(QIODevice.OpenModeFlag.WriteOnly):
            self.download_failed.emit(
                f"Cannot open {path}: {self._save_file.errorString()}")
            self._save_file = None
            return

        self._log(f"download start: {info.asset_url}")
        self._log(f"target file: {path}")
        self._log(f"expected size: {info.asset_size} bytes")

        request = QNetworkRequest(QUrl(info.asset_url))
        request.setRawHeader(b"User-Agent", f"AuthorBoard/{__version__}".encode())
        request.setRawHeader(b"Connection", b"close")
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setAttribute(
            QNetworkRequest.Attribute.Http2AllowedAttribute, False)
        request.setTransferTimeout(_NET_STALL_SECONDS * 1000)

        self._download_reply = self._manager.get(request)

        self._stall_timer = QTimer(self)
        self._stall_timer.setSingleShot(True)
        self._stall_timer.setInterval(_NET_STALL_SECONDS * 1000)
        self._stall_timer.timeout.connect(self._on_stall)
        self._stall_timer.start()

        self._download_reply.downloadProgress.connect(self.download_progress)
        self._download_reply.readyRead.connect(self._on_ready_read)
        self._download_reply.finished.connect(self._on_download_finished)
        self._download_reply.readyRead.connect(self._stall_timer.start)
        self._download_reply.metaDataChanged.connect(self._stall_timer.start)
        self._download_reply.redirected.connect(
            lambda url: self._log(f"redirected to: {url.toString()}"))
        self._download_reply.metaDataChanged.connect(
            lambda: self._log(
                f"response headers: status="
                f"{self._download_reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)} "
                f"content-length="
                f"{self._download_reply.header(QNetworkRequest.KnownHeaders.ContentLengthHeader)}"))

    def _on_ready_read(self):
        reply, save = self._download_reply, self._save_file
        if reply is None or save is None:
            return
        data = reply.readAll()
        if data.size() and save.write(data) != data.size():
            self._write_error = save.errorString() or "write failed"
            self._log(f"write error: {self._write_error}")
            reply.abort()

    def _on_stall(self):
        if self._download_reply is not None:
            r = self._download_reply
            self._log(
                f"stall: error={r.error()} "
                f"({int(r.error())}) "
                f"isRunning={r.isRunning()} "
                f"isFinished={r.isFinished()} "
                f"bytesAvail={r.bytesAvailable()} "
                f"status={r.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)}")
            r.abort()

    def _on_download_finished(self):
        reply = self._download_reply
        if self._stall_timer is not None:
            self._stall_timer.stop()
            self._stall_timer = None
        self._download_reply = None
        if reply is None:
            return
        try:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            self._log(f"reply finished: error={reply.error()} "
                      f"({int(reply.error())}) status={status} "
                      f"bytes_received={reply.bytesAvailable()}")
        except Exception:
            pass

        save, self._save_file = self._save_file, None
        if save is None:
            try:
                reply.deleteLater()
            except Exception:
                pass
            return

        def fail(msg):
            save.cancelWriting()
            try:
                reply.deleteLater()
            except Exception:
                pass
            self._log(f"download failed: {msg}")
            self.download_failed.emit(msg)

        if self._user_cancelled:
            save.cancelWriting()
            try:
                reply.deleteLater()
            except Exception:
                pass
            return

        if self._write_error:
            return fail(f"Cannot write update file: {self._write_error}")

        if reply.error() != QNetworkReply.NetworkError.NoError:
            return fail(reply.errorString() or
                        f"network error {int(reply.error())}")

        if status is not None and int(status) != 200:
            return fail(f"Server returned HTTP {status}")

        actual = save.size()
        if self._expected_size and actual != self._expected_size:
            return fail(f"Incomplete download ({actual} of "
                        f"{self._expected_size} bytes)")

        if not save.commit():
            return fail(f"Commit failed: {save.errorString()}")

        self._log(f"download complete: {save.fileName()} ({actual} bytes)")
        try:
            reply.deleteLater()
        except Exception:
            pass
        self.download_finished.emit(save.fileName())

    def cancel_download(self):
        self._log("user cancelled download")
        self._user_cancelled = True

        if self._curl_proc is not None:
            self._curl_stop = True
            try:
                self._curl_proc.terminate()
                self._curl_proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self._curl_proc.kill()
                except OSError:
                    pass
            if self._curl_poll is not None:
                self._curl_poll.stop()
                self._curl_poll = None
            self._curl_proc = None
            self._cleanup_curl_file()
            return

        if self._download_reply is not None:
            self._download_reply.abort()


SKIP_KEY = "updates/skip_until"
SKIPPED_VERSION_KEY = "updates/skipped_version"


def should_prompt(info: ReleaseInfo, qsettings) -> bool:
    skipped = qsettings.value(SKIPPED_VERSION_KEY, "")
    if skipped and skipped != info.version:
        return True
    until = qsettings.value(SKIP_KEY, "")
    if not until:
        return True
    when = QDateTime.fromString(until, Qt.DateFormat.ISODate)
    return not when.isValid() or when <= QDateTime.currentDateTime()


def set_skip(info: ReleaseInfo, days: int, qsettings):
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