#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$ROOT_DIR/data"
TARGET_UID=${1:-$(id -u)}
TARGET_GID=${2:-$(id -g)}

dirs=(
  "$DATA_DIR"
  "$DATA_DIR/data_input"
  "$DATA_DIR/data_raw"
  "$DATA_DIR/data_hash"
  "$DATA_DIR/data_json"
  "$DATA_DIR/data_cleaned"
  "$DATA_DIR/data_chunked"
  "$DATA_DIR/data_chromadb_meta"
)

for d in "${dirs[@]}"; do
  if [ ! -d "$d" ]; then
    mkdir -p "$d"
    echo "created: $d"
  fi
  if [ ! -f "$d/.gitkeep" ]; then
    touch "$d/.gitkeep"
    echo "touched: $d/.gitkeep"
  fi
done

if [ ! -f "$DATA_DIR/data_input/sample.txt" ]; then
  cat > "$DATA_DIR/data_input/sample.txt" <<'TXT'
sample input
TXT
  echo "created: $DATA_DIR/data_input/sample.txt"
fi

if [ -f "$ROOT_DIR/.env.example" ] && [ ! -f "$ROOT_DIR/.env" ]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  echo "copied: .env from .env.example"
fi

if chown -R "${TARGET_UID}:${TARGET_GID}" "$DATA_DIR" 2>/dev/null; then
  echo "chown applied: ${TARGET_UID}:${TARGET_GID} -> $DATA_DIR"
else
  echo "warning: chown failed (maybe on Windows mount). To fix ownership run: sudo chown -R 1000:1000 $DATA_DIR"
fi

chmod -R 0755 "$DATA_DIR" || echo "warning: chmod failed (maybe on Windows mount)"

echo "Initialization complete."
