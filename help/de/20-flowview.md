# FlowView

**FlowView** ist ein eigenes, nicht modales Fenster, das die **Nachbarschaft einer Notiz** zeigt: die Wurzel und ihre direkt verbundenen Notizen. Damit läufst du den Verbindungsgraphen **einen Schritt nach dem anderen** ab, ohne das Board zu verlassen.

## Öffnen

- **Rechtsklick auf eine Notiz → FlowView öffnen**.
- Oder **Ansicht → FlowView** (Strg+T) bei ausgewählter Notiz.

Es gibt immer nur **ein** FlowView-Fenster: Öffnest du es für eine andere Notiz, wird das bestehende Fenster auf diese umgehängt.

## Aufbau

- **Zwei Spalten**: links die Wurzel, rechts ihre direkten Nachbarn in Pin-Reihenfolge.
- **Kanten** sind rechtwinklig geführt; jede Kante hat eine eigene Spur, sodass sich keine zwei Linien überkreuzen.
- **Rechtsklick auf eine Kante**: Farbe, Beschriftung (z. B. „Bruder von“) oder Löschen.
- **Doppelklick auf einen Knoten**: öffnet den großen Editor.
- **▶-Pfeil** rechts an einem Nachbarn: macht ihn zur neuen Wurzel und baut die Ansicht um ihn herum neu auf.

## Inspector

Der Inspector im FlowView ist der **gleiche** wie auf dem Board: Titel, Tags, Attribute, Text, Anhänge und Verbindungen der aktuell inspizierten Notiz. Änderungen landen sofort im Board.

## Minimap

In der unteren linken Ecke liegt eine **Übersicht der ganzen verbundenen Komponente**:

- **Gefüllte Punkte** sind die aktuelle Wurzel und ihre Nachbarn (klick = dorthin springen).
- **Hohle Punkte** sind bis zu `MAX_DOTS − |aktiv|` weitere Notizen nach BFS-Abstand; ihre Anzahl bleibt immer begrenzt, damit die Minimap auf großen Boards lesbar bleibt.
- **Hover** zeigt den Titel jeder Notiz.

## Pfad hervorheben

- Klick auf einen **hohlen Punkt** → AuthorBoard zeichnet den **kürzesten Pfad** von der Wurzel zu dieser Notiz als gelbe Linie.
- Alles, was nicht auf dem Pfad liegt, wird **abgeblendet** – der nächste Schritt ist so sofort sichtbar.
- Erreichst du die Ziel-Notiz (sie wird neue Wurzel), erlischt die Markierung – der Pfad ist zu Ende.
- Wählst du einen anderen hohlen Punkt, wird der Pfad neu berechnet.
- **Solange ein Pfad aktiv ist**, ändern Klicks im FlowView die Auswahl **nicht** – so kannst du den Weg nicht versehentlich verlassen. Die **▶-Pfeile** funktionieren weiterhin.

## Notizenliste

Neben der Minimap sitzt eine **durchsuchbare, in der Breite verstellbare Liste** aller Notizen, die die Minimap zeigt:

- **● Einträge**: aktive Notizen; Klick setzt sie als Wurzel.
- **○ Einträge**: Silhouetten; Klick schaltet den Pfad ein / aus.
- Der aktuell markierte Silhouetten-Punkt ist **gelb hinterlegt** – passend zur Pfadfarbe in der Minimap.
- **Enter** leert die Suche, **Esc** leert sie und gibt den Fokus an die Liste zurück.

## Vor- und Zurück

Die **◀ / ▶**-Knöpfe unten links in der Minimap:

- Bei aktiver Pfadmarkierung: **einen Schritt zurück / vor** auf dem Pfad.
- Ohne aktive Pfadmarkierung: durch die **Wurzel-Historie** blättern, also den letzten Sprung rückgängig machen oder wiederholen.

## Navigation und Synchronisation

- **Strg+0** oder *Rechtsklick auf leeren Hintergrund → Ansicht zurücksetzen* stellt Zoom und Position wieder her.
- FlowView, Minimap und Notizenliste sind **immer synchron**: egal, wo du klickst, alle drei zeigen dieselbe Wurzel, dieselben Nachbarn, denselben Pfad.
- Board und FlowView teilen sich die Notizen – Änderungen an einer Notiz erscheinen auf beiden Seiten sofort.

## Tipps

- Nutze FlowView als **Lesepfad**: Klick auf eine entfernte Notiz in der Liste, dann mit ◀/▶ Schritt für Schritt bis dorthin – das Board bleibt dabei ruhig, weil du es nicht verlässt.
- Für einen reinen **Überblick über die Nachbarschaft** genügt die Minimap; den großen FlowView brauchst du erst, wenn du die Notizinhalte selbst lesen willst.