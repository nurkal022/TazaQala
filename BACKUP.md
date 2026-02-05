# Выгрузка и восстановление данных TazaQala

Перед перестройкой системы сохраните все данные с сервера: базу данных, загруженные фото и документы.

---

## 1. Выгрузка данных с сервера

### На сервере (SSH)

```bash
cd /var/www/taza_qala
bash scripts/backup_from_server.sh
```

Скрипт создаст архив в каталоге `backups/`, например:
`/var/www/taza_qala/backups/taza_qala_backup_20250130_143022.tar.gz`

В архиве:
- **taza_qala.db** — полная копия базы (пользователи, репорты, призы, уведомления)
- **uploads/** — все загруженные фото (до/после) и документы
- **static/image.png**, **static/img_after.jpeg** — буферные картинки, если используются в репортах

### Скачать архив на компьютер

С вашего компьютера (подставьте свой логин и IP сервера):

```bash
scp user@92.118.115.202:/var/www/taza_qala/backups/taza_qala_backup_*.tar.gz ./
```

Или через FileZilla: зайдите на сервер, откройте `/var/www/taza_qala/backups/` и скачайте последний файл `taza_qala_backup_*.tar.gz`.

---

## 2. Восстановление после переустановки

Когда новая система будет готова:

1. Скопируйте архив на сервер (или оставьте в проекте).
2. Выполните:

```bash
cd /var/www/taza_qala
bash scripts/restore_backup.sh backups/taza_qala_backup_20250130_143022.tar.gz
```

Скрипт подставит БД и файлы в нужные места; при необходимости перезапустите сервис вручную:

```bash
sudo systemctl restart taza_qala
```

---

## 3. Ручная выгрузка (если скрипт недоступен)

```bash
cd /var/www/taza_qala
mkdir -p backups
tar -czf backups/taza_qala_manual_$(date +%Y%m%d).tar.gz \
  taza_qala.db \
  static/uploads \
  static/image.png \
  static/img_after.jpeg
```

Путь к БД на сервере может быть задан через `DATABASE_URL` в systemd (например `sqlite:////var/www/taza_qala/taza_qala.db`). В этом случае в архив нужно включить файл по этому пути.

---

## 4. Что именно сохраняется

| Данные | Где хранятся | В бэкапе |
|--------|--------------|----------|
| Пользователи, репорты, призы, уведомления | SQLite `taza_qala.db` | ✅ |
| Фото «до» (репорты) | `static/uploads/*.jpg/png` | ✅ |
| Фото «после» и документы уборки | `static/uploads/cleanup/` | ✅ |
| Буферные изображения | `static/image.png`, `static/img_after.jpeg` | ✅ |

После восстановления пути в БД (например `uploads/xxx.jpg` или `image.png`) остаются корректными.
