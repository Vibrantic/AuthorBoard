# Changelog

## 1.2.3

The first release with a Windows installer and a built-in updater. Once
installed via `AuthorBoard-Setup-1.2.3.exe`, future updates arrive through
the app itself.

### Added

- **Windows installer (`AuthorBoard-Setup-1.2.3.exe`).** Per-user install
  to `%LOCALAPPDATA%\AuthorBoard\` (no UAC prompt), Start Menu entry,
  optional desktop shortcut, uninstaller. Replaces the previous "download a
  zip and extract it" workflow.
- **In-app update check.** AuthorBoard queries
  `github.com/<owner>/<repo>/releases/latest` shortly after startup (delayed
  ~2 s, so the first frame is not delayed) and on demand via **Help → Check
  for updates…**. The startup check is silent unless an update exists; the
  manual check always reports a result.
- **Update dialog with release-notes preview.** Renders the GitHub release
  `body` (Markdown) in a `QTextBrowser`, with **Update now**, **Remind me
  tomorrow** (1-day skip), **Remind me in a week** (7-day skip) and
  **Later** (ask again on next start).
- **Download with progress and automatic restart.** Choosing *Update now*
  downloads the platform archive with a status-bar percentage, then hands
  off to a small standalone `AuthorBoardUpdater.exe` that waits for the
  main process to exit, replaces the app folder from a staged extraction
  (rollback on failure), and relaunches AuthorBoard automatically.
- **Skip state persisted in `QSettings`** under `updates/skip_until` and
  `updates/skipped_version`. A newer release always overrides a skip, so
  skipping 1.2.3 does not hide 1.2.4.
- **26 new translation keys** for the updater UI in `locales/en.json`.

### Changed

- **`build_windows.py` builds two bundles.** Main app
  (`dist/AuthorBoard/`) plus the standalone updater
  (`dist/AuthorBoardUpdater/`), which is then staged into
  `dist/AuthorBoard/updater/` so the release zip is self-contained and a
  future update can still launch the updater on an older install.
- **`build_windows.py` fails fast** — each step returns a bool, and
  `main()` bails out on the first failure. Previously an updater build
  failure was silently ignored.
- **`build_windows.py` cleans stale artifacts** for each bundle name before
  rebuilding, so a release archive never contains ghost files from an older
  build.
- **`HIDDEN` list extended** with `flow_view`, `group_item`, `updater`,
  `updater_dialog` (were missing before; only mattered if PyInstaller's
  static analysis ever missed the lazy imports).

### Fixed

- **Language switch raised `TypeError`.** `switch_language` unpacked
  `QProcess.startDetached(...)` as `(ok, pid)` (the PyQt5 signature).
  PySide6 returns a plain `bool`; the unpack raised and the switch never
  completed. Now uses the PySide6 signature.
- **Language switch could leave the app closed without reopening it.** On
  a frozen build where the relaunch fails (binary moved, no exec
  permission, sandboxed), the window was closed *before* the relaunch was
  attempted. The relaunch is now attempted first; on failure the window
  stays open and a warning tells the user to start AuthorBoard manually —
  the language choice is already persisted and will be used next time.
- **`BoardScene.note_matches` was missing the `haystack` parameter** that
  `NoteItem.search_haystack` was added to feed. Loading any notebook raised
  `TypeError: note_matches() got an unexpected keyword argument 'haystack'`
  on the first tree refresh. Fixed.
- **Stale search haystack after a note-type rename.** The per-note cache is
  now invalidated on `reset_types` and when the label baked into the cache
  differs from the current one.
- **`AboutDialog` credits drifted from `version.py`.** The three
  `AUTHOR_*` constants were unused; the dialog now reads them live.
- **`tests/test_showcase.py`** no longer asserts hard-coded fixture counts;
  it asserts the invariants the showcase is meant to demonstrate, and reads
  raw JSON for the structural checks (fixing a
  `TypeError: 'GroupData' object is not subscriptable`).
- **`tests/test_inspector_stability.py`** now has real assertions (it used
  to only print diagnostics).

### Compatibility

- **Files:** no format change. Files saved by 1.2.2 open in 1.2.3, and
  vice versa.
- **Settings:** existing `QSettings` keys are unaffected. Three new keys
  (`updates/skip_until`, `updates/skipped_version`, plus
  `updates/last_check` if you add throttling later) default to absent — no
  migration needed.
- **Install layout changes for new installs.** 1.2.2 and earlier were a
  zip folder. Users upgrading from 1.2.2 should delete the extracted
  folder after installing 1.2.3; user data in `~/.authorboard/` is not
  touched by either path.
- **No public API change.**

## 1.2.2

A bugfix release. No file-format change: 1.2.2 reads every 1.2.1 file, and
1.2.1 reads every 1.2.2 file.

### Fixed

- **FlowView crashed on open.** `NoteListPanel.__init__` called
  `self.search.installEventFilter(self)` *before* `self.search` was assigned,
  so constructing a `FlowViewDialog` raised `AttributeError` from inside a
  signal handler, the dialog was never shown, and the user saw "nothing
  happens". The duplicate `self.search = QLineEdit()` lower in `__init__`
  is the real widget; the stray pre-emptive filter line has been removed.
- **Language switch could quit the app without reopening it.** On a frozen
  build where the relaunch fails (binary moved, no exec permission,
  sandboxed), `switch_language` closed the current window *before* attempting
  the relaunch, leaving the user with a closed app and no new instance. The
  relaunch is now attempted first; on failure the window stays open and a
  warning explains that the next manual start will use the new language
  (the choice is already persisted in `QSettings`). The language menu
  checkmark is also restored to the actual current language on cancel, as
  intended.
- **`QProcess.startDetached` in `switch_language` was unpacked as
  `(ok, pid)`.** PySide6 returns a plain `bool` (the `(bool, qint64)` tuple
  only exists in PyQt5). The unpack raised `TypeError` and the language
  switch never completed. Now uses the PySide6 signature.
- **`BoardScene.note_matches` missed the new `haystack` parameter** that
  `NoteItem.search_haystack` was added to feed. The search filter raised
  `TypeError: note_matches() got an unexpected keyword argument 'haystack'`
  on the first `refresh_tree()` after loading a book. The function now
  accepts an optional `haystack` (default `None`, builds it from the note
  as before), and the scene passes the cached one.
- **Stale search haystack after a note-type rename.** Renaming a note type
  (book or global) updated the visible label but not the cached search
  haystack of notes that use the type, so typing the new label did not
  match them until each note was touched. The per-note haystack cache is
  now invalidated whenever the type registry changes
  (`MainWindow.reset_types`) and whenever the label differs from the one
  baked into the cache (guarded by `NoteItem._haystack_key`).
- **`AboutDialog` and `version.py` disagreed.** The three `AUTHOR_*`
  constants in `version.py` were unused by `AboutDialog` (which hard-coded
  the same names in its HTML), so editing them had no effect. `AboutDialog`
  now imports and displays them live, in a small "Team" section; the prose
  remains fully translatable.

### Changed

- **Undo / redo is cheaper on boards with many threads.** `apply_state`
  used to destroy and recreate *every* connection item on every undo/redo
  step, invalidating the scene's item index and forcing a full repaint.
  Connections are now reconciled by id: only removed ones are dropped, only
  new ones are added, and colour / label edits are applied in place. Cost
  is now O(changed connections) instead of O(all connections).
- **`models.note_matches` accepts a cached haystack** (optional
  `haystack` keyword) so callers can skip the O(len(note)) string build.
  `BoardScene.note_matches` uses this.
- **Test robustness.** `tests/test_showcase.py` no longer asserts exact
  fixture counts (10 groups, 16 timeline entries, 51 notes) — those
  properties changed every time the showcase was edited. The test now
  asserts the *invariants* the showcase is meant to exercise (at least one
  group with valid geometry, at least one dated note, at least one undated
  note, all timeline entries ↔ parsable dates, both a nested and a locked
  frame, etc.). The `GroupData` vs. raw-JSON mistake (indexing dataclasses
  like dicts) is fixed. `tests/test_inspector_stability.py` now has real
  `assert` statements (the previous version only printed diagnostics).
  `tests/test_shelf_library.py` documents the y-axis snap that its
  `drop_book` setup depends on and asserts invariants rather than one
  hard-coded category id.

### Documentation

- `tests/test_showcase.py` now has a `# NOTE:` explaining why it validates
  the raw JSON file rather than `Storage.load(...)` output.
