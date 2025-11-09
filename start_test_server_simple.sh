#!/bin/bash

# Упрощенный скрипт запуска без venv (использует системный Python)

cd "$(dirname "$0")/jesse-master"

echo "=========================================="
echo "Запуск Jesse Test Server (без venv)"
echo "=========================================="
echo "Порт: 9001"
echo "URL: http://localhost:9001"
echo "=========================================="
echo ""

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "ОШИБКА: python3 не найден"
    exit 1
fi

echo "Python версия:"
python3 --version
echo ""

# Проверка установки зависимостей
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "Установка зависимостей..."
    pip3 install --user --upgrade pip
    pip3 install --user -r requirements.txt
    pip3 install --user -e .
else
    echo "Зависимости уже установлены"
fi

# Проверка .env файла
if [ ! -f ".env" ]; then
    echo "ОШИБКА: .env файл не найден!"
    exit 1
fi

# Проверка структуры проекта
if [ ! -d "strategies" ] || [ ! -d "storage" ]; then
    echo "Создание структуры проекта Jesse..."
    mkdir -p strategies storage
fi

# Проверка Redis
echo "Проверка Redis..."
if ! redis-cli ping &>/dev/null; then
    echo "ПРЕДУПРЕЖДЕНИЕ: Redis не запущен!"
    echo "Запустите Redis:"
    echo "  sudo systemctl start redis"
    echo "  или"
    echo "  sudo service redis start"
    echo ""
    read -p "Продолжить без Redis? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Определение команды jesse
JESSE_CMD="jesse"
if ! command -v jesse &> /dev/null; then
    # Попробуем найти в локальной установке
    if [ -f "$HOME/.local/bin/jesse" ]; then
        JESSE_CMD="$HOME/.local/bin/jesse"
    elif [ -f "/root/.local/bin/jesse" ]; then
        JESSE_CMD="/root/.local/bin/jesse"
    else
        echo "ОШИБКА: команда jesse не найдена"
        echo "Установка jesse..."
        pip3 install --user -e .
        JESSE_CMD="/root/.local/bin/jesse"
    fi
fi

echo ""
echo "Запуск сервера на порту 9001..."
echo "Для остановки нажмите Ctrl+C"
echo ""

$JESSE_CMD run

