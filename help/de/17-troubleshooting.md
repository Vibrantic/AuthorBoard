# Fehlersuche und Daten

## Wo liegen meine Daten?

| Was | Ort |
|---|---|
| Bibliothek, Regale | `~/.authorboard/library.json` |
| Notizbücher | `~/.authorboard/books/<id>.json` |
| Sicherungen | `~/.authorboard/backups/<id>/` |
| Einstellungen | `~/.authorboard/settings.json` |

Mit der Umgebungsvariablen `AUTHORBOARD_HOME` nutzt du einen anderen Ordner. Unter Windows ist `~` dein Benutzerordner (z. B. `C:\Users\Name`).

## Die Rechtschreibprüfung funktioniert nicht

Installiere das optionale Paket: `pip install pyspellchecker` und starte neu. Prüfe *Einstellungen → Allgemein*. Namen von Notizen und Tags werden nie markiert.

## „cannot import name …“

Die Programmdateien stammen aus verschiedenen Versionen. Ersetze **alle** Dateien durch dieselbe Version – einschließlich der Ordner `locales` und `help` – und lösche den Ordner `__pycache__`.

## Ein Notizbuch lässt sich nicht öffnen

Nutze *Datei → Sicherung laden …* oder öffne `<Buch>.json.autosave`. Dateien werden atomar geschrieben (Temp-Datei, dann Umbenennen); ein Absturz hinterlässt also keine halb geschriebenen Dateien.

## Grenzen

- Einzelne Anhänge bis 40 MB. Anhänge liegen in der Notizbuch-Datei, sehr große machen sie entsprechend groß.
- Die Rechtschreibprüfung kennt Englisch und Deutsch.

## Probleme melden

Beschreibe die Schritte und hänge die Meldung an, die beim Start mit `python main.py` im Terminal erscheint.
