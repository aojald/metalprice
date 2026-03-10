#!/usr/bin/env python3
"""
Update the embedded CSV in dashboard.html with the contents of
metal_prices_last_month_mt.csv. Run this after exporting a new CSV
so the dashboard shows the latest data by default.

Usage:
  python3 update_dashboard_embedded_csv.py
  python3 update_dashboard_embedded_csv.py --csv path/to/file.csv
  python3 update_dashboard_embedded_csv.py --dashboard path/to/dashboard.html
"""

import argparse
import os
import re

DEFAULT_CSV = "metal_prices_last_month_mt.csv"
DEFAULT_DASHBOARD = "dashboard.html"


def _script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def escape_js_template_literal(text: str) -> str:
    """Escape content for use inside a JavaScript template literal (backticks)."""
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def main() -> None:
    ap = argparse.ArgumentParser(description="Embed metal_prices_last_month_mt.csv into dashboard.html")
    ap.add_argument("--csv", default=DEFAULT_CSV, help=f"Input CSV file (default: {DEFAULT_CSV})")
    ap.add_argument("--dashboard", default=DEFAULT_DASHBOARD, help=f"Dashboard HTML to update (default: {DEFAULT_DASHBOARD})")
    ap.add_argument("--dry-run", action="store_true", help="Print what would be replaced, do not write")
    args = ap.parse_args()

    script_dir = _script_dir()
    csv_path = os.path.join(script_dir, args.csv) if args.csv == DEFAULT_CSV else args.csv
    dashboard_path = os.path.join(script_dir, args.dashboard) if args.dashboard == DEFAULT_DASHBOARD else args.dashboard

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            csv_content = f.read()
    except FileNotFoundError:
        raise SystemExit(f"CSV file not found: {csv_path}")

    csv_content = csv_content.rstrip("\n")
    if not csv_content:
        raise SystemExit(f"CSV file is empty: {csv_path}")

    try:
        with open(dashboard_path, "r", encoding="utf-8") as f:
            dashboard_html = f.read()
    except FileNotFoundError:
        raise SystemExit(f"Dashboard file not found: {dashboard_path}")

    # Match const EMBEDDED_CSV = ` ... `;  (use \x60 for ASCII backtick to avoid encoding issues)
    pattern = re.compile(
        r"(const\s+EMBEDDED_CSV\s*=\s*\x60)([\s\S]*?)(\x60\s*;)",
        re.DOTALL,
    )
    match = pattern.search(dashboard_html)
    if not match:
        raise SystemExit(
            "Could not find EMBEDDED_CSV block in dashboard. No change made.\n"
            f"  CSV: {csv_path}\n"
            f"  Dashboard: {dashboard_path}\n"
            "  Ensure dashboard.html contains:  const EMBEDDED_CSV = ` ... `;"
        )

    escaped = escape_js_template_literal(csv_content)
    new_html = dashboard_html[: match.start(2)] + escaped + dashboard_html[match.end(2) :]

    if args.dry_run:
        print(f"Would update {dashboard_path} with {len(csv_content)} chars from {csv_path}.")
        return

    with open(dashboard_path, "w", encoding="utf-8") as f:
        f.write(new_html)
    print(f"Updated {dashboard_path} with data from {csv_path}.")


if __name__ == "__main__":
    main()
