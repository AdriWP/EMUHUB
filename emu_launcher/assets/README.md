# assets – Bilder für EMUHUB

Icon und Logo sind fertig erzeugt. Fehlt eine Datei, nutzt EMUHUB den Standard (kein Icon, Schriftzug „EMUHUB“).
Neu erzeugen oder umfärben: `py tools\make_brand_assets.py` im Projektordner (Farben und Maße oben im Skript).
Zum Weiterbearbeiten (z. B. Inkscape): `source/icon.svg` und `source/logo.svg`.

| Datei | Zweck | Format / Größe |
|---|---|---|
| `icon.ico` | App-Symbol (Fenster, Taskleiste) | ICO mit den Größen 16, 32, 48, 64, 128, 256 px |
| `icon.png` | wie `icon.ico`, falls keine .ico vorhanden | PNG, quadratisch, **1024 × 1024**, transparent, ca. 10 % Rand um das Motiv |
| `logo.png` | ersetzt den Schriftzug „EMUHUB“ oben links | PNG, transparent, Seitenverhältnis ca. 4:1 (z. B. **800 × 200**), wird auf 40 px Höhe skaliert |

Nach dem Ablegen EMUHUB neu starten.
