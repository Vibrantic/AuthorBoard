# Troubleshooting and data

## Where is my data?

| Item | Location |
|---|---|
| Library, shelves | `~/.authorboard/library.json` |
| Notebooks | `~/.authorboard/books/<id>.json` |
| Backups | `~/.authorboard/backups/<id>/` |
| Settings | `~/.authorboard/settings.json` |

Set the environment variable `AUTHORBOARD_HOME` to use another folder. On Windows `~` is your user folder (for example `C:\Users\Name`).

## Spell checking does not work

Install the optional package: `pip install pyspellchecker`, then restart. Check *Settings → General*. Names of notes and tags are never flagged.

## "cannot import name …"

The program files are from different versions. Replace **all** files of the program with the same release, including the `locales` and `help` folders, and delete the `__pycache__` folder.

## A notebook will not open

Use *File → Load backup …* or open `<book>.json.autosave`. Files are written atomically (temp file then rename), so a crash cannot leave half-written files.

## Limits

- Single attachments up to 40 MB. Attachments are stored inside the notebook file, so very large attachments make the file big.
- Spell checking knows English and German.

## Reporting problems

Describe the steps and attach the message shown in the terminal when starting with `python main.py`.
