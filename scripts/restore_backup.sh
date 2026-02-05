#!/bin/bash
# Восстановление данных из бэкапа (после переустановки системы)
# Использование: bash scripts/restore_backup.sh path/to/taza_qala_backup_YYYYMMDD_HHMMSS.tar.gz

set -e

if [ -z "$1" ] || [ ! -f "$1" ]; then
  echo "Usage: $0 <backup.tar.gz>"
  echo "Example: $0 taza_qala_backup_20250130_120000.tar.gz"
  exit 1
fi

ARCHIVE="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== TazaQala Restore ==="
echo "From:  $ARCHIVE"
echo "To:    $PROJECT_ROOT"

# Останавливаем приложение, если есть (на сервере)
if command -v systemctl &>/dev/null && systemctl is-active --quiet taza_qala 2>/dev/null; then
  echo "Stopping taza_qala service..."
  sudo systemctl stop taza_qala
fi

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT
tar -xzf "$ARCHIVE" -C "$TMPDIR"

# Восстанавливаем БД
if [ -f "$TMPDIR/taza_qala.db" ]; then
  DB_PATH="${DATABASE_URL:-}"
  if [ -n "$DB_PATH" ]; then
    DB_PATH="${DB_PATH#sqlite:///}"
  else
    DB_PATH="${PROJECT_ROOT}/taza_qala.db"
  fi
  cp "$TMPDIR/taza_qala.db" "$DB_PATH"
  echo "  Restored: $DB_PATH"
fi

# Восстанавливаем uploads
if [ -d "$TMPDIR/uploads" ]; then
  mkdir -p "${PROJECT_ROOT}/static/uploads"
  cp -rn "$TMPDIR/uploads"/* "${PROJECT_ROOT}/static/uploads/" 2>/dev/null || true
  echo "  Restored: static/uploads/"
fi

# Буферные картинки
for f in image.png img_after.jpeg; do
  if [ -f "$TMPDIR/static/$f" ]; then
    mkdir -p "${PROJECT_ROOT}/static"
    cp "$TMPDIR/static/$f" "${PROJECT_ROOT}/static/"
    echo "  Restored: static/$f"
  fi
done

if command -v systemctl &>/dev/null && systemctl is-active --quiet taza_qala 2>/dev/null; then
  echo "Starting taza_qala service..."
  sudo systemctl start taza_qala
fi

echo "Done."
