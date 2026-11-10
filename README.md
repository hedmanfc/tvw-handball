# TVW Handball – Team-App

Inoffizielle Team-App für TV Wächtersbach (Daten: nuLiga, HHV).

- `tools/nuliga_scraper.py` holt Spielplan und Spielberichte von nuLiga
- `tools/build_app.py` baut daraus die Webseite (`site/index.html`)
- `data/` enthält die geholten Daten (wird automatisch aktualisiert)
- `.github/workflows/update.yml` aktualisiert und veröffentlicht alles automatisch (Sa/So abends, Mo/Di früh) oder per Knopfdruck

Neue Mannschaft oder Saison: Eintrag in `STAFFELN` in `tools/nuliga_scraper.py` **und** in `tools/build_app.py` ergänzen.
Lokal testen: `pip install requests beautifulsoup4`, dann `python tools/nuliga_scraper.py --ordner data` und `python tools/build_app.py data site/index.html --standalone`.
