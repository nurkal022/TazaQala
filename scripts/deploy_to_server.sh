#!/bin/bash
# Деплой с локальной машины на сервер: код + текущая БД + uploads без потери данных
# 
# Использование:
#   export TAZA_SERVER_HOST=212.192.220.185   # или ваш IP/домен
#   export TAZA_SSH_USER=root
#   bash scripts/deploy_to_server.sh
#
# Или: TAZA_SERVER_HOST=212.192.220.185 TAZA_SSH_USER=root bash scripts/deploy_to_server.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

SERVER="${TAZA_SERVER_HOST:-212.192.220.185}"
USER="${TAZA_SSH_USER:-root}"
REMOTE_DIR="/var/www/taza_qala"

echo "=== Деплой TazaQala на сервер ==="
echo "Сервер: $USER@$SERVER"
echo "Путь на сервере: $REMOTE_DIR"
echo ""

# 1. Проверка локальной БД
if [ ! -f "$PROJECT_ROOT/taza_qala.db" ]; then
    echo "Ошибка: локально не найден taza_qala.db. Запустите приложение локально или восстановите бэкап."
    exit 1
fi
echo "✓ Локальная БД: taza_qala.db"

# 2. Пуш кода в git (если нет незакоммиченных изменений)
if git rev-parse --git-dir >/dev/null 2>&1; then
    if [ -n "$(git status --porcelain)" ]; then
        echo "Внимание: есть незакоммиченные изменения. На сервер уйдут только БД и uploads; код обновится из последнего push."
    else
        echo "Пушим код в origin..."
        git push origin main 2>/dev/null || git push origin master 2>/dev/null || true
    fi
fi

# 3. На сервере: бэкап текущих данных
echo "Создаю бэкап на сервере..."
ssh "$USER@$SERVER" "mkdir -p $REMOTE_DIR/backups && \
  if [ -f $REMOTE_DIR/taza_qala.db ]; then cp $REMOTE_DIR/taza_qala.db $REMOTE_DIR/backups/taza_qala.db.before_\$(date +%Y%m%d_%H%M%S); fi"

# 4. Загрузка локальной БД на сервер
echo "Загружаю БД на сервер..."
scp "$PROJECT_ROOT/taza_qala.db" "$USER@$SERVER:$REMOTE_DIR/taza_qala.db"
ssh "$USER@$SERVER" "chown www-data:www-data $REMOTE_DIR/taza_qala.db"

# 5. Загрузка uploads (если есть)
if [ -d "$PROJECT_ROOT/static/uploads" ] && [ "$(find "$PROJECT_ROOT/static/uploads" -type f 2>/dev/null | wc -l)" -gt 0 ]; then
    echo "Синхронизирую static/uploads..."
    rsync -avz --delete \
      --exclude='.gitkeep' \
      "$PROJECT_ROOT/static/uploads/" \
      "$USER@$SERVER:$REMOTE_DIR/static/uploads/" 2>/dev/null || \
    scp -r "$PROJECT_ROOT/static/uploads/"* "$USER@$SERVER:$REMOTE_DIR/static/uploads/" 2>/dev/null || true
    ssh "$USER@$SERVER" "chown -R www-data:www-data $REMOTE_DIR/static/uploads"
fi

# 6. На сервере: обновление кода из git и перезапуск
echo "Обновляю код на сервере и перезапускаю сервис..."
ssh "$USER@$SERVER" "cd $REMOTE_DIR && \
  git fetch origin && git reset --hard origin/main 2>/dev/null || git reset --hard origin/master 2>/dev/null || true && \
  [ -d venv ] && . venv/bin/activate && pip install -q -r requirements.txt; \
  sudo systemctl restart taza_qala"

echo ""
echo "✓ Деплой завершён."
echo "Проверка: curl -sI http://$SERVER/taza_qala/ | head -1"
echo "Логи: ssh $USER@$SERVER 'journalctl -u taza_qala -n 30 --no-pager'"
