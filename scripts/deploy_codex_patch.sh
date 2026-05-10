#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HA_CONFIG="${HA_CONFIG:-/mnt/data/supervisor/homeassistant}"
SRC="${SRC:-$REPO_ROOT/custom_components/midea_ac_lan}"
DST="$HA_CONFIG/custom_components/midea_ac_lan"
BACKUP_ROOT="$HA_CONFIG/.component-backup-codex"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_ROOT/midea_ac_lan-$TS"

if [[ ! -f "$SRC/manifest.json" ]]; then
  echo "ERROR: source component not found: $SRC" >&2
  exit 2
fi

mkdir -p "$BACKUP_ROOT"
if [[ -d "$DST" ]]; then
  echo "STAGE=backup BACKUP=$BACKUP"
  cp -a "$DST" "$BACKUP"
fi

echo "STAGE=install SRC=$SRC DST=$DST"
mkdir -p "$DST"
cp -a "$SRC/." "$DST/"
find "$DST" -type d -name __pycache__ -prune -exec rm -rf {} +

echo "STAGE=verify"
if command -v python3 >/dev/null 2>&1; then
  python3 -m py_compile "$DST"/*.py
elif command -v python >/dev/null 2>&1; then
  python -m py_compile "$DST"/*.py
else
  echo "WARN: python is not available on this host; skipping py_compile"
fi
cat "$DST/manifest.json"

echo "STAGE=done"
echo "Restart Home Assistant Core after this script completes."
echo "Rollback source: $BACKUP"
