# Rückgängig, Sicherungen und Wiederherstellung

## Rückgängig und Wiederholen

**Strg+Z** macht rückgängig, **Strg+Y** (oder Strg+Umschalt+Z) wiederholt. Fast alles lässt sich rückgängig machen: Anlegen, Löschen, Verschieben, Größe ändern, Text, Tags, Attribute, Pins, Fäden, Farben, Sperren, Kommentare und Anhänge. Tippen wird zu Schritten zusammengefasst. In einem Textfeld macht Strg+Z zuerst deine Eingabe dort rückgängig.

## Ungespeicherte Änderungen

Die Titelleiste zeigt ein Sternchen `*`, wenn es ungespeicherte Änderungen gibt. Beim Öffnen eines anderen Notizbuchs, beim Zurück zum Regal, beim Sprachwechsel und beim Beenden fragt das Programm, ob **gespeichert, verworfen oder abgebrochen** werden soll.

## Automatische Sicherung und Wiederherstellung

Alle paar Minuten (siehe *Einstellungen*) wird bei ungespeicherten Änderungen eine Wiederherstellungskopie `<Buch>.autosave` geschrieben. Nach einem Absturz bietet AuthorBoard an, sie zu laden. Beim Speichern wird sie entfernt.

## Sicherungen

Beim Speichern eines Notizbuchs wird die vorherige Fassung nach `~/.authorboard/backups/<Buch>/` kopiert (höchstens alle 5 Minuten, die neuesten 20 bleiben). **Datei → Sicherung laden …** stellt eine davon im geöffneten Board wieder her; mit Strg+Z lässt sich das rückgängig machen.
