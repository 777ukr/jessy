#!/bin/bash

# Скрипт для запуска Jesse на отдельном порту для тестирования

cd "$(dirname "$0")/jesse-master"

echo "=========================================="
echo "Запуск Jesse Test Server"
echo "=========================================="
echo "Порт: 9001"
echo "URL: http://localhost:9001"
echo "=========================================="
echo ""

# Проверка наличия виртуального окружения
if [ ! -d "venv" ]; then
    echo "Создание виртуального окружения..."
    if ! python3 -m venv venv 2>/dev/null; then
        echo "ОШИБКА: Не удалось создать виртуальное окружение."
        echo "Установите python3-venv:"
        echo "  sudo apt install python3.10-venv"
        echo "Или используйте системный Python (не рекомендуется)"
        read -p "Продолжить с системным Python? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# Активация виртуального окружения
echo "Активация виртуального окружения..."
source venv/bin/activate

# Проверка активации
if [ -z "$VIRTUAL_ENV" ]; then
    echo "ОШИБКА: Не удалось активировать виртуальное окружение"
    exit 1
fi

# Установка зависимостей (если нужно)
if [ ! -f "venv/.deps_installed" ]; then
    echo "Установка зависимостей..."
    pip install --upgrade pip
    pip install -r requirements.txt
    touch venv/.deps_installed
fi

# Установка Jesse в режиме разработки
echo "Установка Jesse..."
pip install -e .

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
        echo "Попробуйте запустить: pip install -e ."
        exit 1
    fi
fi

# Запуск сервера
echo ""
echo "Запуск сервера на порту 9001..."
echo "Для остановки нажмите Ctrl+C"
echo ""

$JESSE_CMD run

