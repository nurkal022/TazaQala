# Деплой TazaQala на сервер с локальной БД

Актуальный код и локальная база данных выгружаются на сервер без потери данных.

## Что нужно перед деплоем

1. **Локально** в проекте есть файл `taza_qala.db` (текущая БД).
2. **Доступ по SSH** к серверу: `ssh root@212.192.220.185` (или ваш хост).
3. На сервере уже развёрнут проект в `/var/www/taza_qala` (nginx, systemd, venv).

## Быстрый деплой (одной командой)

Из корня проекта на **локальной машине**:

```bash
# Укажите хост и пользователя (если не 212.192.220.185 и root)
export TAZA_SERVER_HOST=212.192.220.185
export TAZA_SSH_USER=root

bash scripts/deploy_to_server.sh
```

Скрипт:

- сделает бэкап текущей БД на сервере в `backups/`;
- зальёт ваш локальный `taza_qala.db` на сервер;
- синхронизирует `static/uploads/` с сервером (если есть файлы);
- обновит код на сервере (`git pull` / `git reset --hard origin/main`);
- установит зависимости и перезапустит сервис `taza_qala`.

## Пошагово (если скрипт не используете)

### 1. Локально: отправить код в репозиторий

```bash
cd /Users/nurlykhan/taza_qala
git add -A
git status
git commit -m "Deploy: ..."   # при необходимости
git push origin main
```

### 2. Локально: загрузить БД и uploads на сервер

```bash
SERVER=212.192.220.185
USER=root
REMOTE=/var/www/taza_qala

# Бэкап на сервере
ssh $USER@$SERVER "cp $REMOTE/taza_qala.db $REMOTE/backups/taza_qala.db.bak_\$(date +%Y%m%d_%H%M%S) 2>/dev/null; true"

# Загрузка БД
scp taza_qala.db $USER@$SERVER:$REMOTE/taza_qala.db
ssh $USER@$SERVER "chown www-data:www-data $REMOTE/taza_qala.db"

# Загрузка uploads (если нужно)
rsync -avz static/uploads/ $USER@$SERVER:$REMOTE/static/uploads/
ssh $USER@$SERVER "chown -R www-data:www-data $REMOTE/static/uploads"
```

### 3. На сервере: обновить код и перезапустить

```bash
ssh $USER@$SERVER

cd /var/www/taza_qala
git pull origin main   # или git fetch && git reset --hard origin/main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart taza_qala
sudo systemctl status taza_qala
```

### 4. Проверить

- Сайт: `https://ваш-домен/taza_qala/` или `http://212.192.220.185/taza_qala/`
- Логи: `journalctl -u taza_qala -n 50 --no-pager`

## Переменные окружения на сервере

В systemd-сервисе (`/etc/systemd/system/taza_qala.service`) должны быть заданы:

- `SECRET_KEY` — секретный ключ Flask
- `DATABASE_URL=sqlite:////var/www/taza_qala/taza_qala.db`
- `SCRIPT_NAME=/taza_qala` — если приложение отдаётся по пути `/taza_qala`
- При необходимости: `OPENAI_API_KEY` для AI-модерации

После правки сервиса:

```bash
sudo systemctl daemon-reload
sudo systemctl restart taza_qala
```

## Если что-то пошло не так

- Бэкапы БД на сервере: `/var/www/taza_qala/backups/`.
- Восстановить предыдущую БД:  
  `sudo cp /var/www/taza_qala/backups/taza_qala.db.before_YYYYMMDD_HHMMSS /var/www/taza_qala/taza_qala.db`  
  затем `sudo systemctl restart taza_qala`.
- Логи: `journalctl -u taza_qala -f`.
