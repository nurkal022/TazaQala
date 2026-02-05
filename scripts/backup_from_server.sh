#!/bin/bash
# Выгрузка всех данных TazaQala с сервера: БД + картинки + документы
# Запускать на сервере из корня проекта: bash scripts/backup_from_server.sh

set -e

# Корень проекта (на сервере обычно /var/www/taza_qala)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Имя архива с датой
STAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE="taza_qala_backup_${STAMP}.tar.gz"
BACKUP_DIR="${PROJECT_ROOT}/backups"
mkdir -p "$BACKUP_DIR"
OUTPUT="${BACKUP_DIR}/${ARCHIVE}"

echo "=== TazaQala Backup ==="
echo "Project: $PROJECT_ROOT"
echo "Output:  $OUTPUT"

# Путь к БД: из DATABASE_URL или по умолчанию
if [ -n "$DATABASE_URL" ]; then
  # sqlite:////var/www/taza_qala/taza_qala.db -> /var/www/taza_qala/taza_qala.db
  DB_PATH="${DATABASE_URL#sqlite:///}"
else
  DB_PATH="${PROJECT_ROOT}/taza_qala.db"
fi

if [ ! -f "$DB_PATH" ]; then
  echo "ERROR: Database not found: $DB_PATH"
  exit 1
fi

# Временная папка для упаковки (сохраняем структуру)
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# 1) Копируем БД
cp "$DB_PATH" "$TMPDIR/taza_qala.db"
echo "  + database: taza_qala.db"

# 2) Копируем uploads (фото репортов, фото после уборки, документы)
if [ -d "${PROJECT_ROOT}/static/uploads" ]; then
  cp -r "${PROJECT_ROOT}/static/uploads" "$TMPDIR/"
  echo "  + static/uploads/"
fi

# 3) Буферные картинки (в БД могут быть пути image.png, img_after.jpeg)
for f in image.png img_after.jpeg; do
  if [ -f "${PROJECT_ROOT}/static/$f" ]; then
    mkdir -p "$TMPDIR/static"
    cp "${PROJECT_ROOT}/static/$f" "$TMPDIR/static/"
    echo "  + static/$f"
  fi
done

# Упаковываем
tar -czf "$OUTPUT" -C "$TMPDIR" .
echo ""
echo "Done: $OUTPUT"
echo "Size: $(du -h "$OUTPUT" | cut -f1)"
echo ""
echo "Скачать на свой компьютер (выполнить локально):"
echo "  scp user@92.118.115.202:$OUTPUT ./"
echo "или (если проект в /var/www/taza_qala):"
echo "  scp user@YOUR_SERVER:/var/www/taza_qala/backups/${ARCHIVE} ./"
