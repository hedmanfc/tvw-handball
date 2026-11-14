#!/usr/bin/env python3
"""Prüft, ob gerade ein Spiel angepfiffen wurde, dessen Liveticker-ID (meeting) noch fehlt.

Aufruf: python tools/live_check.py data
Schreibt "go=true" oder "go=false" in die Datei $GITHUB_OUTPUT (sonst auf die Konsole).
Läuft alle 5 Minuten, ist aber nur eine Dateiprüfung und dauert wenige Sekunden.
Ein Update wird ausgelöst, wenn ein Spiel in den letzten 15 Minuten begonnen hat (Anpfiff bis 15 Minuten danach,
also etwa beim Anpfiff und 5 und 10 Minuten später) und für dieses Spiel noch keine ID vorliegt.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FENSTER_MIN = 15
ordner = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
jetzt = datetime.now(ZoneInfo("Europe/Berlin"))
heute = jetzt.strftime("%Y-%m-%d")
treffer = []
for datei in sorted(ordner.glob("nuliga_*-26-27_spielplan.json")):  # nur die laufende Saison
    for p in json.loads(datei.read_text(encoding="utf-8")):
        if p.get("datum") != heute or p.get("meeting") or not p.get("zeit"):
            continue
        try:
            h, m = map(int, p["zeit"].split(":"))
        except ValueError:
            continue
        seit = (jetzt.hour * 60 + jetzt.minute) - (h * 60 + m)
        if 0 <= seit < FENSTER_MIN:
            treffer.append(f'{p["heim"]} - {p["gast"]} ({p["zeit"]}, seit {seit} Min.)')
go = "true" if treffer else "false"
print(f"{jetzt:%d.%m. %H:%M} Uhr: {len(treffer)} Spiel(e) ohne Ticker-ID im Anpfiff-Fenster", *treffer, sep="\n  ")
ziel = os.environ.get("GITHUB_OUTPUT")
if ziel:
    with open(ziel, "a") as f:
        f.write(f"go={go}\n")
else:
    print("go=" + go)
