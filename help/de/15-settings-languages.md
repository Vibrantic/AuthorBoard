# Einstellungen und Sprachen

Öffnen mit **Bearbeiten → Einstellungen …** (Strg+,).

## Allgemein

- **Rechtschreibprüfung** an/aus und **Wörterbuch** (Automatisch = Sprache der Oberfläche, English, Deutsch).
- **Fokus-Modus** an/aus.
- **Automatische Sicherung**: Intervall in Minuten.
- **Eigenes Wörterbuch**: die Wörter, die du hinzugefügt hast; hier lassen sie sich entfernen.

## Notizarten

Siehe [Notizarten](topic:05-note-types): eigene Arten für dieses Buch und globale für alle Bücher.

## Sprache der Oberfläche

*Ansicht → Sprache* wechselt sofort zwischen den installierten Sprachen. Das Fenster öffnet sich in der neuen Sprache neu und kehrt zu deinem Notizbuch zurück; bei ungespeicherten Änderungen wirst du vorher gefragt.

### Eine Sprache hinzufügen

1. `python i18n.py new fr "Français"` ausführen. Das erzeugt `locales/fr.json` mit allen Texten.
2. Die Werte in dieser Datei übersetzen (leere Werte fallen auf Deutsch zurück).
3. Optional `help/en` nach `help/fr` kopieren und das Handbuch übersetzen.
4. Neu starten: Die Sprache erscheint im Menü.

Nach neuen Programmtexten hilft `python i18n.py update fr`, und `python i18n.py check fr` listet fehlende Übersetzungen auf.

Die Einstellungen liegen in `~/.authorboard/settings.json`.
