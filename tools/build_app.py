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


def _city(n):
    n = re.sub(r"^(TV|TGS|HSG|SG|TSG|MSG)\s+", "", n)
    n = re.sub(r"\s+I{1,3}$", "", n)
    return re.sub(r"-.*$", "", re.sub(r"/.*$", "", n))


def _esc(t):
    return str(t).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(l):
    out = []
    while len(l.encode("utf-8")) > 73:
        k = 73
        while len(l[:k].encode("utf-8")) > 73:
            k -= 1
        out.append(l[:k])
        l = " " + l[k:]
    out.append(l)
    return "\r\n".join(out)


VTZ = ["BEGIN:VTIMEZONE", "TZID:Europe/Berlin", "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST",
       "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT", "BEGIN:STANDARD",
       "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET", "DTSTART:19701025T030000",
       "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD", "END:VTIMEZONE"]


def kalender(key, d):
    """Abo-Kalender (.ics) mit allen Spielen der Mannschaft; Kalender-Apps laden ihn regelmäßig neu."""
    from datetime import datetime, timedelta, timezone
    W = d["W"]
    hall = {}
    for g in d["AL"]:
        if g["o"] and g["h"] not in hall:
            hall[g["h"]] = g["o"]
    jetzt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TVW Handball App//DE", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
         "X-WR-CALNAME:" + _esc(W + " Spielplan"), "X-WR-TIMEZONE:Europe/Berlin", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
         "X-PUBLISHED-TTL:PT6H"] + VTZ
    n = 0
    for dat, zeit, h, a, e in sorted(d["G"], key=lambda g: (g[0], g[1])):
        if W not in (h, a):
            continue
        n += 1
        heim = h == W
        gegner = a if heim else h
        st = datetime.strptime(dat + " " + zeit, "%Y-%m-%d %H:%M")
        en = st + timedelta(minutes=105)
        hl = hall.get(h, "")
        ort = (hl if _city(h).lower() in hl.lower() else hl + ", " + _city(h)) if hl else _city(h)
        titel = (W + " – " + gegner) if heim else (gegner + " – " + W)
        if e:
            titel += "  " + e
        uid = "tvw-%s-%s-%s@tvw-handball" % (key, dat, re.sub(r"[^A-Za-z0-9]", "", h + a))
        L += ["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + jetzt, "DTSTART;TZID=Europe/Berlin:" + st.strftime("%Y%m%dT%H%M00"),
              "DTEND;TZID=Europe/Berlin:" + en.strftime("%Y%m%dT%H%M00"), "SUMMARY:" + _esc(titel), "LOCATION:" + _esc(ort),
              "DESCRIPTION:" + _esc(("Heimspiel" if heim else "Auswärtsspiel") + " · " + d["liga"]),
              "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Handballspiel", "TRIGGER:-PT2H", "END:VALARM", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in L) + "\r\n", n


def pruefen(ds):
    """Plausibilitätsprüfung: Tabelle, Spielplan und Spielberichte müssen zusammenpassen. Meldet Abweichungen als Warnung."""
    probleme = 0
    for key, d in ds.items():
        W = d["W"]
        g_res = [g for g in d["G"] if W in (g[2], g[3]) and g[4]]
        al = [g for g in d["AL"] if W in (g["h"], g["a"])]
        if len(g_res) != len(al):
            print("::warning::%s: %d Spiele mit Ergebnis im Spielplan, aber %d Spielberichte" % (key, len(g_res), len(al)))
            probleme += 1
        for g in d["AL"]:
            for i, seite in enumerate(g["s"]):
                tore = sum(p[2] for p in seite)
                if str(tore) != str(g["e"][i]):
                    print("::warning::%s: %s – %s (%s): Torschützen ergeben %d, Endstand %s" % (key, g["h"], g["a"], g["d"], tore, g["e"][i]))
                    probleme += 1
            if int(g["hz"][0]) > int(g["e"][0]) or int(g["hz"][1]) > int(g["e"][1]):
                print("::warning::%s: %s – %s (%s): Halbzeitstand höher als Endstand" % (key, g["h"], g["a"], g["d"]))
                probleme += 1
        sp = {(g[0], g[2], g[3]): g[4] for g in d["G"]}
        for g in d["AL"]:
            e = sp.get((g["d"], g["h"], g["a"]))
            if e is not None and e != "%s:%s" % tuple(g["e"]):
                print("::warning::%s: %s – %s (%s): Spielplan %s, Spielbericht %s:%s" % (key, g["h"], g["a"], g["d"], e, g["e"][0], g["e"][1]))
                probleme += 1
    print("Prüfung:", "alles stimmig" if not probleme else "%d Auffälligkeit(en), siehe Warnungen" % probleme)