- `tests/test_shelf_library.py` now has a `# NOTE:` about `drop_book`
  snapping by y; if that ever changes, the test's drop-position setup must
  change too.

### Compatibility

- No `storage.FORMAT_VERSION` bump. Files saved by 1.2.1 open unchanged in
  1.2.2, and 1.2.2 writes files that 1.2.1 opens.
- PySide6's `QProcess.startDetached` returns `bool` — code that ran against
  PyQt5's `(bool, pid)` tuple is no longer compatible and has been fixed
  here. No user-facing API change.
- No public API (module-level function, class, or attribute listed in the
  docs) was removed.

## 1.2.1

Group frames, a fix for undo, and a fix for the stuck mouse cursor.
Existing notebooks open unchanged.

**New**

- **Group frames.** Select notes and press `Ctrl+G` (or right-click a
  note → *Gruppe aus Auswahl*) to frame them with a titled, coloured,
  resizable group, similar to the comment box in Unreal Blueprints. A
  group can also be created empty from the board's right-click menu
  (*Neue Gruppe hier*).
  - Dragging the header moves the frame together with all notes inside
    it. Pins and threads follow. Locked notes stay where they are.
  - Membership is geometric: a note belongs to the topmost frame that
    contains its centre. Notes dropped into a frame join it, notes
    dragged out leave it. Where frames overlap, the topmost frame wins.
  - Frames can be nested: a frame that lies completely inside another
    one moves with it.
  - Double-click the header to rename. Right-click offers rename,
    colour, lock, *Gruppe nach vorne*, *Gruppe auflösen* (frame
    removed, notes stay) and *Gruppe samt Notizen löschen*. `Delete`
    on a selected frame removes only the frame.
  - Only the header, the border and the resize corner react to the
    mouse. The inside of a frame is click-through, so rubber-band
    selection and double-click-to-create-a-note still work there.
  - Frames dim together with their notes when a search filter or
    focus mode is active, are included in *Alles anzeigen* and in the
    PNG export, and are covered by undo / redo, autosave and backups.
  - Stored as an optional `"groups"` list in the notebook file. The
    file format version is unchanged; older AuthorBoard versions open
    such files but ignore the frames.

