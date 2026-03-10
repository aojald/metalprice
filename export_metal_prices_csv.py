#!/usr/bin/env python3
"""
Update a single source CSV of metal prices and regenerate the dashboard snapshot.

Daily workflow:
  python3.11 export_metal_prices_csv.py

What it does:
  1. Fetch the recent price series directly from dailymetalprice.com pages.
  2. Merge those fresh points into a single source CSV.
  3. Forward-fill missing non-trading days in that source CSV.
  4. Recompute EUR columns from Frankfurter USD->EUR rates.
  5. Export a short rolling snapshot used by dashboard.html.

Outputs:
  - metal_prices_source_mt.csv      # canonical source file to update every day
  - metal_prices_last_month_mt.csv  # rolling snapshot used by the dashboard
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://www.dailymetalprice.com"
BASE_HTTP = "http://www.dailymetalprice.com"
SOURCE_CSV = "metal_prices_source_mt.csv"
DASHBOARD_CSV = "metal_prices_last_month_mt.csv"
DASHBOARD_HTML = "dashboard.html"
FETCH_DAYS = 20
DASHBOARD_CALENDAR_DAYS = 31
HTTP_TIMEOUT = 20

METALS = {
    "gold": {"code": "au", "fetch_unit": "oz", "csv_unit": "oz"},
    "silver": {"code": "ag", "fetch_unit": "oz", "csv_unit": "oz"},
    "aluminum": {"code": "al", "fetch_unit": "t", "csv_unit": "mt"},
    "copper": {"code": "cu", "fetch_unit": "t", "csv_unit": "mt"},
    "lithium": {"code": "li", "fetch_unit": "t", "csv_unit": "mt"},
}

METALS_USE_HTTP = {"au", "ag", "cu"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def build_csv_columns() -> list[str]:
    columns = ["date"]
    for name, meta in METALS.items():
        unit = meta["csv_unit"]
        columns.append(f"{name}_usd_{unit}")
        columns.append(f"{name}_eur_{unit}")
    return columns


CSV_COLUMNS = build_csv_columns()


def make_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers=HEADERS)


def urlopen_text(url: str) -> str:
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(make_request(url), timeout=HTTP_TIMEOUT, context=ctx) as response:
        return response.read().decode("utf-8", errors="replace")


def normalize_date(value: int | float | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1e10:
            timestamp /= 1000.0
        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (ValueError, OSError):
            return None
        return dt.strftime("%Y-%m-%d")
    text = str(value).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    return None


def parse_chart_series_html(html: str) -> list[tuple[str, float]]:
    match = re.search(r"data:\s*\[(.*?)\]\s*,\s*backgroundColor:", html, re.DOTALL | re.IGNORECASE)
    if not match:
        return []
    out: list[tuple[str, float]] = []
    for ts_raw, val_raw in re.findall(r"\[\s*(\d{10,13})\s*,\s*([-+]?\d+(?:\.\d+)?)\s*\]", match.group(1)):
        date_str = normalize_date(int(ts_raw))
        if not date_str:
            continue
        out.append((date_str, float(val_raw)))
    out.sort(key=lambda item: item[0])
    return out


def base_for_metal(code: str) -> str:
    return BASE_HTTP if code in METALS_USE_HTTP else BASE


def fetch_recent_series(name: str, days: int) -> dict[str, float]:
    meta = METALS[name]
    url = (
        f"{base_for_metal(meta['code'])}/metalprices.php"
        f"?c={meta['code']}&u={meta['fetch_unit']}&d={days}"
    )
    html = urlopen_text(url)
    rows = parse_chart_series_html(html)
    if not rows:
        raise RuntimeError(f"No inline chart data found for {name} at {url}")
    return dict(rows)


def fetch_eur_usd(start_date: str, end_date: str) -> dict[str, float]:
    url = f"https://api.frankfurter.dev/v1/{start_date}..{end_date}?from=USD&to=EUR"
    text = urlopen_text(url)
    payload = json.loads(text)
    rates: dict[str, float] = {}
    for date_str, value in (payload.get("rates") or {}).items():
        if isinstance(value, dict) and "EUR" in value:
            rates[date_str] = float(value["EUR"])
    return rates


def load_existing_rows(path: str) -> dict[str, dict[str, str]]:
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows: dict[str, dict[str, str]] = {}
            for row in reader:
                date_str = (row.get("date") or "").strip()
                if not date_str:
                    continue
                rows[date_str] = {column: (row.get(column, "") or "").strip() for column in CSV_COLUMNS}
            return rows
    except FileNotFoundError:
        return {}


def load_existing_source_with_bootstrap(source_path: str, bootstrap_path: str) -> dict[str, dict[str, str]]:
    rows = load_existing_rows(source_path)
    if rows:
        return rows
    if source_path != bootstrap_path:
        return load_existing_rows(bootstrap_path)
    return {}


def build_calendar(start_date: str, end_date: str) -> list[str]:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def merge_series(existing: dict[str, dict[str, str]], fresh_by_metal: dict[str, dict[str, float]]) -> dict[str, dict[str, str]]:
    merged = {date_str: row.copy() for date_str, row in existing.items()}
    for date_str in list(merged.keys()):
        merged[date_str].setdefault("date", date_str)
        for column in CSV_COLUMNS:
            merged[date_str].setdefault(column, "")

    for name, series in fresh_by_metal.items():
        unit = METALS[name]["csv_unit"]
        usd_column = f"{name}_usd_{unit}"
        eur_column = f"{name}_eur_{unit}"
        for date_str, usd_value in series.items():
            row = merged.setdefault(date_str, {column: "" for column in CSV_COLUMNS})
            row["date"] = date_str
            row[usd_column] = f"{usd_value:.4f}"
            row[eur_column] = ""
    return merged


def forward_fill_usd(rows_by_date: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    if not rows_by_date:
        return {}
    dates = sorted(rows_by_date)
    full_dates = build_calendar(dates[0], dates[-1])
    filled: dict[str, dict[str, str]] = {}
    last_seen: dict[str, str] = {}

    for date_str in full_dates:
        base_row = rows_by_date.get(date_str, {})
        row = {column: "" for column in CSV_COLUMNS}
        row["date"] = date_str
        for name, meta in METALS.items():
            unit = meta["csv_unit"]
            usd_column = f"{name}_usd_{unit}"
            current_usd = (base_row.get(usd_column) or "").strip()
            if current_usd:
                last_seen[usd_column] = current_usd
            row[usd_column] = last_seen.get(usd_column, "")
        filled[date_str] = row
    return filled


def recompute_eur_columns(rows_by_date: dict[str, dict[str, str]], fx_rates: dict[str, float]) -> None:
    for date_str, row in rows_by_date.items():
        rate = fx_rates.get(date_str)
        for name, meta in METALS.items():
            unit = meta["csv_unit"]
            usd_column = f"{name}_usd_{unit}"
            eur_column = f"{name}_eur_{unit}"
            usd_text = row.get(usd_column, "")
            if not usd_text or rate is None:
                row[eur_column] = ""
                continue
            row[eur_column] = f"{float(usd_text) * rate:.4f}"


def write_rows(path: str, rows_by_date: dict[str, dict[str, str]], date_subset: list[str] | None = None) -> None:
    dates = sorted(rows_by_date) if date_subset is None else date_subset
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for date_str in dates:
            row = rows_by_date[date_str]
            writer.writerow([row.get(column, "") for column in CSV_COLUMNS])


def escape_js_template_literal(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def embed_dashboard_csv(csv_path: str, dashboard_path: str) -> None:
    try:
        with open(csv_path, "r", encoding="utf-8") as handle:
            csv_content = handle.read().rstrip("\n")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Dashboard CSV file not found: {csv_path}") from exc
    if not csv_content:
        raise RuntimeError(f"Dashboard CSV file is empty: {csv_path}")

    try:
        with open(dashboard_path, "r", encoding="utf-8") as handle:
            html = handle.read()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Dashboard HTML file not found: {dashboard_path}") from exc

    pattern = re.compile(r"(const\s+EMBEDDED_CSV\s*=\s*\x60)([\s\S]*?)(\x60\s*;)", re.DOTALL)
    match = pattern.search(html)
    if not match:
        raise RuntimeError(f"Could not find EMBEDDED_CSV block in {dashboard_path}")

    escaped_csv = escape_js_template_literal(csv_content)
    updated_html = html[: match.start(2)] + escaped_csv + html[match.end(2) :]
    with open(dashboard_path, "w", encoding="utf-8") as handle:
        handle.write(updated_html)


def slice_recent_dates(rows_by_date: dict[str, dict[str, str]], calendar_days: int) -> list[str]:
    dates = sorted(rows_by_date)
    if not dates:
        return []
    end = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    start = end - timedelta(days=calendar_days)
    keep = []
    current = start
    while current <= end:
        date_str = current.isoformat()
        if date_str in rows_by_date:
            keep.append(date_str)
        current += timedelta(days=1)
    return keep


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update the canonical source CSV and regenerate the dashboard snapshot."
    )
    parser.add_argument(
        "--source-csv",
        default=SOURCE_CSV,
        help=f"Canonical source CSV to update (default: {SOURCE_CSV})",
    )
    parser.add_argument(
        "--dashboard-csv",
        default=DASHBOARD_CSV,
        help=f"Rolling snapshot for the dashboard (default: {DASHBOARD_CSV})",
    )
    parser.add_argument(
        "--fetch-days",
        type=int,
        default=FETCH_DAYS,
        help=f"Recent series length fetched from the source site (default: {FETCH_DAYS})",
    )
    parser.add_argument(
        "--dashboard-calendar-days",
        type=int,
        default=DASHBOARD_CALENDAR_DAYS,
        help=(
            "Calendar window exported to the dashboard snapshot "
            f"(default: {DASHBOARD_CALENDAR_DAYS})"
        ),
    )
    parser.add_argument(
        "--dashboard-html",
        default=DASHBOARD_HTML,
        help=f"Dashboard HTML file whose embedded CSV should be refreshed (default: {DASHBOARD_HTML})",
    )
    parser.add_argument(
        "--no-embed-dashboard",
        action="store_true",
        help="Skip embedding the regenerated dashboard CSV into the dashboard HTML file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Fetching fresh metal series...")
    fresh_by_metal: dict[str, dict[str, float]] = {}
    for name in METALS:
        series = fetch_recent_series(name, args.fetch_days)
        fresh_by_metal[name] = series
        print(f"  {name}: {len(series)} points")

    all_fresh_dates = sorted({date_str for series in fresh_by_metal.values() for date_str in series})
    if not all_fresh_dates:
        raise SystemExit("No fresh data was fetched.")

    print(f"Loading existing source CSV: {args.source_csv}")
    existing_rows = load_existing_source_with_bootstrap(args.source_csv, args.dashboard_csv)
    merged_rows = merge_series(existing_rows, fresh_by_metal)
    filled_rows = forward_fill_usd(merged_rows)

    start_date = min(filled_rows)
    end_date = max(filled_rows)
    print(f"Fetching USD->EUR rates for {start_date}..{end_date}")
    fx_rates = fetch_eur_usd(start_date, end_date)
    recompute_eur_columns(filled_rows, fx_rates)

    write_rows(args.source_csv, filled_rows)
    recent_dates = slice_recent_dates(filled_rows, args.dashboard_calendar_days)
    write_rows(args.dashboard_csv, filled_rows, recent_dates)
    if not args.no_embed_dashboard:
        dashboard_html_path = args.dashboard_html
        if not os.path.isabs(dashboard_html_path):
            dashboard_html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), dashboard_html_path)
        dashboard_csv_path = args.dashboard_csv
        if not os.path.isabs(dashboard_csv_path):
            dashboard_csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), dashboard_csv_path)
        embed_dashboard_csv(dashboard_csv_path, dashboard_html_path)

    print(f"Updated {args.source_csv} with {len(filled_rows)} rows.")
    print(f"Updated {args.dashboard_csv} with {len(recent_dates)} rows.")
    if not args.no_embed_dashboard:
        print(f"Updated {args.dashboard_html} with embedded CSV data.")


if __name__ == "__main__":
    main()