def main():
    tpl = (HERE / "app_template.html").read_text(encoding="utf-8")
    logo = (HERE / "logo_datauri.txt").read_text().strip()
    ds = {}
    for key in STAFFELN:
        if (ORDNER / f"nuliga_{key}_alle.json").exists():
            ds[key] = dataset(key)
            print(f"{key}: {ds[key]['n']} Berichte, {len(ds[key]['G'])} Spiele im Plan")
    def _san(o):
        # Sicherheit: HTML-Sonderzeichen in allen Texten aus nuLiga entschärfen (die App baut Ansichten per innerHTML)
        if isinstance(o, str):
            return o.replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        if isinstance(o, list):
            return [_san(x) for x in o]
        if isinstance(o, dict):
            return {_san(k): _san(v) for k, v in o.items()}
        return o
    ds = _san(ds)
    if STANDALONE:  # beim automatischen Bau auf GitHub: aktuelle News holen (Fehler sind unkritisch)
        try:
            sys.path.insert(0, str(HERE))
            import news_scraper
            news_scraper.hole(ORDNER)
        except Exception as e:
            print("news: übersprungen (%s)" % e)
    news = {"items": []}
    if (ORDNER / "news.json").exists():
        try:
            news = json.loads((ORDNER / "news.json").read_text(encoding="utf-8"))
            news["items"] = [i for i in news.get("items", []) if str(i.get("u", "")).startswith("https://www.tvw-handballer.de/")][:12]
        except Exception as e:
            print("news.json unlesbar:", e)
    news = _san(news)
    pruefen(ds)
    data = "var SUBS=" + ("true" if STANDALONE else "false") + ";\nvar LOGO=" + json.dumps(logo) + ";\nvar DEFAULT=" + json.dumps(DEFAULT if DEFAULT in ds else next(iter(ds))) + \
           ";\nvar DATASETS=" + json.dumps(ds, ensure_ascii=False, separators=(",", ":")) + ";\nvar NEWS=" + json.dumps(news, ensure_ascii=False, separators=(",", ":")) + ";"
    assert "/*@DATA@*/" in tpl
    html = tpl.replace("/*@DATA@*/", data.replace("</", "<\\/"))
    html = html.replace('id="splg" alt="" src=""', 'id="splg" alt="" src="' + logo + '"')
    if STANDALONE:
        head = ('<!doctype html><html lang="de"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                '<meta name="theme-color" content="#0d0f13"><link rel="manifest" href="manifest.webmanifest">'
                '<link rel="apple-touch-icon" href="icon-192.png"><link rel="icon" href="icon-192.png">'
                '<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">'
                '<meta name="robots" content="noindex,nofollow,noarchive"><meta name="referrer" content="no-referrer">'
                '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; '
                'style-src \'unsafe-inline\' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; '
                'img-src \'self\' data: blob:; manifest-src \'self\'; connect-src \'none\'; base-uri \'none\'; form-action \'none\'">'
                '<style>:root{color-scheme:dark}[hidden]{display:none!important}body{margin:0}img{max-width:100%}</style>')
        html = head + html + "</body></html>"
        AUS.parent.mkdir(parents=True, exist_ok=True)
        for k, d in ds.items():
            txt, n = kalender(k, d)
            (AUS.parent / ("kalender-%s.ics" % k)).write_text(txt, encoding="utf-8", newline="")
        print("Kalenderdateien:", len(ds))
        stat = HERE / "static"
        if stat.exists():
            for f in stat.iterdir():
                (AUS.parent / f.name).write_bytes(f.read_bytes())
    AUS.write_text(html, encoding="utf-8")
    print("geschrieben:", AUS, round(AUS.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
