#!/bin/bash
# Скрипт для быстрого развертывания Taza Qala на сервере
# Использование: bash deploy.sh

set -e

echo "🚀 Начинаю развертывание Taza Qala..."

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Переменные
PROJECT_DIR="/var/www/taza_qala"
SERVICE_NAME="taza_qala"

# Проверка прав root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Ошибка: Запустите скрипт с правами root (sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Проверка прав доступа пройдена${NC}"

# Создание директории проекта
if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}Создаю директорию проекта...${NC}"
    mkdir -p "$PROJECT_DIR"
fi

# Установка прав
echo -e "${YELLOW}Устанавливаю права доступа...${NC}"
chown -R www-data:www-data "$PROJECT_DIR"
chmod -R 755 "$PROJECT_DIR"

# Проверка виртуального окружения
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo -e "${YELLOW}Создаю виртуальное окружение...${NC}"
    cd "$PROJECT_DIR"
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    echo -e "${GREEN}✓ Виртуальное окружение создано${NC}"
else
    echo -e "${GREEN}✓ Виртуальное окружение уже существует${NC}"
fi

# Создание директории для загрузок
mkdir -p "$PROJECT_DIR/static/uploads"
chown -R www-data:www-data "$PROJECT_DIR/static/uploads"
chmod -R 775 "$PROJECT_DIR/static/uploads"

# Проверка systemd service
if [ ! -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
    echo -e "${YELLOW}Создаю systemd service...${NC}"
    echo -e "${RED}ВАЖНО: Отредактируйте /etc/systemd/system/${SERVICE_NAME}.service и установите SECRET_KEY!${NC}"
    cp "$PROJECT_DIR/systemd_service_example.service" "/etc/systemd/system/${SERVICE_NAME}.service"
    echo -e "${GREEN}✓ Service файл создан${NC}"
else
    echo -e "${GREEN}✓ Systemd service уже существует${NC}"
fi

# Перезагрузка systemd
echo -e "${YELLOW}Перезагружаю systemd...${NC}"
systemctl daemon-reload

# Проверка nginx конфигурации
echo -e "${YELLOW}Проверяю конфигурацию nginx...${NC}"
if nginx -t; then
    echo -e "${GREEN}✓ Конфигурация nginx корректна${NC}"
else
    echo -e "${RED}Ошибка в конфигурации nginx!${NC}"
    exit 1
fi

# Запуск/перезапуск сервиса
echo -e "${YELLOW}Запускаю сервис...${NC}"
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

# Проверка статуса
sleep 2
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo -e "${GREEN}✓ Сервис успешно запущен${NC}"
else
    echo -e "${RED}Ошибка: Сервис не запустился${NC}"
    echo "Проверьте логи: journalctl -u ${SERVICE_NAME} -n 50"
    exit 1
fi

# Перезагрузка nginx
echo -e "${YELLOW}Перезагружаю nginx...${NC}"
systemctl reload nginx

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Развертывание завершено успешно!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Полезные команды:"
echo "  • Проверить статус: systemctl status ${SERVICE_NAME}"
echo "  • Просмотр логов: journalctl -u ${SERVICE_NAME} -f"
echo "  • Перезапуск: systemctl restart ${SERVICE_NAME}"
echo "  • URL: http://92.118.115.202/taza_qala/"
echo ""