- **Groups in the in-app manual.** Two new help topics — *Gruppen*
  and *FlowView* — are included in the English and German manual
  (`help/en/19-groups.md`, `help/en/20-flowview.md` and the `de`
  equivalents), linked from *Getting started* and searchable through
  *F1 → Documentation*.

**Fixed**

- **Undo / redo did not restore notes.** `apply_state` compared the
  target snapshot with itself, so no note was ever replaced; only
  threads, selection and (now) group frames came back. It now
  compares against the state that was being displayed.

- Removed a leftover debug `print` from `NoteItem.model_changed`
  that wrote a line to the console on every edit.

**Build**

- `group_item` added to the hidden imports of all three build
  scripts, and `flow_view` added to the Linux and macOS scripts (the
  Windows script had it).
- `tools/make_screenshots.py` now sets `QT_QPA_FONTDIR` on Windows
  (offscreen mode) so screenshots render with the system fonts, and
  copies a single known-good TTF into a temp directory to avoid the
  `QFontEngineFT: Failed to create FreeType font engine` warning
  some Windows font files trigger. The offscreen plugin's
  `propagateSizeHints` chatter is filtered out of stderr.

**Internal**

- New test `tests/test_groups.py` (creation, membership, nesting,
  moving, undo, save / load).
- `tests/test_i18n.py` no longer starts a real second process when
  switching the language (the old test re-launched itself
  recursively) and uses its own settings key, so it no longer
  changes the real language setting.
- `tests/test_flow_view.py` repaired and extended with a minimap
  path check.
- `tests/test_shelf_library.py`: mention lookup now announces its
  edits via `model_changed()`, as the app does.

## 1.2.0

**New**

- **FlowView** — a non-modal, zoomable window that shows the current
  root note and its direct neighbours in pin order. Click ▶ on a
  neighbour to re-root; right-click a thread to delete it (the
  neighbour that loses its only connection disappears from the view).
  Every node is fully editable through the embedded Inspector, so both
  root and neighbours can be edited without leaving FlowView.
  Right-click a note on the board → *FlowView öffnen*, or use
  *View → FlowView (Ctrl+T)* with a note selected.

- **FlowView minimap** — a compact 240×240 overview in the bottom-left
  corner of the FlowView, always showing the whole connected component
  of the current root. The root and its direct neighbours are drawn as
  filled "active" dots (click = re-root); up to 30 further notes are
  drawn as hollow "silhouette" dots, ordered by BFS distance from the
  root. Hover any dot for the note title.

- **Path highlight** — clicking a silhouette dot (or its entry in the
  note list) highlights the shortest path from the root to that note as
  a poly-line through the dots of every intermediate note. Clicking an
  active neighbour steps along that path; when the destination becomes
  the root, the highlight clears. Only one silhouette can be selected
  at a time — selecting a different one replaces the path.

