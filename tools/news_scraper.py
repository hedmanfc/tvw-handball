#!/usr/bin/env python3
"""Holt die Neuigkeiten von der Webseite der Handballabteilung (tvw-handballer.de) und
speichert sie als data/news.json.  Fehler sind unkritisch: dann bleibt die alte Datei bestehen.

Aufruf:  python news_scraper.py [Ordner]      (Standard: data)
"""
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

BASIS = "https://www.tvw-handballer.de/"
SEITE = BASIS + "news/"
MONATE = {m: i + 1 for i, m in enumerate(
    ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"])}
PFAD = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/[^/?#]+")
DATUM = re.compile(r"(\d{1,2})\.\s*([A-Za-zäÄ]+)\s+(\d{4})")


def parse(html, limit=12):
    """Zieht Beiträge aus der News-Seite: Titel, Link, Datum, Auszug."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    gesehen, items = set(), []
    for a in soup.find_all("a", href=True):
        url = urljoin(BASIS, a["href"].split("#")[0])
        m = PFAD.search(url)
        if not url.startswith(BASIS) or not m or url in gesehen:
            continue
        titel = " ".join(a.get_text(" ", strip=True).split())
        if len(titel) < 6 or titel.lower().startswith("mehr lesen"):
            continue  # Bild- oder "Mehr lesen"-Links überspringen; der Titel-Link kommt separat
        gesehen.add(url)
        # Container: kleinster Elternknoten, der Titel plus weiteren Text enthält
        box = a
        for _ in range(5):
            if box.parent is None:
                break
            box = box.parent
            if len(box.get_text(" ", strip=True)) > len(titel) + 40:
                break
        text = " ".join(box.get_text(" ", strip=True).split())
        d = None
        dm = DATUM.search(text)
        if dm and dm.group(2).lower() in MONATE:
            d = "%s-%02d-%02d" % (dm.group(3), MONATE[dm.group(2).lower()], int(dm.group(1)))
        if not d:
            d = "%s-%s-%s" % m.groups()
        rest = text.replace(titel, " ")
        if dm:
            rest = rest.replace(dm.group(0), " ")
        rest = re.sub(r"Mehr lesen\.*", " ", rest)
        rest = " ".join(rest.split())
        if len(rest) > 220:
            rest = rest[:217].rsplit(" ", 1)[0] + " …"
        items.append({"d": d, "t": titel, "u": url, "x": rest})
        if len(items) >= limit:
            break
    items.sort(key=lambda x: x["d"], reverse=True)
    return items


def hole(ordner):
    ordner = Path(ordner)
    ziel = ordner / "news.json"
    try:
        import requests
        r = requests.get(SEITE, timeout=20, headers={"User-Agent": "TVW-Team-App (privates Teamprojekt)"})
        r.raise_for_status()
        items = parse(r.text)
        if not items:
            raise ValueError("keine Beiträge erkannt")
        ziel.write_text(json.dumps({"stand": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "quelle": SEITE, "items": items},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        print("news:", len(items), "Beiträge gespeichert")
        return True
    except Exception as e:  # Netz weg, Seite umgebaut, ... -> alte Datei behalten
        print("news: übersprungen (%s)" % e)
        return False


if __name__ == "__main__":
    hole(sys.argv[1] if len(sys.argv) > 1 else "data")
