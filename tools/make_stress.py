#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate stress-test boards (Optimization.md Phase 0).

    python tools/make_stress.py 500
    python tools/make_stress.py 2000 --threads 2
    python tools/make_stress.py 5000 --out /tmp/stress.json

Writes a valid AuthorBoard JSON file you can open with *File -> Open* to
measure open time, pan/zoom FPS and selection latency.
"""
import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from models import (
    AttributeData, ConnectionData, NoteData, NoteTypeData, PinData,
    ProjectData, BUILTIN_NOTE_TYPES,
)
from storage import Storage

WORDS = ("fire ash forest castle river map sword oath memory spark ember "
         "shadow light stone wind rain tower gate bridge harbor archive "
         "keeper order guild spell price secret betray rescue journey").split()


def rand_text(rng, n):
    return " ".join(rng.choice(WORDS) for _ in range(n))


def build(n_notes, threads_per_note, out):
    rng = random.Random(42)
    project = ProjectData()
    types = ["note", "character", "location", "chapter", "scene", "event", "idea"]
    cols = {t.key: t.color for t in BUILTIN_NOTE_TYPES}

    notes = []
    for i in range(n_notes):
        typ = types[i % len(types)]
        n = NoteData(
            title=f"{typ.title()} {i}",
            content=rand_text(rng, rng.randint(5, 120)),
            x=(i % 40) * 320.0 + rng.uniform(-20, 20),
            y=(i // 40) * 260.0 + rng.uniform(-20, 20),
            width=260, height=200,
            color=cols.get(typ, "#fff176"), note_type=typ,
            status=rng.choice(["", "draft", "revise", "done"]),
            tags=[rng.choice(WORDS) for _ in range(rng.randint(0, 3))],
            attributes=[AttributeData(
                "Date", f"{rng.randint(1100,1300)}-0{rng.randint(1,9)}-1{rng.randint(0,9)}")],
            pins=[PinData(x=240, y=30)],
        )
        notes.append(n)
        project.notes.append(n)

    for n in notes:
        for _ in range(threads_per_note):
            other = rng.choice(notes)
            if other is n:
                continue
            project.connections.append(ConnectionData(
                start_pin_id=n.pins[0].id,
                end_pin_id=other.pins[0].id,
                label=rng.choice(["", "ally", "rival", "mentor"]),
            ))

    project.custom_types = [NoteTypeData("custom_spell", "Spell", "#b2dfdb", ["Cost"])]

    with open(out, "w", encoding="utf-8") as f:
        json.dump(Storage.to_dict(project), f, ensure_ascii=False)
    print(f"{out}: {n_notes} notes, {len(project.connections)} threads, "
          f"{os.path.getsize(out)//1024} KB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("notes", type=int)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    out = a.out or os.path.join(ROOT, "showcase", f"_stress_{a.notes}.json")
    build(a.notes, a.threads, out)