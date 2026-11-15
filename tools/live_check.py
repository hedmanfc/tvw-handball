#!/usr/bin/env python3
"""Prüft, ob gerade ein Spiel angepfiffen wurde, dessen Liveticker-ID (meeting) noch fehlt.

Aufruf: python tools/live_check.py data
Schreibt "go=true" oder "go=false" in die Datei $GITHUB_OUTPUT (sonst auf die Konsole).
Läuft alle 5 Minuten, ist aber nur eine Dateiprüfung und dauert wenige Sekunden.
Ein Update wird ausgelöst, wenn ein Spiel in höchstens 5 Minuten beginnt oder vor höchstens 15 Minuten begonnen hat und für
dieses Spiel noch keine ID vorliegt. Sobald die ID da ist, hören die Läufe für dieses Spiel auf.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VOR_MIN = 5    # ab 5 Minuten vor Anpfiff prüfen, ob nuLiga die Spiel-ID schon geliefert hat
NACH_MIN = 15  # und bis 15 Minuten nach Anpfiff
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
        if -VOR_MIN <= seit < NACH_MIN:
            treffer.append(f'{p["heim"]} - {p["gast"]} ({p["zeit"]}, seit {seit} Min.)')
go = "true" if treffer else "false"
print(f"{jetzt:%d.%m. %H:%M} Uhr: {len(treffer)} Spiel(e) ohne Ticker-ID im Zeitfenster", *treffer, sep="\n  ")
ziel = os.environ.get("GITHUB_OUTPUT")
if ziel:
    with open(ziel, "a") as f:
        f.write(f"go={go}\n")
else:
    print("go=" + go)
