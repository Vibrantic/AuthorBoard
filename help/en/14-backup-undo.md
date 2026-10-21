# Undo, backups and recovery

## Undo and redo

**Ctrl+Z** undoes, **Ctrl+Y** (or Ctrl+Shift+Z) redoes. Almost everything can be undone: creating, deleting, moving, resizing, text, tags, attributes, pins, threads, colours, locks, comments and attachments. Typing is grouped into steps. Inside a text field Ctrl+Z undoes your typing there first.

## Unsaved changes

The window title shows an asterisk `*` when there are unsaved changes. Opening another notebook, going back to the bookshelf, switching the language or closing the program asks whether to **save, discard or cancel**.

## Autosave and recovery

Every few minutes (see *Settings*) a recovery copy `<book>.autosave` is written when there are unsaved changes. After a crash AuthorBoard offers to load it. Saving removes it.

## Backups

When you save a notebook, the previous version is copied to `~/.authorboard/backups/<book>/` (at most every 5 minutes, the newest 20 are kept). **File → Load backup …** restores one into the open board; you can undo that with Ctrl+Z.
