# Changelog

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