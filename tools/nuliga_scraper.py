#!/usr/bin/env python3
"""
nuLiga-Scraper für TV Wächtersbach (mehrere Mannschaften und Saisons)

Holt je Staffel den kompletten Spielplan und alle Spielberichte und wertet sie aus.

Einmalig installieren:   pip install requests beautifulsoup4
Alles holen:             python nuliga_scraper.py
Nur eine Staffel:        python nuliga_scraper.py --nur erste-26-27
Liste der Staffeln:      python nuliga_scraper.py --liste

Ergebnis (im selben Ordner), je Staffel <key>:
  nuliga_<key>_alle.json      -> alle Spiele der Staffel mit Spielverlauf
  nuliga_<key>_spielplan.json -> kompletter Spielplan (auch noch offene Spiele)
  nuliga_<key>_kompakt.json   -> nur euer Team, mit Spielern
  nuliga_cache.json           -> merkt sich bereits geladene Berichte (abgeschlossene Saisons ändern sich nie)

Zusätzlich für die aktuelle erste Mannschaft (wie bisher):
  nuliga_alle.json und nuliga_kompakt.json

Zum Aktualisieren der App schickst du Claude die *_alle.json-Dateien (oder den ganzen Ordner als ZIP).
Das Skript wartet zwischen den Abrufen kurz, um nuLiga nicht zu belasten.
"""
import argparse
import html as htmllib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://hhv-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/"
PAUSE = 0.8  # Sekunden zwischen zwei Abrufen

# key: (Saison, Gruppen-ID, Teamname in dieser Staffel, Anzeigename)
STAFFELN = {
    "erste-26-27":  ("Offenbach-Hanau 26/27", "492715", "TV Wächtersbach",    "1. Mannschaft 2026/27 (Bezirksoberliga)"),
    "zweite-26-27": ("Offenbach-Hanau 26/27", "492052", "TV Wächtersbach II", "2. Mannschaft 2026/27 (Bezirksklasse)"),
    "erste-25-26":  ("Offenbach-Hanau 25/26", "421685", "TV Wächtersbach",    "1. Mannschaft 2025/26 (Bezirksoberliga)"),
    "zweite-25-26": ("Offenbach-Hanau 25/26", "421487", "TV Wächtersbach II", "2. Mannschaft 2025/26 (2. Bezirksklasse)"),
}


def new_session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (privates Handball-Team-Projekt)"
    return s


def get(session, page, champ, group, **params):
    params.update(championship=champ, group=group)
    r = session.get(BASE + page, params=params, timeout=30)
    r.raise_for_status()
    time.sleep(PAUSE)
    return r.text, r.url


def meeting_from_href(href):
    q = parse_qs(urlparse(htmllib.unescape(href)).query)
    return q["meeting"][0] if q.get("meeting") else None


def parse_spielplan(text):
    """Liest die Spielplan-Tabelle (Gesamt). Datum wird bei Folgezeilen des Tages übernommen."""
    soup = BeautifulSoup(text, "html.parser")
    plan, datum = [], None
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        txt = [c.get_text(" ", strip=True) for c in cells]
        zi = next((i for i, x in enumerate(txt) if re.search(r"\b\d\d:\d\d\b", x) and not re.search(r"\d\d\.\d\d\.\d{4}", x)), None)
        if zi is None or len(txt) < zi + 6:
            continue
        for x in txt[:zi]:
            m = re.search(r"(\d\d)\.(\d\d)\.(\d{4})", x)
            if m:
                datum = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        meeting = None
        for a in tr.find_all("a", href=True):
            if "groupMeetingReport" in a["href"]:
                meeting = meeting_from_href(a["href"])
        m = re.search(r"\b(\d\d:\d\d)\b", txt[zi])
        erg = re.match(r"^(\d+):(\d+)", txt[zi + 5])
        plan.append({
            "datum": datum, "zeit": m.group(1), "halle_code": txt[zi + 1], "nr": txt[zi + 2],
            "heim": txt[zi + 3], "gast": txt[zi + 4], "ergebnis_roh": txt[zi + 5],
            "tore_heim": int(erg.group(1)) if erg else None,
            "tore_gast": int(erg.group(2)) if erg else None,
            "meeting": meeting,
        })
    return plan


