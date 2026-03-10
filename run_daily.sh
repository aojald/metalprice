#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"
python3.11 export_metal_prices_csv.py "$@"
