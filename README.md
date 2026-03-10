# MetalsPrice

Metal commodity prices (USD/EUR) with CSV export and a portable dashboard. Data from [dailymetalprice.com](https://www.dailymetalprice.com/); EUR/USD from [Frankfurter](https://www.frankfurter.dev/).

**Metals:** Gold, Silver (troy **oz**); Aluminum, Copper, Lithium (**mt** = metric ton).

---

## Quick start

```bash
# Update the canonical source CSV and regenerate the dashboard snapshot
python3.11 export_metal_prices_csv.py

# Open the dashboard (double-click or open in browser)
open dashboard.html
```

---

## Project layout

| File | Description |
|------|-------------|
| **export_metal_prices_csv.py** | Fetches the recent metal series, merges it into a single source CSV, recomputes EUR values, regenerates the dashboard snapshot, and refreshes the embedded CSV in `dashboard.html`. |
| **metal_prices_source_mt.csv** | Canonical source CSV updated incrementally day after day. |
| **metal_prices_last_month_mt.csv** | Last ~20 trading days (oz for Au/Ag, mt for Al/Cu/Li), forward-filled. |
| **dashboard.html** | Single-file dashboard: metal cards, USD/EUR or EUR/USD FX chart, line/candlestick, Day/Week/Month. |
| **update_dashboard_embedded_csv.py** | Optional manual helper to replace the CSV embedded in `dashboard.html`. |
| **run_daily.sh** | Small helper that runs the standard daily refresh flow with `python3.11`. |
| **.github/workflows/** | GitHub Actions for daily refresh and GitHub Pages deployment. |

---

## Export script (CSV)

- **Data source:** dailymetalprice.com page HTML. The script parses the inline Chart.js series embedded in `metalprices.php`.
- **FX:** Frankfurter API for EUR/USD.
- **Storage model:** one canonical file, `metal_prices_source_mt.csv`, updated incrementally. Each run also regenerates `metal_prices_last_month_mt.csv` for the dashboard.
- **Dashboard embed:** by default, each run also updates `dashboard.html` so the portable dashboard stays current.

**Usage:**

```bash
python3.11 export_metal_prices_csv.py
```

Useful options:

- `--source-csv path/to/file.csv` — use another canonical source file.
- `--dashboard-csv path/to/file.csv` — write the rolling dashboard snapshot somewhere else.
- `--dashboard-html path/to/dashboard.html` — choose which HTML dashboard to refresh.
- `--fetch-days 20` — number of recent source points requested from the provider.
- `--dashboard-calendar-days 31` — width of the snapshot exported for the dashboard.
- `--no-embed-dashboard` — skip updating `dashboard.html`.

**CSV columns:**  
`date`, `gold_usd_oz`, `gold_eur_oz`, `silver_usd_oz`, `silver_eur_oz`, `aluminum_usd_mt`, `aluminum_eur_mt`, `copper_usd_mt`, `copper_eur_mt`, `lithium_usd_mt`, `lithium_eur_mt`.

---

## Dashboard (`dashboard.html`)

- **Portable:** one HTML file; CSV is embedded so it works from `file://` without a server.
- **Features:** metal cards (last price + sparkline, USD/oz for Gold/Silver and USD/mt for Al/Cu/Li), **USD/EUR** or **EUR/USD** mini chart next to the cards (depending on selected currency), main chart (line or candlestick), Day / Week / Month, “Load CSV” to pick another file.
- **Libraries:** Chart.js and Lightweight Charts (TradingView) from CDN.

Open `dashboard.html` in a browser. A normal run of `export_metal_prices_csv.py` already refreshes the embedded CSV automatically.

---

## Manual embedded CSV update

If you want to update the embedded CSV manually:

```bash
python3.11 update_dashboard_embedded_csv.py
```

Paths are resolved from the script’s directory, so you can run it from anywhere. Options:

- `--csv path/to/file.csv` — use another CSV.
- `--dashboard path/to/dashboard.html` — use another HTML file.
- `--dry-run` — show what would be updated without writing.

---

## Requirements

- **Python 3** (3.9+).
- **Standard library only** is enough for the export/update scripts.
- **Dashboard:** modern browser; no local server required.

---

## Recommended workflow

Use the project as a static dashboard with a daily export refresh:

```bash
python3.11 export_metal_prices_csv.py
open dashboard.html
```

Or use the helper:

```bash
./run_daily.sh
```

---

## Free hosting with GitHub Pages

This repository is ready to be published as a static site on GitHub Pages with a daily automated refresh.

### Included workflows

- `refresh-data.yml`
  Runs daily at `06:17 UTC`, executes `python3.11 export_metal_prices_csv.py`, and commits updated data when files changed.
- `deploy-pages.yml`
  Publishes the dashboard to GitHub Pages on every push to `main` or `master`.

### Setup steps

1. Push this project to a GitHub repository.
2. Open `Settings` -> `Pages` in that repository.
3. Under `Build and deployment`, choose `GitHub Actions` as the source.
4. Keep your default branch as `main` or `master`.
5. Trigger `Deploy GitHub Pages` once manually if you want the site online immediately.
6. Optionally trigger `Refresh Metals Data` once manually to force a fresh dataset before the first scheduled run.

### What gets published

The Pages workflow publishes:

- `index.html` built from `dashboard.html`
- `dashboard.html`
- `metal_prices_last_month_mt.csv`

So the site opens directly on the dashboard.

### Notes

- Scheduled workflows run in UTC.
- GitHub may delay scheduled workflows slightly.
- The refresh workflow only creates a commit when data actually changed.

---

## Data sources

- **Metal prices:** [dailymetalprice.com](https://www.dailymetalprice.com/) (`metalprices.php`, inline Chart.js series).
- **EUR/USD:** [Frankfurter API](https://www.frankfurter.dev/) (ECB-based rates).
