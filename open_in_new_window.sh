#!/bin/bash

# Скрипт для открытия Jesse Test в новом окне Cursor

WORKSPACE_FILE="/home/crypto/sites/cryptotrader.com/jesse-test/jesse.code-workspace"

echo "Открытие Jesse Test workspace в новом окне..."
echo "Workspace: $WORKSPACE_FILE"
echo ""

# Проверка существования файла
if [ ! -f "$WORKSPACE_FILE" ]; then
    echo "ОШИБКА: Workspace файл не найден: $WORKSPACE_FILE"
    exit 1
fi

# Попытка открыть через cursor
if command -v cursor &> /dev/null; then
    cursor "$WORKSPACE_FILE" --new-window
    echo "✅ Открыто через cursor"
elif command -v code &> /dev/null; then
    code "$WORKSPACE_FILE" --new-window
    echo "✅ Открыто через code"
else
    echo "ОШИБКА: cursor или code не найдены в PATH"
    echo ""
    echo "Откройте вручную:"
    echo "  File → Open Workspace from File..."
    echo "  Выберите: $WORKSPACE_FILE"
    exit 1
fi

