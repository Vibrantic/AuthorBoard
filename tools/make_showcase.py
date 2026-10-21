#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the showcase notebooks (German and English).

    python tools/make_showcase.py            # writes showcase/*.json

The showcase is a fictional dark-fantasy novel that uses *every* feature of
AuthorBoard: all note types, custom and global note types, tags, attributes,
status, pins (some locked), labelled coloured threads, locked notes, a dated
timeline, rich text with colours / links / images, comments, attachments (an
image, text files), mentions between notes and book information.

The file is created with Qt (for the illustrations and for normalising the
rich text) so it must run with PySide6 installed.  Ids are derived from fixed
names so re-running produces identical files.
"""

import base64
import json
import os
import sys
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient, QTextDocument)
from PySide6.QtWidgets import QApplication

NS = uuid.UUID("6f1c2a52-8c2e-4c63-9a53-0a5b7c1d9e10")
uid = lambda *p: str(uuid.uuid5(NS, "/".join(p)))
cid = lambda name: uuid.uuid5(NS, "comment/" + name).hex[:12]

app = QApplication.instance() or QApplication([])


# ======================================================================= images
def png_bytes(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def make_map(labels):
    """A parchment-style map of the Northlands."""
    img = QImage(720, 460, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 720, 460)
    g.setColorAt(0, QColor("#e9d8b0")); g.setColorAt(1, QColor("#cdb584"))
    p.fillRect(img.rect(), g)
    p.setPen(QPen(QColor("#8a6d3b"), 6)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(3, 3, 714, 454)
    sea = QPainterPath(); sea.moveTo(0, 300); sea.cubicTo(120, 250, 200, 360, 330, 330)
    sea.cubicTo(420, 300, 470, 380, 560, 440); sea.lineTo(0, 460); sea.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#9bb8c4")); p.drawPath(sea)
    p.setBrush(QColor("#4b5a3a"))                        # the burnt forest
    for i in range(46):
        x = 360 + (i * 53) % 280; y = 70 + (i * 37) % 170
        p.drawEllipse(QPointF(x, y), 7, 7)
    p.setPen(QPen(QColor("#6d4c41"), 3, Qt.PenStyle.DashLine))   # the route
    path = QPainterPath(); path.moveTo(500, 150); path.cubicTo(420, 230, 330, 250, 250, 300)
    path.cubicTo(200, 330, 170, 290, 120, 320); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)
    p.setPen(QColor("#3e2c1c")); f = QFont("serif", 13); f.setBold(True); p.setFont(f)
    for text, x, y in ((labels[0], 440, 90), (labels[1], 80, 300), (labels[2], 270, 270), (labels[3], 560, 230)):
        p.drawText(QPointF(x, y), text)
    for x, y in ((500, 150), (120, 320), (250, 300), (610, 215)):
        p.setBrush(QColor("#a14a4a")); p.setPen(QPen(QColor("#3e2c1c"), 1.5)); p.drawEllipse(QPointF(x, y), 6, 6)
    f2 = QFont("serif", 22); f2.setItalic(True); p.setFont(f2); p.setPen(QColor("#5b4426"))
    p.drawText(QPointF(24, 440), labels[4])
    p.end()
    return png_bytes(img)


def make_portrait(caption):
    """A silhouette with an ember glow."""
    img = QImage(300, 380, QImage.Format.Format_ARGB32)
    p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 0, 380); g.setColorAt(0, QColor("#1b1620")); g.setColorAt(1, QColor("#3a1f1a"))
    p.fillRect(img.rect(), g)
    glow = QRadialGradient(150, 200, 170); glow.setColorAt(0, QColor(255, 140, 40, 150)); glow.setColorAt(1, QColor(255, 140, 40, 0))
    p.setBrush(glow); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(150, 200), 170, 170)
    p.setBrush(QColor("#0e0b10")); p.drawEllipse(QPointF(150, 150), 52, 60)
    sh = QPainterPath(); sh.moveTo(40, 380); sh.cubicTo(50, 260, 110, 235, 150, 235); sh.cubicTo(190, 235, 250, 260, 260, 380); sh.closeSubpath(); p.drawPath(sh)
    p.setBrush(QColor("#ffb74d"))
    for x, y, r in ((205, 118, 4), (225, 95, 3), (190, 80, 2.5), (232, 140, 2)):
        p.drawEllipse(QPointF(x, y), r, r)
    p.setPen(QColor("#e8d9c0")); f = QFont("serif", 14); f.setItalic(True); p.setFont(f)
    p.drawText(QRectF(0, 340, 300, 30), Qt.AlignmentFlag.AlignCenter, caption)
    p.end()
    return png_bytes(img)


def make_mood(caption):
    """Smoky gradient 'mood board' picture."""
    img = QImage(520, 300, QImage.Format.Format_ARGB32)
    p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 520, 300); g.setColorAt(0, QColor("#2b2b30")); g.setColorAt(0.6, QColor("#5a3a2a")); g.setColorAt(1, QColor("#d9822b"))
    p.fillRect(img.rect(), g); p.setPen(QPen(QColor(10, 10, 10, 200), 5))
    for i in range(14):
        x = 20 + i * 38; p.drawLine(QPointF(x, 300), QPointF(x + (i % 3) * 6 - 6, 120 + (i * 29) % 90))
    p.setPen(QColor("#f1e6d3")); f = QFont("serif", 16); f.setItalic(True); p.setFont(f); p.drawText(18, 34, caption)
    p.end()
    return png_bytes(img)


# ======================================================================== builder
def build(lang):
    de = lang == "de"
    T = lambda d, e: d if de else e                     # pick the language

    notes, by_key, connections, blobs = [], {}, [], {}
    TYPE_COLORS = {"note": "#fff176", "character": "#ffb3c1", "location": "#a5d6a7", "chapter": "#90caf9",
                   "scene": "#ce93d8", "event": "#ffcc80", "plot": "#80deea", "item": "#d7ccc8",
                   "idea": "#e6ee9c", "research": "#b0bec5", "custom_zauberspruch": "#b2dfdb",
                   "custom_fraktion": "#d1c4e9", "global_moodboard": "#f48fb1"}
    custom_types = [
        {"key": "custom_zauberspruch", "label": T("Zauberspruch", "Spell"), "color": TYPE_COLORS["custom_zauberspruch"],
         "attributes": [T("Wirkung", "Effect"), T("Preis", "Price")]},
        {"key": "custom_fraktion", "label": T("Fraktion", "Faction"), "color": TYPE_COLORS["custom_fraktion"],
         "attributes": [T("Anführer", "Leader"), T("Ziel", "Goal")]},
        # A *global* type (normally defined in Settings) travels with the file when notes use it
        {"key": "global_moodboard", "label": "Moodboard", "color": TYPE_COLORS["global_moodboard"],
         "attributes": [T("Quelle", "Source"), T("Stimmung", "Mood")]},
    ]

    def add_blob(name, data, mime, key):
        aid = uid("blob", key)
        blobs[aid] = data
        return {"id": aid, "name": name, "mime": mime, "size": len(data), "inline": False}

    def rich(html):
        """Normalise HTML through Qt; returns (plain_text, html)."""
        doc = QTextDocument(); doc.setHtml(html)
        return doc.toPlainText().replace("\ufffc", ""), doc.toHtml()

    def note(key, typ, title, x, y, attrs=None, tags=None, content="", status="", w=270, h=200,
             color=None, locked=False, html=None, attachments=None, comments=None):
        if html:
            content, html = rich(html)
        n = {"id": uid("note", key), "title": title, "content": content, "x": x, "y": y, "width": w,
             "height": h, "color": color or TYPE_COLORS[typ], "note_type": typ, "status": status,
             "locked": locked, "rich": html or "", "tags": tags or [],
             "attributes": [{"name": k, "value": v} for k, v in (attrs or [])],
             "pins": [], "attachments": attachments or [], "comments": comments or []}
        notes.append(n); by_key[key] = n
        return n

    def comment(name, quote, text, day):
        return {"id": cid(name), "text": text, "quote": quote, "created": f"2026-10-{day}T10:15"}

    def pin(key, color, locked=False):
        n = by_key[key]; j = len(n["pins"])
        p = {"id": uid("pin", key, str(j)), "x": n["width"] - 18, "y": min(38 + 22 * j, n["height"] - 14),
             "color": color, "locked": locked}
        n["pins"].append(p)
        return p["id"]

    def connect(a, b, label="", color="#d4a373", lock=False):
        connections.append({"id": uid("conn", a, b, label), "start_pin_id": pin(a, color, lock),
                            "end_pin_id": pin(b, color, lock), "color": color, "label": label})

    def span(c, text):  # comment marker in the HTML
        return f'<span title="ab-comment:{cid(c)}">{text}</span>'

    # ---------------------------------------------------------------- names
    N = {k: T(*v) for k, v in {
        "mira": ("Mira Valen",) * 2, "kaelen": ("Kaelen Dorn",) * 2, "veyr": ("Lord Veyr",) * 2,
        "tomas": ("Tomas der Fährmann", "Tom the Ferryman"), "isolde": ("Isolde Wren",) * 2,
        "huter": ("Der Aschenhüter", "The Ash Keeper"), "wald": ("Aschenwald", "Ashwood"),
        "burg": ("Burg Hohenfels", "Hohenfels Castle"), "hafen": ("Nebelhafen", "Mistharbor"),
        "archiv": ("Das Archiv von Karrow", "The Archive of Karrow"), "quelle": ("Die Aschenquelle", "The Ash Spring"),
        "orden": ("Orden vom Aschenlicht", "Order of the Ashlight"), "gilde": ("Die Nebelgilde", "The Mist Guild"),
        "stab": ("Der Aschenstab", "The Ash Staff"), "ring": ("Siegelring des Ordens", "Order's Signet Ring"),
        "karte": ("Karte der Nordlande", "Map of the Northlands"),
    }.items()}

    # ================================================================ characters
    mira_c = comment("mira", T("Feuer des Aschenhüters", "fire of the Ash Keeper"),
                     T("Ist der Preis hier schon zu offensichtlich? Erst in Kapitel 3 andeuten.",
                       "Is the price too obvious this early? Hint at it in chapter 3 instead."), "02")
    portrait = add_blob("mira_portrait.png", make_portrait(T("Mira im Schein der Glut", "Mira in the glow of the embers")), "image/png", "portrait")
    mira_att = dict(portrait, inline=True)
    mira_html = (
        f'<p><span style="font-size:15pt;font-weight:600;color:#ffd54f">{N["mira"]}</span></p>'
        f'<p>{T("Aufgewachsen als Waise bei einer Heilerin. Trägt das ", "Raised as an orphan by a healer. She carries the ")}'
        f'{span("mira", T("Feuer des Aschenhüters", "fire of the Ash Keeper"))}'
        f'{T(", ohne zu wissen, was es kostet. Wirkt <b>zäh und trotzig</b>, zweifelt aber ständig an sich.", ", without knowing what it costs. Seems <b>tough and defiant</b> but constantly doubts herself.")}</p>'
        f'<p><i>{T("Innere Reise:", "Inner journey:")}</i> {T("von der Angst vor der eigenen Kraft zur Entscheidung, sie bewusst zu nutzen – und den Preis zu zahlen.", "from fear of her own power to the decision to use it deliberately - and to pay the price.")}</p>'
        f'<p><img src="attachment:{portrait["id"]}" width="200" /></p>')
    note("mira", "character", N["mira"], 0, 0,
         [(T("Alter", "Age"), "19"), (T("Rolle", "Role"), T("Protagonistin", "Protagonist")),
          (T("Beruf", "Occupation"), T("Kräutersammlerin", "Herb gatherer")),
          (T("Herkunft", "Origin"), T("Dorf am Rand des Aschenwalds", "Village at the edge of Ashwood"))],
         T(["held", "magie", "hauptfigur"], ["hero", "magic", "protagonist"]), "", "done", w=290, h=260,
         color="#ffd54f", html=mira_html, attachments=[mira_att], comments=[
             comment("mira", T("Feuer des Aschenhüters", "fire of the Ash Keeper"),
                     T("Ist der Preis hier schon zu offensichtlich? Erst in Kapitel 3 andeuten.",
                       "Is the price too obvious this early? Hint at it in chapter 3 instead."), "02")])
    note("kaelen", "character", N["kaelen"], 330, 0,
         [(T("Alter", "Age"), "34"), (T("Rolle", "Role"), T("Mentor & Verräter", "Mentor & traitor")),
          (T("Beruf", "Occupation"), T("Ritter des Ordens vom Aschenlicht", "Knight of the Order of the Ashlight"))],
         T(["mentor", "geheimnis", "verrat"], ["mentor", "secret", "betrayal"]),
         T("Narbe über dem linken Auge. Spricht selten, hält aber jedes Versprechen – bis auf eines. Seine Loyalität gehört in Wahrheit Lord Veyr, der seine Schwester als Geisel hält.",
           "A scar over his left eye. He rarely speaks but keeps every promise - except one. His true loyalty belongs to Lord Veyr, who holds his sister hostage."), "revise", h=230)
    note("veyr", "character", N["veyr"], 660, 0,
         [(T("Alter", "Age"), "52"), (T("Rolle", "Role"), T("Antagonist", "Antagonist")),
          (T("Beruf", "Occupation"), T("Statthalter der Nordlande", "Governor of the Northlands"))],
         T(["antagonist", "macht"], ["antagonist", "power"]),
         T("Charismatisch, höflich, grausam. Will die Aschenquelle versiegeln – nicht aus Bosheit, sondern aus Angst vor dem, was mit ihr erwacht.",
           "Charismatic, polite, cruel. He wants to seal the Ash Spring - not out of malice but out of fear of what awakens with it."), "draft", h=230)
    note("tomas", "character", N["tomas"], 0, 300,
         [(T("Alter", "Age"), "61"), (T("Rolle", "Role"), T("Nebenfigur, Retter", "Supporting role, rescuer")),
          (T("Beruf", "Occupation"), T("Fährmann", "Ferryman"))], T(["nebenfigur", "humor"], ["supporting", "humor"]),
         T("Redet ohne Punkt und Komma, weiß aber mehr, als er zugibt. Hat vor Jahren Kaelens Schwester über den Fluss gebracht.",
           "Talks without pause but knows more than he admits. Years ago he ferried Kaelen's sister across the river."), "done")
    note("isolde", "character", N["isolde"], 330, 300,
         [(T("Alter", "Age"), "27"), (T("Rolle", "Role"), T("Verbündete, Gelehrte", "Ally, scholar")),
          (T("Beruf", "Occupation"), T("Archivarin", "Archivist"))], T(["verbündete", "wissen"], ["ally", "knowledge"]),
         T("Scharfsinnig, nervös, nie ohne Tintenfleck an den Fingern. Sucht das verbotene Tagebuch der ersten Aschenhüterin.",
           "Sharp, nervous, never without ink on her fingers. She is looking for the forbidden diary of the first Ash Keeper."), "done")
    note("huter", "character", N["huter"], 660, 300,
         [(T("Alter", "Age"), T("über 900", "over 900")), (T("Rolle", "Role"), T("Geisterwesen", "Spirit")),
          (T("Beruf", "Occupation"), T("Wächter der Aschenquelle", "Guardian of the Ash Spring"))],
         T(["magie", "mysterium"], ["magic", "mystery"]),
         T("Spricht mit der Stimme des Waldes. Erinnert sich an alle, die vor Mira das Feuer getragen haben – und an alle, die daran zerbrachen.",
           "Speaks with the voice of the forest. Remembers everyone who carried the fire before Mira - and everyone who broke under it."), "draft")

    # ================================================================ places
    L = lambda k: (T("Region", "Region"), k)
    note("wald", "location", N["wald"], 1060, 0, [(T("Region", "Region"), T("Nordlande", "Northlands")), (T("Typ", "Type"), T("Verbrannter Urwald", "Burnt primeval forest"))],
         T(["wald", "magie"], ["forest", "magic"]),
         T("Seit dem Großen Brand ragen schwarze Stämme in den Himmel, doch zwischen den Wurzeln glimmt es noch. Im Herbst riecht alles nach kaltem Rauch.",
           "Since the Great Fire black trunks reach into the sky, yet between the roots something still glows. In autumn everything smells of cold smoke."), "done")
    note("burg", "location", N["burg"], 1390, 0, [(T("Region", "Region"), T("Mittellande", "Midlands")), (T("Typ", "Type"), T("Festung", "Fortress"))],
         T(["burg", "antagonist"], ["castle", "antagonist"]),
         T("Sitz des Statthalters. Drei Ringmauern, ein Turm, der nie im Schatten liegt.", "Seat of the governor. Three curtain walls and a tower that never lies in shadow."), "draft")
    note("hafen", "location", N["hafen"], 1720, 0, [(T("Region", "Region"), T("Küste", "Coast")), (T("Typ", "Type"), T("Hafenstadt", "Port town"))],
         T(["stadt", "handel"], ["town", "trade"]),
         T("Immer Nebel, immer Möwen. Die Nebelgilde regelt hier, was ein- und ausgeht – auch Geheimnisse.",
           "Always fog, always gulls. The Mist Guild decides what goes in and out here - secrets included."), "done")
    note("archiv", "location", N["archiv"], 1060, 300, [(T("Region", "Region"), T("Mittellande", "Midlands")), (T("Typ", "Type"), T("Bibliothek unter der Stadt", "Library beneath the city"))],
         T(["wissen"], ["knowledge"]), T("Gewölbe aus der Zeit vor dem Orden. Das Pergament flüstert, wenn man zu nahe kommt.",
                                       "Vaults from the time before the Order. The parchment whispers when you come too close."), "done")
    note("quelle", "location", N["quelle"], 1390, 300, [(T("Region", "Region"), T("Nordlande", "Northlands")), (T("Typ", "Type"), T("Heiliger Ort", "Sacred place"))],
         T(["magie", "finale"], ["magic", "finale"]),
         T("Ein Teich aus flüssiger Glut im Herzen des Aschenwalds. Wer hineinsteigt, gibt etwas her – meist eine Erinnerung.",
           "A pool of liquid embers in the heart of Ashwood. Whoever steps in gives something up - usually a memory."), "draft")

    # ================================================ factions / spells / moodboard
    note("orden", "custom_fraktion", N["orden"], 2060, 0, [(T("Anführer", "Leader"), T("Lord Veyr (inoffiziell)", "Lord Veyr (unofficially)")), (T("Ziel", "Goal"), T("Das Feuer unter Kontrolle halten", "Keep the fire under control"))],
         T(["orden", "macht"], ["order", "power"]), T("Gegründet nach dem Fall der Sternwarte. Ursprünglich Hüter des Wissens, heute Werkzeug des Statthalters.",
                                                    "Founded after the fall of the Observatory. Once keepers of knowledge, now the governor's tool."), "draft")
    note("gilde", "custom_fraktion", N["gilde"], 2390, 0, [(T("Anführer", "Leader"), "Madame Corre"), (T("Ziel", "Goal"), T("Handel und Schweigen", "Trade and silence"))],
         T(["gilde", "handel"], ["guild", "trade"]), T("Schmuggler, Händler, Informanten. Neutral, solange die Bezahlung stimmt.", "Smugglers, traders, informants. Neutral as long as the pay is right."), "")
    note("funkenruf", "custom_zauberspruch", T("Funkenruf", "Spark Call"), 2060, 300,
         [(T("Wirkung", "Effect"), T("Beschwört einen kleinen, lenkbaren Funken", "Summons a small, steerable spark")), (T("Preis", "Price"), T("Ein Fingerhut voll Erinnerung", "A thimbleful of memory"))],
         T(["magie", "zauber"], ["magic", "spell"]), T("Der erste Spruch, den Mira instinktiv beherrscht. Wirkt am besten bei Dämmerung.", "The first spell Mira masters by instinct. Works best at dusk."), "done")
    note("aschenschwur", "custom_zauberspruch", T("Aschenschwur", "Ash Oath"), 2390, 300,
         [(T("Wirkung", "Effect"), T("Bindet einen Eid an Feuer", "Binds an oath to fire")), (T("Preis", "Price"), T("Das Gedächtnis an den Schwörenden", "The memory of the one who swears"))],
         T(["magie", "finale", "zauber"], ["magic", "finale", "spell"]), T("Wer ihn bricht, verbrennt von innen. Isolde findet ihn im Tagebuch der ersten Aschenhüterin.", "Whoever breaks it burns from within. Isolde finds it in the diary of the first Ash Keeper."), "revise")
    mood = add_blob("mood_burnt_forest.png", make_mood(T("Stille vor dem Feuer", "Silence before the fire")), "image/png", "mood")
    note("mood", "global_moodboard", T("Moodboard: Verbrannter Wald", "Moodboard: Burnt forest"), 2720, 0,
         [(T("Quelle", "Source"), T("Eigene Skizze", "Own sketch")), (T("Stimmung", "Mood"), T("still, bedrohlich, warm", "quiet, ominous, warm"))],
         T(["stimmung", "wald"], ["mood", "forest"]), T("Referenz für die Eröffnungsszene. Globale Notizart – steht in jedem Notizbuch zur Verfügung.", "Reference for the opening scene. A global note type - available in every notebook."),
         "", attachments=[mood])

    # ================================================================ plot
    note("akt1", "plot", T("Akt I – Der Funke", "Act I - The Spark"), 0, 640, [(T("Akt", "Act"), "1"), (T("Status", "Status"), T("geschrieben", "written"))], T(["struktur"], ["structure"]),
         T("Mira entdeckt ihre Kraft, wird gejagt, flieht nach Nebelhafen.", "Mira discovers her power, is hunted and flees to Mistharbor."), "done", locked=True)
    note("akt2", "plot", T("Akt II – Die Spur", "Act II - The Trail"), 330, 640, [(T("Akt", "Act"), "2"), (T("Status", "Status"), T("in Arbeit", "in progress"))], T(["struktur"], ["structure"]),
         T("Archiv, Tagebuch, Verrat auf Hohenfels. Mira verliert ihren Mentor.", "Archive, diary, betrayal at Hohenfels. Mira loses her mentor."), "draft", locked=True)
    note("akt3", "plot", T("Akt III – Der Preis", "Act III - The Price"), 660, 640, [(T("Akt", "Act"), "3"), (T("Status", "Status"), T("geplant", "planned"))], T(["struktur", "finale"], ["structure", "finale"]),
         T("Die Aschenquelle. Mira muss wählen: Kontrolle oder Opfer.", "The Ash Spring. Mira must choose: control or sacrifice."), "", locked=True)
    wende_html = (f'<p><b>{T("Mitte des Buchs.", "Midpoint of the book.")}</b> '
                  f'{T("Kaelen gesteht – zu spät. Leser sollen den Hinweisen aus Kapitel 1 und 2 folgen können. ", "Kaelen confesses - too late. Readers should be able to follow the hints from chapters 1 and 2. ")}'
                  f'{span("wende", T("Zeitleiste gegen Kapitel 2 prüfen!", "Check the timeline against chapter 2!"))}</p>')
    note("wende", "plot", T("Wendepunkt: Kaelens Geheimnis", "Turning point: Kaelen's secret"), 990, 640, [(T("Akt", "Act"), "2"), (T("Status", "Status"), T("überarbeiten", "revise"))],
         T(["struktur", "verrat", "geheimnis"], ["structure", "betrayal", "secret"]), "", "revise", h=230, html=wende_html,
         comments=[comment("wende", T("Zeitleiste gegen Kapitel 2 prüfen!", "Check the timeline against chapter 2!"), T("Ankunft in Nebelhafen liegt vor dem Brand-Datum?", "Does the arrival in Mistharbor come before the fire date?"), "03")])

    # ================================================================ items
    map_png = add_blob("northlands_map.png", make_map([N["wald"], N["hafen"], N["archiv"], N["burg"], T("Die Nordlande", "The Northlands")]), "image/png", "map")
    route = add_blob("route_notes.txt", T("Route: Aschenwald -> Nebelhafen (2 Tage zu Fuß)\nNebelhafen -> Karrow (Fähre, 1 Tag)\nKarrow -> Hohenfels (Straße, 3 Tage)\n",
                                           "Route: Ashwood -> Mistharbor (2 days on foot)\nMistharbor -> Karrow (ferry, 1 day)\nKarrow -> Hohenfels (road, 3 days)\n").encode("utf-8"), "text/plain", "route")
    note("stab", "item", N["stab"], 1390, 640, [(T("Besitzer", "Owner"), N["mira"]), (T("Herkunft", "Origin"), N["wald"])], T(["artefakt", "magie"], ["artifact", "magic"]),
         T("Ein verkohlter Ast, der nie ganz erkaltet. Verstärkt Funkenruf, verkürzt aber das Gedächtnis.", "A charred branch that never fully cools. It strengthens Spark Call but shortens memory."), "done")
    note("ring", "item", N["ring"], 1720, 640, [(T("Besitzer", "Owner"), N["kaelen"]), (T("Herkunft", "Origin"), N["burg"])], T(["artefakt", "verrat"], ["artifact", "betrayal"]),
         T("Zeigt eine Flamme im Kreis. Lord Veyr trägt das Gegenstück.", "Shows a flame in a circle. Lord Veyr wears the counterpart."), "done")
    note("karte", "item", N["karte"], 2060, 640, [(T("Besitzer", "Owner"), N["tomas"]), (T("Herkunft", "Origin"), N["hafen"])], T(["artefakt"], ["artifact"]),
         T("Handgezeichnet, mit Randnotizen in drei verschiedenen Handschriften. Im Anhang: die Karte und Tomas' Routenliste.", "Hand-drawn, with margin notes in three different handwritings. Attached: the map and Tom's route list."), "", locked=True,
         attachments=[map_png, route])

    # ================================================================ chapters (rich text, comments)
    cm1 = comment("kap1a", T("kaltem Rauch", "cold smoke"), T("Tolles Eröffnungsbild – im Epilog wieder aufgreifen.", "Great opening image - echo it in the epilogue."), "01")
    cm2 = comment("kap1b", T("Funke", "spark"), T("Hier klarmachen, dass nur Mira ihn sehen kann.", "Make clear here that only Mira can see it."), "01")
    k1 = (f'<p>{T("Der Herbst kam früh in den ", "Autumn came early to ")}<b>{N["wald"]}</b>, '
          f'{T("und mit ihm der Geruch von ", "and with it the smell of ")}{span("kap1a", T("kaltem Rauch", "cold smoke"))}'
          f'{T(", der seit dem Großen Brand in den Bäumen hing. ", " that had hung in the trees since the Great Fire. ")}<b>{N["mira"]}</b> '
          f'{T("sammelte Pilze am Waldrand, als der Boden unter ihren Füßen zu summen begann. Es war kein Beben, eher ein Flüstern, das durch ihre Stiefel kroch und sich in ihrer Brust festsetzte. Sie ließ den Korb fallen. Zwischen den verkohlten Wurzeln glomm ein einzelner ",
                "was gathering mushrooms at the edge of the forest when the ground began to hum beneath her feet. It was not a tremor but a whisper that crept through her boots and settled in her chest. She dropped the basket. Between the charred roots a single ")}'
          f'{span("kap1b", f"<span style=\"color:#ff9f43\"><b>{T("Funke", "spark")}</b></span>")}'
          f'{T(" glomm, kaum größer als ein Samenkorn – und er sah sie an.", " glowed, hardly larger than a seed - and it looked at her.")}</p>'
          f'<p>{T("Sie kannte die Geschichten: vom ", "She knew the stories: of the ")}<i>{N["huter"]}</i>'
          f'{T(", der in den Wäldern wachte, von Menschen, die er berührte und die nie wieder dieselben waren. Mira hatte sie immer für ", ", who watched over the forests, of people he touched who were never the same again. Mira had always taken them for ")}'
          f'<span style="background-color:#fff176">{T("Ammenmärchen", "old wives\' tales")}</span>'
          f'{T(" gehalten. Nun streckte sie die Hand aus, und der Funke sprang auf ihre Haut, wärmte sie, ohne zu brennen.", ". Now she reached out, and the spark jumped onto her skin, warming her without burning.")}</p>'
          f'<p style="text-align:center"><i><span style="color:#b388ff">{T("„Endlich“, sagte eine Stimme, die aus dem Wald selbst zu kommen schien. „Es hat so lange gedauert.“", "\"At last,\" said a voice that seemed to come from the forest itself. \"It took so long.\"")}</span></i></p>')
    k2c = comment("kap2", T("Das Mädchen mit dem Feuer", "The girl with the fire"), T("Tomas weiß mehr, als er sagt – hier Vorausdeutung auf Kapitel 4.", "Tom knows more than he says - foreshadowing for chapter 4."), "02")
    k2 = (f'<p>{N["hafen"]} {T("empfing Mira mit Möwengeschrei und dem Gestank von Teer und altem Fisch. ", "welcomed Mira with the cry of gulls and the stench of tar and old fish. ")}{N["tomas"]} '
          f'{T("hatte sie am Morgen aus dem Fluss gezogen, nachdem die Männer des Statthalters sie bis zur Anlegestelle gejagt hatten, und seitdem hörte er nicht auf zu reden. ", "had pulled her from the river that morning after the governor\'s men chased her to the landing, and he had not stopped talking since. ")}'
          f'„{span("kap2", T("Das Mädchen mit dem Feuer", "The girl with the fire"))}{T(" in der Hand“, murmelte er und rieb sich den Bart. „", "\" he muttered, rubbing his beard. \"")}Lord Veyr '
          f'{T("zahlt gutes Gold für so etwas, aber Tomas hat noch nie verkauft, was ihm das Schicksal ins Boot gelegt hat.“", "pays good gold for such a thing, but Tom has never sold what fate put in his boat.\"")}</p>'
          f'<p>{T("In einer Hafenkneipe traf Mira zum ersten Mal ", "In a harbor tavern Mira met ")}<b>{N["isolde"]}</b>'
          f'{T(", eine Archivarin aus Karrow, die nach einem Buch suchte, das es nicht geben durfte. Sie sprach leise und schnell, und als Mira den ", ", an archivist from Karrow searching for a book that should not exist. She spoke quietly and quickly, and when Mira laid the ")}{N["stab"]}'
          f'{T(" auf den Tisch legte, wurde sie noch leiser. „Wo hast du den her?“ – „Aus dem Aschenwald.“ – „Dann haben wir nicht viel Zeit.“", " on the table she grew quieter still. \"Where did you get that?\" - \"From Ashwood.\" - \"Then we have little time.\"")}</p>'
          f'<p><img src="attachment:{map_png["id"]}" width="460" /></p>')
    k3 = (f'<p>{T("Das Archiv von Karrow lag tief unter der Stadt, in Gewölben, die älter waren als der ", "The Archive of Karrow lay deep beneath the city, in vaults older than the ")}{N["orden"]}. '
          f'{N["isolde"]} {T("führte Mira durch Gänge, in denen das Pergament flüsterte, wenn man zu nahe vorbeiging. Staub lag auf allem wie ein Versprechen.", "led Mira through corridors where the parchment whispered when you passed too close. Dust lay on everything like a promise.")}</p>'
          f'<p>{T("In einer verschlossenen Truhe fanden sie das Tagebuch einer Frau, die vor neunhundert Jahren den Aschenhüter gerufen hatte – und den Preis dafür bezahlt. Jede Seite endete mit demselben Satz: ", "In a locked chest they found the diary of a woman who had called the Ash Keeper nine hundred years ago - and paid the price. Every page ended with the same sentence: ")}'
          f'<b><i>{T("Wer das Feuer trägt, trägt auch das Vergessen.", "Whoever carries the fire also carries forgetting.")}</i></b> '
          f'{T("Mira las ihn dreimal, bis die Buchstaben vor ihren Augen verschwammen. Dann hörte sie Schritte. Jemand folgte ihnen durch die Regale.", "Mira read it three times until the letters blurred. Then she heard footsteps. Someone was following them through the shelves.")} '
          f'<a href="https://example.org/diary-of-the-first-keeper">{T("(Quelle: Tagebuch-Edition)", "(source: diary edition)")}</a></p>')
    k4c = comment("kap4", T("Siegelring", "signet ring"), T("Den Ring schon in Kapitel 1 beiläufig erwähnen.", "Mention the ring casually as early as chapter 1."), "04")
    k4 = (f'<p>{N["burg"]} {T("thronte über dem Tal wie ein Raubvogel. ", "perched above the valley like a bird of prey. ")}{N["kaelen"]} '
          f'{T("hatte Mira versprochen, dass sie dort sicher wäre, und er hatte es geglaubt, als er es sagte. Erst als sich die Tore hinter ihr schlossen und Lord Veyr lächelnd die Treppe herabkam, verstand sie, wessen ", "had promised Mira she would be safe there, and he had believed it when he said it. Only when the gates closed behind her and Lord Veyr came smiling down the stairs did she understand whose ")}'
          f'{span("kap4", T("Siegelring", "signet ring"))}{T(" er am Finger trug.", " he wore on his finger.")}</p>'
          f'<p>{T("„Du hättest es wissen müssen“, sagte Kaelen leise. „Ich habe dich nie belogen. Ich habe dir nur nicht alles erzählt.“", "\"You should have known,\" Kaelen said quietly. \"I never lied to you. I just did not tell you everything.\"")}</p>'
          f'<p><span style="color:#ff5c5c"><b>{T("Mira spürte den Funken in ihrer Brust aufflammen. Zum ersten Mal wollte sie, dass er brannte.", "Mira felt the spark flare in her chest. For the first time she wanted it to burn.")}</b></span></p>')
    chapters = [
        ("1", T("Kapitel 1 – Der erste Funke", "Chapter 1 - The First Spark"), "done", k1, [cm1, cm2], [], None),
        ("2", T("Kapitel 2 – Nebel über dem Hafen", "Chapter 2 - Fog over the Harbor"), "done", k2, [k2c], [dict(map_png, inline=True)], None),
        ("3", T("Kapitel 3 – Das Archiv", "Chapter 3 - The Archive"), "draft", k3, [], [], None),
        ("4", T("Kapitel 4 – Verrat auf Hohenfels", "Chapter 4 - Betrayal at Hohenfels"), "revise", k4, [k4c], [], None),
        ("5", T("Kapitel 5 – Die Quelle", "Chapter 5 - The Spring"), "draft", None, [], [],
         T("ENTWURF – Die Aschenquelle liegt im Herzen des Aschenwalds. Der Aschenhüter wartet. Mira muss Funkenruf und Aschenschwur verbinden; der Preis ist ihre Kindheit. Offen: Wie viel von Isolde bleibt im Text sichtbar?",
          "DRAFT - The Ash Spring lies in the heart of Ashwood. The Ash Keeper waits. Mira must combine Spark Call and Ash Oath; the price is her childhood. Open: how much of Isolde stays visible in the text?")),
        ("6", T("Kapitel 6 – Asche und Morgenlicht", "Chapter 6 - Ash and Morning Light"), "", None, [], [],
         T("TODO: Epilog. Morgenlicht über dem Aschenwald. Was bleibt von Mira, wenn der Preis bezahlt ist?", "TODO: Epilogue. Morning light over Ashwood. What remains of Mira once the price is paid?")),
    ]
    status_word = {"done": T("fertig", "done"), "draft": T("Entwurf", "draft"), "revise": T("überarbeiten", "revise"), "": T("offen", "open")}
    for i, (nr, title, status, html, cms, atts, plain) in enumerate(chapters):
        content = plain or ""
        n = note(f"kap{nr}", "chapter", title, i * 340, 980,
                 [(T("Nummer", "Number"), nr), (T("Status", "Status"), status_word[status]), (T("Wortzahl", "Word count"), "0")],
                 [T("kapitel", "chapter"), f"{T('akt', 'act')}{1 if i < 2 else 2 if i < 4 else 3}"], content, status, w=310, h=270,
                 html=html, attachments=atts, comments=[c for c in cms if True])
        n["attributes"][2]["value"] = str(len(n["content"].split()))

    # ================================================================ scenes
    scenes = [
        ("1.1", T("Szene 1.1 – Funken im Unterholz", "Scene 1.1 - Sparks in the Undergrowth"), "14.09.1203", "21:40", N["wald"], T("Mira (personal)", "Mira (close third)"), "done",
         T("Der Große Brand, wie Mira ihn als Kind erinnert: Rauch, Schreie, eine Hand, die sie aus dem Feuer zieht. Schnitt zurück in die Gegenwart.", "The Great Fire as Mira remembers it as a child: smoke, screams, a hand pulling her from the flames. Cut back to the present.")),
        ("1.2", T("Szene 1.2 – Der sprechende Wald", "Scene 1.2 - The Speaking Forest"), "03.10.1203", "17:05", N["wald"], T("Mira (personal)", "Mira (close third)"), "done",
         T("Der Aschenhüter spricht zum ersten Mal. Mira rennt – und der Wald lässt sie nicht los.", "The Ash Keeper speaks for the first time. Mira runs - and the forest will not let go of her.")),
        ("2.1", T("Szene 2.1 – Möwen und Schatten", "Scene 2.1 - Gulls and Shadows"), "18.09.1203", "08:30", N["hafen"], T("Mira (personal)", "Mira (close third)"), "done",
         T("Ankunft in Nebelhafen. Tomas zeigt ihr, wie man in dieser Stadt verschwindet.", "Arrival in Mistharbor. Tom shows her how to disappear in this town.")),
        ("3.1", T("Szene 3.1 – Das flüsternde Pergament", "Scene 3.1 - The Whispering Parchment"), "02.10.1203", "23:10", N["archiv"], T("Isolde (personal)", "Isolde (close third)"), "draft",
         T("Perspektivwechsel: Isolde sieht, wie Mira beim Lesen zu glühen beginnt, und weiß, dass sie gerade etwas Gefährliches in die Welt gelassen hat.", "Change of perspective: Isolde watches Mira begin to glow as she reads and knows she has just released something dangerous.")),
        ("4.1", T("Szene 4.1 – Das Tor schließt sich", "Scene 4.1 - The Gate Closes"), "11.10.1203", "23:45", N["burg"], T("Kaelen (personal)", "Kaelen (close third)"), "revise",
         T("Kaelens Sicht auf den Verrat. Er zählt die Schritte bis zur Zelle und versucht, sich nicht zu erinnern, wie sie ihm vertraut hat.", "Kaelen's view of the betrayal. He counts the steps to the cell and tries not to remember how she trusted him.")),
        ("5.1", T("Szene 5.1 – Glut im Wasser", "Scene 5.1 - Embers in the Water"), "31.10.1203", "00:00", N["quelle"], T("Mira (personal)", "Mira (close third)"), "draft",
         T("Mira steigt in die Quelle. Entwurf: Dialog mit dem Aschenhüter noch zu erklärend, später kürzen.", "Mira steps into the spring. Draft: the dialogue with the Ash Keeper still explains too much - trim later.")),
    ]
    for i, (nr, title, datum, uhr, ort, persp, status, text) in enumerate(scenes):
        note(f"szene{nr}", "scene", title, i * 340, 1320,
             [(T("Nummer", "Number"), nr), (T("Datum", "Date"), datum), (T("Uhrzeit", "Time"), uhr), (T("Ort", "Place"), ort), (T("Perspektive", "Perspective"), persp)],
             [T("szene", "scene")], text, status, w=310, h=250)

    # ================================================================ events (timeline)
    events = [
        ("ev_sternwarte", T("Der Fall der Sternwarte", "The Fall of the Observatory"), "1187", "", N["wald"], [T("geschichte", "history")], T("Nur das Jahr ist bekannt – die Chroniken widersprechen sich.", "Only the year is known - the chronicles contradict each other.")),
        ("ev_orden", T("Gründung des Ordens vom Aschenlicht", "Founding of the Order of the Ashlight"), "03.04.1190", "10:00", N["burg"], [T("geschichte", "history"), T("orden", "order")], T("Offizielle Gründung. Das Gründungsdokument fehlt im Archiv.", "Official founding. The founding document is missing from the archive.")),
        ("ev_duerre", T("Das Dürre-Jahr", "The Year of Drought"), "07.1195", "", T("Nordlande", "Northlands"), [T("geschichte", "history")], T("Nur Monat und Jahr bekannt.", "Only month and year are known.")),
        ("ev_geburt", T("Mira wird geboren", "Mira is born"), "21.12.1184", "05:30", T("Dorf am Aschenwald", "Village at Ashwood"), ["mira", T("geschichte", "history")], T("Geburt in der längsten Nacht des Jahres.", "Born on the longest night of the year.")),
        ("ev_brand", T("Der Große Brand", "The Great Fire"), "14.09.1203", "22:15", N["wald"], [T("wendepunkt", "turning-point")], T("Brand, der den Wald verändert hat. Auslöser ungeklärt.", "The fire that changed the forest. Cause unknown.")),
        ("ev_hafen", T("Ankunft in Nebelhafen", "Arrival in Mistharbor"), "18.09.1203", "08:30", N["hafen"], [T("handlung", "plot")], ""),
        ("ev_archiv", T("Entdeckung des Tagebuchs", "Discovery of the diary"), "02.10.1203", "23:10", N["archiv"], [T("handlung", "plot"), T("wissen", "knowledge")], ""),
        ("ev_verrat", T("Kaelens Verrat", "Kaelen's betrayal"), "11.10.1203", "23:45", N["burg"], [T("handlung", "plot"), T("verrat", "betrayal")], ""),
        ("ev_quelle", T("Entzündung der Quelle", "Ignition of the spring"), "31.10.1203", "00:00", N["quelle"], [T("finale", "finale")], ""),
        ("ev_morgen", T("Epilog: Morgenlicht", "Epilogue: Morning light"), "01.11.1203", "06:12", N["wald"], [T("epilog", "epilogue")], ""),
    ]
    for i, (key, title, datum, uhr, ort, tags, text) in enumerate(events):
        note(key, "event", title, (i % 5) * 340, 1690 + (i // 5) * 240,
             [(T("Datum", "Date"), datum), (T("Uhrzeit", "Time"), uhr), (T("Ort", "Place"), ort)], tags, text, "", w=290, h=210)

    # ================================================================ ideas, research, notes
    note("idee1", "idea", T("Idee: Spiegelwelt aus Asche", "Idea: Mirror world of ash"), 0, 2210, [], [T("idee", "idea"), T("fortsetzung", "sequel")],
         T("Band 2: Hinter der Quelle liegt ein Spiegelbild der Welt, in dem alles verbrannt ist. Wer dort stirbt, erlischt für immer.", "Book 2: Beyond the spring lies a mirror of the world in which everything has burned. Whoever dies there is extinguished forever."), "")
    note("idee2", "idea", T("Idee: Prolog aus Sicht des Hüters", "Idea: Prologue from the Keeper's view"), 340, 2210, [], [T("idee", "idea"), T("prolog", "prologue")],
         T("Ein kurzer Prolog, nur 300 Wörter: Der Hüter sieht den ersten Funken in einem Kind und erinnert sich.", "A short prologue, only 300 words: the Keeper sees the first spark in a child and remembers."), "draft")
    ritual = add_blob("fire_rituals_notes.md", T("# Feuerrituale\n\n- Johannisfeuer\n- Reinigungsfeuer\n- Gottesurteile\n\nFür den Aschenschwur: Eide wurden über Flammen geschworen.\n", "# Fire rituals\n\n- Midsummer fires\n- Cleansing fires\n- Trials by ordeal\n\nFor the Ash Oath: oaths were sworn over flames.\n").encode("utf-8"), "text/markdown", "ritual")
    res1_html = (f'<p>{T("Johannisfeuer, Reinigungsfeuer, Gottesurteile. Für den Aschenschwur interessant: Eide wurden über Flammen geschworen. ", "Midsummer fires, cleansing fires, trials by ordeal. Interesting for the Ash Oath: oaths were sworn over flames. ")}'
                 f'<a href="https://example.org/fire-rituals">{T("Zur Quelle im Browser öffnen (Strg+Klick)", "Open the source in the browser (Ctrl+click)")}</a></p>')
    note("res1", "research", T("Recherche: Feuerrituale im Mittelalter", "Research: Fire rituals in the Middle Ages"), 680, 2210, [(T("Quelle", "Source"), T("Fachbuch, Kap. 7", "Textbook, ch. 7")), (T("Link", "Link"), "https://example.org/fire-rituals")],
         [T("recherche", "research"), T("magie", "magic")], "", "", html=res1_html, attachments=[ritual])
    note("res2", "research", T("Recherche: Schiffsverkehr an der Nordküste", "Research: Shipping on the north coast"), 1020, 2210, [(T("Quelle", "Source"), T("Museum Nebelhafen", "Mistharbor Museum")), (T("Link", "Link"), "https://example.org/coast")],
         [T("recherche", "research"), "nebelhafen" if de else "mistharbor"],
         T("Fährzeiten, Tiefgang der Boote, Lotsenwesen. Tomas' Fähre braucht bei Ebbe Hilfe von der Gilde.", "Ferry times, draft of the boats, pilotage. Tom's ferry needs help from the guild at low tide."), "")
    note("stil", "note", T("Stilguide", "Style guide"), 1360, 2210, [(T("Status", "Status"), T("gültig", "valid"))], [T("stil", "style"), T("regeln", "rules")],
         T("Personale Erzählperspektive, Präteritum. Keine Ortsnamen ohne Sinneseindruck. Keine Erklärdialoge länger als drei Zeilen. Rauch, Asche und Glut sparsam einsetzen – nicht jede Szene braucht Feuer.",
           "Close third person, past tense. No place names without a sensory impression. No explanatory dialogue longer than three lines. Use smoke, ash and embers sparingly - not every scene needs fire."), "done", color="#fff59d", locked=True)
    note("fragen", "note", T("Offene Fragen", "Open questions"), 1700, 2210, [], [T("todo", "todo")],
         T("Warum hält Veyr Kaelens Schwester? Wann erfährt Mira vom Preis? Wie viel verrät das Tagebuch? Muss Isolde überleben?", "Why does Veyr hold Kaelen's sister? When does Mira learn of the price? How much does the diary reveal? Must Isolde survive?"), "revise", color="#ffe082")

    # ================================================================ threads
    BLUE, RED, GREEN, YELLOW, ORANGE, VIOLET, GREY = "#4da6ff", "#e8505b", "#4cc38a", "#ffd54f", "#ff9f43", "#b388ff", "#9e9e9e"
    c = connect
    c("mira", "kaelen", T("Schülerin von", "student of"), BLUE); c("kaelen", "veyr", T("dient heimlich", "secretly serves"), RED)
    c("mira", "isolde", T("Verbündete", "ally"), GREEN); c("mira", "tomas", T("wird gerettet von", "rescued by"), YELLOW)
    c("mira", "huter", T("Seelenband", "soul bond"), VIOLET); c("mira", "wald", T("wächst auf in", "grows up in"), GREEN)
    c("mira", "stab", T("besitzt", "owns"), YELLOW); c("mira", "funkenruf", T("beherrscht", "masters"), VIOLET)
    c("kaelen", "ring", T("trägt", "wears"), RED); c("kaelen", "orden", T("Mitglied", "member"), BLUE)
    c("veyr", "orden", T("kontrolliert", "controls"), RED); c("veyr", "burg", T("herrscht über", "rules"), RED)
    c("tomas", "hafen", T("lebt in", "lives in"), GREEN); c("tomas", "karte", T("besitzt", "owns"), YELLOW)
    c("isolde", "archiv", T("arbeitet in", "works in"), GREEN); c("isolde", "aschenschwur", T("findet", "finds"), VIOLET)
    c("huter", "quelle", T("bewacht", "guards"), VIOLET); c("gilde", "hafen", T("beherrscht", "controls"), ORANGE)
    c("res1", "aschenschwur", T("inspiriert", "inspires"), GREY); c("res2", "hafen", T("beschreibt", "describes"), GREY)
    c("idee1", "quelle", T("baut auf", "builds on"), GREY); c("mood", "wald", T("zeigt", "depicts"), GREY)
    c("akt1", "akt2", T("führt zu", "leads to"), ORANGE, lock=True); c("akt2", "akt3", T("führt zu", "leads to"), ORANGE, lock=True)
    c("wende", "kaelen", T("betrifft", "concerns"), RED); c("wende", "kap4", T("liegt in", "is in"), BLUE)
    for a, b in zip(range(1, 6), range(2, 7)):
        c(f"kap{a}", f"kap{b}", T("folgt", "follows"), GREY)
    c("akt1", "kap1", T("umfasst", "comprises"), BLUE)
    for nr in ("1.1", "1.2"): c(f"szene{nr}", "kap1", T("gehört zu", "belongs to"), BLUE)
    for nr, k in (("2.1", "kap2"), ("3.1", "kap3"), ("4.1", "kap4"), ("5.1", "kap5")): c(f"szene{nr}", k, T("gehört zu", "belongs to"), BLUE)
    for ev, sc in (("ev_brand", "szene1.1"), ("ev_hafen", "szene2.1"), ("ev_archiv", "szene3.1"), ("ev_verrat", "szene4.1"), ("ev_quelle", "szene5.1")):
        c(ev, sc, T("erzählt in", "told in"), ORANGE)
    c("ev_geburt", "mira", T("betrifft", "concerns"), YELLOW); c("ev_orden", "orden", T("betrifft", "concerns"), BLUE)
    pin("stil", VIOLET); pin("fragen", RED); pin("idee2", GREEN)          # decorative pins without threads

    tag_memory = sorted({t for n in notes for t in n["tags"]} | {T("zukunft", "future"), T("figur", "character"), "mira"})

    book = {
        "title": T("Die Chroniken von Aschenwald", "The Ashwood Chronicles"), "author": T("Beispielautorin", "Example Author"),
        "genre": "Dark Fantasy", "category": T("Romane", "Novels"), "color": "#6d4c41", "target_words": 90000, "deadline": T("30.11.2026", "2026-11-30"),
        "description": T("Als die 19-jährige Mira Valen im Aschenwald einen glimmenden Funken findet, ahnt sie nicht, dass er ihr Gedächtnis kostet. Gejagt vom Statthalter und verraten von ihrem Mentor, muss sie den Aschenhüter finden – und entscheiden, was ihr Erinnerungen wert sind.\n\nDiese Datei ist ein Showcase: Sie zeigt alle Funktionen von AuthorBoard mit einem fiktiven Romanprojekt.",
                         "When 19-year-old Mira Valen finds a glowing spark in Ashwood she has no idea it will cost her her memory. Hunted by the governor and betrayed by her mentor, she must find the Ash Keeper - and decide what her memories are worth.\n\nThis file is a showcase: it demonstrates every feature of AuthorBoard with a fictional novel project."),
        "attributes": [{"name": T("Arbeitstitel", "Working title"), "value": T("Asche & Morgenlicht", "Ash & Morning Light")},
                       {"name": T("Reihe", "Series"), "value": T("Band 1 von 3", "Book 1 of 3")},
                       {"name": T("Zielgruppe", "Audience"), "value": "Young Adult / Adult"},
                       {"name": T("Erzählperspektive", "Narrative voice"), "value": T("Personal, Präteritum", "Close third, past tense")},
                       {"name": T("Lektorat", "Editing"), "value": T("ab Januar", "from January")}],
    }

    return {"version": 4, "book": book, "custom_types": custom_types, "known_tags": tag_memory, "notes": notes,
            "connections": connections,
            "attachment_data": {k: base64.b64encode(v).decode("ascii") for k, v in blobs.items()}}


def main():
    out = os.path.join(ROOT, "showcase")
    os.makedirs(out, exist_ok=True)
    for lang, name in (("de", "Die Chroniken von Aschenwald (Showcase).json"),
                       ("en", "The Ashwood Chronicles (Showcase).json")):
        data = build(lang)
        path = os.path.join(out, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"{name}: {len(data['notes'])} notes, {len(data['connections'])} threads, "
              f"{len(data['attachment_data'])} attachments, {os.path.getsize(path) // 1024} KB")


if __name__ == "__main__":
    main()
