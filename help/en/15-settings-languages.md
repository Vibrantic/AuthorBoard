# Settings and languages

Open **Edit → Settings …** (Ctrl+,).

## General

- **Spell checking** on/off and the **dictionary** (Automatic = language of the interface, English, Deutsch).
- **Focus mode** on/off.
- **Autosave** interval in minutes.
- **User dictionary**: the words you added; select and remove them here.

## Note types

See [Note types](topic:05-note-types): custom types for this book and global ones for all books.

## Interface language

*View → Language* switches between the installed languages immediately. The window reopens in the new language and returns to your notebook; if there are unsaved changes you are asked first.

### Adding a language

1. Run `python i18n.py new fr "Français"`. This creates `locales/fr.json` with every text.
2. Translate the values in that file (empty values fall back to German).
3. Optionally copy `help/en` to `help/fr` and translate the manual.
4. Restart: the language appears in the menu.

Use `python i18n.py update fr` after the program gained new texts and `python i18n.py check fr` to list missing translations.

Settings are stored in `~/.authorboard/settings.json`.