- **Path dimming in FlowView** — while a silhouette is selected, every
  FlowView node and thread that is not part of the highlighted path
  dims to 0.25 / 0.1. This makes the walk "pop" out of the graph so the
  user can see at a glance which neighbour to click next. The dim
  recomputes on every re-root.

- **Path navigation buttons** — ◀ / ▶ at the bottom-left of the
  minimap step one hop back / forward along the highlighted path. When
  no silhouette is selected, they fall back to walking the root
  history, so the user can always undo the last re-root even after
  reaching the destination.

- **Note list panel** — a searchable list of every note shown on the
  minimap, docked to the right of it at the same height and resizable
  on its right edge. Active notes are prefixed with `●` and re-root
  the FlowView when clicked; silhouettes are prefixed with `○` and
  toggle the path highlight. The selected silhouette is highlighted in
  the same amber as the minimap path. A search box filters the list in
  real time; `Enter` clears the filter, `Esc` clears and returns focus
  to the list.

- **Selection lock while a path is active** — while a silhouette is
  selected, clicks on FlowView nodes and threads no longer change the
  selection. The ▶ arrows on neighbour nodes still work, so re-rooting
  along the path is not blocked. This prevents the user from
  accidentally breaking the path highlight mid-walk.

- **Bidirectional sync** — the FlowView, minimap and note list always
  agree on the current root, its active neighbours, the selected
  silhouette and its path, regardless of which of the three the user
  clicked. A root change through the FlowView (▶ arrow, "Als Wurzel
  setzen", inspector jump, or an external board change) refreshes the
  minimap and list immediately; a click in the minimap or list updates
  the FlowView just as immediately.

- **Inspector width when maximised** — the embedded Inspector in the
  FlowView is pinned to 500 px when the window is maximised or in
  full-screen, so a wide monitor does not give the inspector an
  oversized share of the screen. At normal window sizes the splitter
  keeps its proportional 3:1 layout.

**Fixed**
- **Cursor Visual Bug** - fixed where sometimes the icon got locked either 
  to cursor or hand depending on what action was executed.

## 1.1.1

Bug fixes and two small UX features. No file-format changes; existing
notebooks open unchanged.

**New**

- **Duplicate with connections.** Ctrl+D now also duplicates the threads
  that connect the selected notes to each other. A thread is duplicated
  only when *both* of its endpoint notes were part of the selection, so
  the copy of a connected group stays a connected group, and a note
  connected to something outside the selection is copied without that
  thread.
- **Select connected notes.** Right-click a note for two new entries:
  *Verbundene Notizen auswählen* selects the note and its direct
  neighbours; *Verbundene Notizen rekursiv auswählen* selects the whole
  connected component reachable by threads. Both entries are disabled
  when the note has no threads.

**Changed**

- Double-clicking a note now opens the full-size editor (previously it
  added a pin). Pins are added only via the right-click menu entry
  *Pin hier hinzufügen*.

**Fixed**

- Building the Linux app with Python 3.14 produced a
  `libpython3.14.so.1.0` load failure in the frozen binary. The build
  docs now recommend Python 3.12 (or 3.11) via `deadsnakes` on
  Ubuntu.
- Focus mode got stuck after the first note click when the deselect
  click landed on another note. The filter deferral is now applied
  only when the press lands on empty background.
- Dimmed notes did not return to full opacity on deselect. Qt's
  `DeviceCoordinateCache` doesn't invalidate cached pixmaps on
  `setOpacity`; the scene now forces an explicit `update()` on every
  item whose opacity changed.
- Threads went invisible after changing the selection until the canvas
  was panned. The visible-set change is now republished whenever the
  selection or the zoom changes.
- Cursor occasionally locked as the closed-hand or resize-diagonal
  icon after panning or resizing. The cursor is now reset on
  `leaveEvent`, `focusOutEvent`, and any button release; `NoteItem`
  also clears its own cursor on release and focus loss. A short
  watchdog cleans up a stuck pan if the release was consumed by a
  child item.
- Language switch in a frozen build could not rebuild the window
  in-process (Qt's `QApplication` singleton can't be re-created).
  Switching the language now saves pending changes (with the usual
  prompt if there are any), closes the current window, and starts a
  fresh AuthorBoard process in the new language, reopening the book
  the user was in.
- Right-click menu on a note raised a `NameError` because one of the
  new entries referenced a variable that hadn't been assigned.
- `BoardView.mouseReleaseEvent` was calling `BoardScene`-only methods
  (`_handle_release`, `interaction_finished`), which crashed on every
  non-middle-button release. The extra calls have been removed; only
  the middle-button branch remains.
- `BoardScene.reset` referenced `self.scene` (a typo for
  `self._mentions_revision`), which crashed on project load.

**Build**

- Added `build_windows.py`, `build_linux.py`, `build_macos.py`
  (onedir). Each script collects the Qt binaries, bundles `help/`,
  `locales/`, `assets/`, `showcase/` and `LICENSE`, and adds the
  `spellchecker` data.
- Added `resource.py` with `resource_path()`, used by `help_dialog.py`,
  `i18n.py` and `main.py`, so bundled resources are found both in a
  frozen build (`sys._MEIPASS`) and in a dev checkout (`__file__`).
- Added `.github/workflows/release.yml` — builds all three platforms
  on tag push and attaches one zip / tar.gz per platform to the
  release.

**Documentation**

- `README.md`: features section updated for adaptive thread
  visibility, large-board rendering and the new comment click
  behaviour; mouse hint updated for the double-click = editor change.
- `README.md`, `AUTHORS`, `version.py`, `about_dialog.py`: credits
  now name the human maintainer and both AI assistants (Claude for
  the initial implementation, DeepSeek for the performance work and
  subsequent bug fixes), each with the specific contribution.
- `locales/en.json`: new strings for the About dialog, the
  "select connected" menu entries, and the updated note tooltip.

## 1.1.0

Performance work, small UX fixes, and one new feature.

**Performance**

- Board rendering
  - Level-of-detail tiers for notes, threads and pins, chosen per
    frame from the current zoom and the number of visible items.
  - Threads whose endpoints are off-screen are skipped; the view
    publishes the visible rect and the visible counts once per paint
    (throttled while panning).
  - Cached paper paths, note tooltips, search haystacks, thread paths
    and label rectangles.
  - Tiled-pixmap grid; device-coordinate item cache; cheaper bounding
    rectangles.
  - Reapplying the search / focus filter only touches items whose
    opacity actually changed.
- Timeline
  - Bucketed O(N) level assignment (previously O(N²); a 5000-note
    timeline frame drops from ~2.2 s to ~44 ms).
  - Cached level and visible-set computations per view state;
    off-screen entries are not painted.
- Data
  - Undo snapshots share per-note JSON strings across history
    entries; undo / redo re-adds only the notes that changed.
  - Refresh paths use dirty flags; the notes tree is updated
    incrementally from a per-note revision; per-note word counts and
    mention lookups are cached.
- Autosave is written on a worker thread and no longer blocks the UI.
- Fit-all is clamped to the minimum zoom, so the mouse wheel can
  always zoom back in.

**UX**

- Threads below 100 % zoom are hidden by default and shown only when
  a note is selected (its connected threads). Invisible threads are
  click-through.
- Clicking a comment in the Comments panel selects and centres the
  note that holds it, without opening the editor. Double-click still
  opens the editor and jumps to the commented words.
- Focus mode no longer gets stuck after the first note click when the
  deselect click landed on a note.
- Dimmed notes correctly return to full opacity when the selection is
  cleared.
- Mouse cursor no longer sticks as the closed-hand or resize-diagonal
  icon after panning or resizing with a release over a child item.

**Internal**

- `tools/make_stress.py` — generates boards of various shapes (grid,
  clusters, hub, long-range threads) for benchmarking.
- `tools/profile_board.py` — headless timing of the hot paths.
- `tools/bsp_probe.py` — BSP vs NoIndex comparison for
  `QGraphicsScene`.

## 1.0.0

First complete release.

- Bookshelf start page with colourable, draggable shelves and
  notebooks
- Board with typed sticky notes, pins, labelled coloured threads,
  search and filters
- Locking of notes and pins, focus mode, threads in front of notes
- Inspector with resizable attribute / attachment / connection lists,
  tag auto-completion
- Attachments (files and images) stored inside the notebook
- Full-size rich-text editor (fonts, colours, highlighter, links,
  images)
- Comments with hover pop-up and a Comments tab
- Spell checking for English and German
- Horizontal timeline, statistics, manuscript / outline / image
  export
- Undo / redo, save prompt, autosave with recovery, automatic backups
- Custom note types per book and global
- English and German interface, searchable in-app documentation,
  About dialog
- Showcase notebooks (English and German)