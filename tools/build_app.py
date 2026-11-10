#!/usr/bin/env python3
"""
Baut die App (eine HTML-Datei) aus den nuLiga-Dateien.

  python build_app.py [Ordner mit nuliga_*.json] [Ausgabedatei] [--standalone]

--standalone: fertige Webseite (mit Manifest und Icons aus tools/static) für GitHub Pages

Standard: Ordner = ..  (eine Ebene höher), Ausgabe = handball.html
Benötigt im selben Ordner: app_template.html, logo_datauri.txt
Neue Staffel/Saison: einen Eintrag in STAFFELN ergänzen (und im Scraper).
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
STANDALONE = "--standalone" in sys.argv  # eigene Webseite statt Claude-Artefakt
ORDNER = Path(ARGS[0]) if len(ARGS) > 0 else HERE.parent
AUS = Path(ARGS[1]) if len(ARGS) > 1 else ORDNER / "handball.html"

# key: (Saison, Mannschaft, Liga, Kopfzeile)
STAFFELN = {
    "erste-26-27":  ("2026/27", "1. Mannschaft", "Bezirksoberliga Männer"),
    "zweite-26-27": ("2026/27", "2. Mannschaft", "Bezirksklasse Männer"),
    "erste-25-26":  ("2025/26", "1. Mannschaft", "Bezirksoberliga Männer"),
    "zweite-25-26": ("2025/26", "2. Mannschaft", "2. Bezirksklasse Männer"),
}
DEFAULT = "erste-26-27"
TYP = {"Tor": 0, "7m mit Tor": 1, "7m ohne Tor": 2, "2 Minuten": 3, "Verwarnung": 4, "Auszeit Heim": 5, "Auszeit Gast": 5}


def sek(z):
    m = re.match(r"(\d+):(\d+)", z or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else 0


def al_eintrag(g):
    s = [[[p["nr"], p["name"], p["tore"], p["tore7"], p["versuche7"], int(p["gelb"]), p["zeitstrafen"], int(p["rot"])]
          for p in g["spieler"][seite]] for seite in ("heim", "gast")]
    v = []
    for e in g["verlauf"]:
        if e["ereignis"] not in TYP:
            continue
        seite = 1 if (e["seite"] == "gast" or e["ereignis"] == "Auszeit Gast") else 0
        v.append([seite, sek(e["zeit"]), TYP[e["ereignis"]], 0 if TYP[e["ereignis"]] == 5 else e["nr"]])
    return {"id": g["id"], "nr": g.get("nr"), "d": g["datum"], "t": g["zeit"], "o": g.get("ort", ""),
            "h": g["heim"], "a": g["gast"], "e": [g["tore_heim"], g["tore_gast"]],
            "hz": [g["hz_heim"], g["hz_gast"]], "s": s, "v": v}


def dataset(key):
    saison, team_lbl, liga = STAFFELN[key]
    alle = json.loads((ORDNER / f"nuliga_{key}_alle.json").read_text(encoding="utf-8"))
    plan = json.loads((ORDNER / f"nuliga_{key}_spielplan.json").read_text(encoding="utf-8"))
    komp = json.loads((ORDNER / f"nuliga_{key}_kompakt.json").read_text(encoding="utf-8"))
    ok = [g for g in alle if "tore_heim" in g and "spieler" in g and "hz_heim" in g and g.get("datum")]
    AL = [al_eintrag(g) for g in ok]
    ergebnis = {g["id"]: f'{g["tore_heim"]}:{g["tore_gast"]}' for g in ok}
    G = []
    for p in plan:
        if not p["datum"]:
            continue
        e = ergebnis.get(p["meeting"]) if p["meeting"] else None
        if e is None and p["tore_heim"] is not None:
            e = f'{p["tore_heim"]}:{p["tore_gast"]}'
        G.append([p["datum"], p["zeit"], p["heim"], p["gast"], e])
    teams = sorted({x for g in G for x in (g[2], g[3])})
    D = {"team": komp["team"], "erstellt": komp["erstellt"],
         "spiele": [s for s in komp["spiele"] if "halbzeit" in s and "spieler" in s], "spieler": komp["spieler"]}
    return {"saison": saison, "team": f"{team_lbl} · TV Wächtersbach" if False else team_lbl, "liga": liga,
            "sub": f"{team_lbl} · {saison}", "W": komp["team"],
            "n": len(AL), "D": D, "G": G, "AL": AL, "T": [[t] for t in teams]}


def main():
    tpl = (HERE / "app_template.html").read_text(encoding="utf-8")
    logo = (HERE / "logo_datauri.txt").read_text().strip()
    ds = {}
    for key in STAFFELN:
        if (ORDNER / f"nuliga_{key}_alle.json").exists():
            ds[key] = dataset(key)
            print(f"{key}: {ds[key]['n']} Berichte, {len(ds[key]['G'])} Spiele im Plan")
    data = "var LOGO=" + json.dumps(logo) + ";\nvar DEFAULT=" + json.dumps(DEFAULT if DEFAULT in ds else next(iter(ds))) + \
           ";\nvar DATASETS=" + json.dumps(ds, ensure_ascii=False, separators=(",", ":")) + ";"
    assert "/*@DATA@*/" in tpl
    html = tpl.replace("/*@DATA@*/", data.replace("</", "<\\/"))
    if STANDALONE:
        head = ('<!doctype html><html lang="de"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                '<meta name="theme-color" content="#0d0f13"><link rel="manifest" href="manifest.webmanifest">'
                '<link rel="apple-touch-icon" href="icon-192.png"><link rel="icon" href="icon-192.png">'
                '<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">'
                '<style>:root{color-scheme:dark}[hidden]{display:none!important}body{margin:0}img{max-width:100%}</style>')
        html = head + html + "</body></html>"
        AUS.parent.mkdir(parents=True, exist_ok=True)
        stat = HERE / "static"
        if stat.exists():
            for f in stat.iterdir():
                (AUS.parent / f.name).write_bytes(f.read_bytes())
    AUS.write_text(html, encoding="utf-8")
    print("geschrieben:", AUS, round(AUS.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
