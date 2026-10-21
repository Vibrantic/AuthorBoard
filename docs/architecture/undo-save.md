# Undo, saving, autosave, backups

## Undo / redo = snapshots

`undo.UndoStack` is a list of **JSON strings** plus an index.

```text
capture_state()  =  json.dumps( Storage.to_dict(build_project_data(for_file=False), with_blobs=False), sort_keys=True )
```

* Any change schedules `checkpoint()` (350 ms debounce, so typing becomes one step). `checkpoint()` pushes the current state if it differs from the top of the stack.
* `undo()` first calls `checkpoint()` (to capture pending edits), then `apply_state()` which rebuilds the board with `restore_project(..., blobs="keep")` and re-selects the previously selected notes.
* **Dirty flag:** `dirty = (stack.current != saved_state)`. Saving sets `saved_state = stack.current`; undoing back to the saved state clears the asterisk.
* Snapshots exclude attachment bytes and the tag memory, so they stay small.

!!! note "Why snapshots?"
    Every feature (threads, locks, comments, tags ...) is automatically undoable as soon as it is part of `ProjectData`. No command objects to maintain. The price is memory (200 states by default), which is small because boards are small.

## When is something saved?

| Action | Result |
|---|---|
| Ctrl+S | `_write`: checkpoint, backup (books), `Storage.save`, clear autosave, update stats |
| leaving a dirty book / closing / switching language | `maybe_save()` -> save / discard / cancel dialog |
| every N minutes | `autosave()` writes `<file>.autosave` (or `~/.authorboard_recovery.json` for files outside the library) |
| next start | `check_recovery` / `load_file` offer the newer autosave |

`Storage.save` is atomic: write `<file>.tmp`, then `os.replace`.

## Backups

`Library.backup` copies `books/<id>.json` to `backups/<id>/YYYYmmdd-HHMMSS.json` *before* it is overwritten. *File -> Load backup ...* loads such a file with `blobs="merge"` as an undoable change.