def spielplan(champ, group):
    session = new_session()
    text, _ = get(session, "groupPage", champ, group, displayTyp="vorrunde", displayDetail="meetings")
    return parse_spielplan(text)


def rows_of(table):
    return [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]


def to_int(x):
    m = re.search(r"\d+", x or "")
    return int(m.group()) if m else 0


def parse_report(text, meeting):
    soup = BeautifulSoup(text, "html.parser")
    g = {"id": meeting, "status": "genehmigt" if "Spielbericht (genehmigt)" in soup.get_text() else "offen"}
    player_tables, events = [], []
    for t in soup.find_all("table"):
        rows = rows_of(t)
        if not rows:
            continue
        first = [r[0] for r in rows if r]
        if "Spielnummer" in first:
            g["nr"] = rows[0][1]
            m = re.search(r"(\d\d)\.(\d\d)\.(\d{4}).*?(\d\d:\d\d)", rows[1][1])
            if m:
                g["datum"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                g["zeit"] = m.group(4)
            g["ort"] = rows[2][1]
            g["heim"], g["gast"] = rows[1][4], rows[2][4]
        elif "Trikot" in first:
            start = first.index("Trikot") + 1
            spieler = []
            for r in rows[start:]:
                r = (r + [""] * 12)[:12]
                if not r[0].isdigit():
                    continue  # Betreuer (A, B, C)
                t7 = re.match(r"(\d+)/(\d+)", r[5])
                spieler.append({
                    "nr": int(r[0]), "name": r[1], "tore": to_int(r[4]),
                    "tore7": int(t7.group(1)) if t7 else 0, "versuche7": int(t7.group(2)) if t7 else 0,
                    "gelb": bool(r[6]), "zeitstrafen": sum(1 for x in r[7:10] if x),
                    "rot": bool(r[10] or r[11]),
                })
            player_tables.append(spieler)
        elif rows[0][:3] == ["Team", "Zeit", "Stand"]:
            for r in rows[1:]:
                r = (r + [""] * 5)[:5]
                m = re.match(r"(\d+)\s+(.*)", r[4])
                events.append({"seite": {"Heim": "heim", "Gast": "gast"}.get(r[0], ""), "zeit": r[1], "stand": r[2],
                               "ereignis": r[3], "nr": int(m.group(1)) if m else None,
                               "name": m.group(2) if m else r[4]})
        elif "Ergebnis" in first:
            for r in rows:
                if r[0] == "Ergebnis":
                    m = re.match(r"(\d+):(\d+)(?:\s*\((\d+):(\d+)\))?", r[1])
                    if m:
                        g["tore_heim"], g["tore_gast"] = int(m.group(1)), int(m.group(2))
                        if m.group(3):
                            g["hz_heim"], g["hz_gast"] = int(m.group(3)), int(m.group(4))
    if len(player_tables) == 2:
        g["spieler"] = {"heim": player_tables[0], "gast": player_tables[1]}
    g["verlauf"] = events
    return g


def fetch_report(meeting, champ, group):
    """Neue Sitzung pro Bericht, prüft ob wirklich der gewünschte Bericht geliefert wurde."""
    for versuch in range(3):
        session = new_session()
        text, url = get(session, "groupMeetingReport", champ, group, meeting=meeting)
        if f"meeting={meeting}" in url:
            g = parse_report(text, meeting)
            g["saison"], g["gruppe"] = champ, group
            return g
        print(f"  Bericht {meeting}: nuLiga lieferte einen anderen Bericht, Versuch {versuch + 2}/3 ...")
    print(f"  Bericht {meeting} übersprungen.")
    return None


def aggregate(spiele, nur_team=None):
    agg = {}
    for s in spiele:
        if "spieler" not in s:
            continue
        for seite in ("heim", "gast"):
            verein = s[seite]
            if nur_team and verein != nur_team:
                continue
            for p in s["spieler"][seite]:
                a = agg.setdefault((verein, p["name"]), dict(
                    name=p["name"], verein=verein, spiele=0, tore=0, tore7=0, versuche7=0,
                    zeitstrafen=0, gelb=0, rot=0))
                a["spiele"] += 1
                a["tore"] += p["tore"]
                a["tore7"] += p["tore7"]
                a["versuche7"] += p["versuche7"]
                a["zeitstrafen"] += p["zeitstrafen"]
                a["gelb"] += int(p["gelb"])
                a["rot"] += int(p["rot"])
    out = list(agg.values())
    for a in out:
        a["tore_pro_spiel"] = round(a["tore"] / a["spiele"], 2) if a["spiele"] else 0
    return sorted(out, key=lambda a: (-a["tore"], a["name"]))


def kompakt(spiele, team):
    eigene = []
    for s in sorted(spiele, key=lambda s: (s.get("datum", ""), s.get("zeit", ""))):
        if team not in (s.get("heim"), s.get("gast")) or "tore_heim" not in s:
            continue
        seite = "heim" if s["heim"] == team else "gast"
        gegner = s["gast" if seite == "heim" else "heim"]
        mein = s["tore_" + seite]
        dein = s["tore_gast" if seite == "heim" else "tore_heim"]
        d = {"nr": s.get("nr"), "datum": s.get("datum"), "zeit": s.get("zeit"), "ort": s.get("ort"),
             "heimspiel": seite == "heim", "gegner": gegner, "tore_eigene": mein, "tore_gegner": dein,
             "status": s["status"]}
        if "hz_heim" in s:
            e1 = s["hz_" + seite]
            g1 = s["hz_gast" if seite == "heim" else "hz_heim"]
            d.update(halbzeit=f"{e1}:{g1}", zweite_halbzeit=f"{mein - e1}:{dein - g1}")
        if "spieler" in s:
            d["spieler"] = [p for p in s["spieler"][seite] if p["tore"] or p["zeitstrafen"] or p["gelb"] or p["rot"] or p["versuche7"]]
        eigene.append(d)
    return {"team": team, "erstellt": datetime.now().isoformat(timespec="minutes"),
            "spiele": eigene, "spieler": aggregate(spiele, team)}


def dump(pfad, obj, indent=1):
    pfad.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")


def staffel_holen(key, ordner, cache, cache_datei):
    champ, group, team, anzeige = STAFFELN[key]
    print(f"\n=== {anzeige} (Gruppe {group}) ===")
    plan = spielplan(champ, group)
    ids = sorted({p["meeting"] for p in plan if p["meeting"]})
    print(f"{len(plan)} Spiele im Spielplan, {len(ids)} Spielberichte.")
    dump(ordner / f"nuliga_{key}_spielplan.json", plan)

    todo = [i for i in ids if i not in cache or cache[i].get("status") != "genehmigt"]
    print(f"{len(todo)} davon werden neu geladen.")
    for n, i in enumerate(todo, 1):
        print(f"[{n}/{len(todo)}] Bericht {i}")
        g = fetch_report(i, champ, group)
        if g:
            cache[i] = g
        cache_datei.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    spiele = [cache[i] for i in ids if i in cache]
    dump(ordner / f"nuliga_{key}_alle.json", spiele)
    komp = kompakt(spiele, team)
    dump(ordner / f"nuliga_{key}_kompakt.json", komp)
    if key == "erste-26-27":  # Dateinamen wie bisher
        dump(ordner / "nuliga_alle.json", spiele)
        dump(ordner / "nuliga_kompakt.json", komp)
    print(f"{key}: {len(spiele)} Berichte, {len(komp['spiele'])} Spiele von {team}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nur", choices=sorted(STAFFELN), help="nur diese Staffel holen")
    ap.add_argument("--liste", action="store_true", help="Staffeln anzeigen")
    ap.add_argument("--ordner", help="Zielordner für die JSON-Dateien (Standard: Ordner des Skripts)")
    args = ap.parse_args()
    if args.liste:
        for k, (champ, group, team, anzeige) in STAFFELN.items():
            print(f"{k:14} {anzeige}")
        return

    ordner = Path(args.ordner).resolve() if args.ordner else Path(__file__).resolve().parent
    ordner.mkdir(parents=True, exist_ok=True)
    cache_datei = ordner / "nuliga_cache.json"
    cache = json.loads(cache_datei.read_text(encoding="utf-8")) if cache_datei.exists() else {}
    for key in ([args.nur] if args.nur else list(STAFFELN)):
        staffel_holen(key, ordner, cache, cache_datei)
    print("\nFertig. Schick Claude die Dateien nuliga_*_alle.json (oder den ganzen Ordner als ZIP).")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:
        sys.exit(f"Netzwerkfehler: {e}")
