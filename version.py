# AuthorBoard - notebooks for authors
# Copyright (C) 2026 The AuthorBoard authors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is distributed WITHOUT ANY WARRANTY; see the file LICENSE.
"""Version and project metadata shown in the About dialog and the docs."""

# version.py (additions)
__version__ = "1.2.5"
APP_NAME = "AuthorBoard"
LICENSE_NAME = "GNU General Public License v3.0 or later"
LICENSE_SPDX = "GPL-3.0-or-later"

# GitHub release source (used by updater.py)
GITHUB_OWNER = "Vibrantic"
GITHUB_REPO = "AuthorBoard"

# Asset naming convention for release uploads
# (must match what build_windows.py / build_linux.py / build_macos.py produce)
UPDATE_ASSET_WINDOWS = "AuthorBoard-{version}-windows.zip"
UPDATE_ASSET_LINUX = "AuthorBoard-{version}-linux.tar.gz"
UPDATE_ASSET_MACOS = "AuthorBoard-{version}-macos.zip"

AUTHOR_MAINTAINER = "Vibrantic"
AUTHOR_AI_INITIAL = "Claude (Anthropic)"
AUTHOR_AI_PERFORMANCE = "DeepSeek"