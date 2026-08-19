#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${AH_CONFIG:-$ROOT/config/default.toml}"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/ah-gui" ]]; then
  exec "$ROOT/.venv/bin/ah-gui" --config "$CONFIG"
elif command -v ah-gui >/dev/null 2>&1; then
  exec ah-gui --config "$CONFIG"
else
  exec python3 -m ah.gui.app --config "$CONFIG"
fi
