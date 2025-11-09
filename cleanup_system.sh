#!/bin/bash

# Скрипт для безопасной очистки системы
# Освобождает место, удаляя кэши, старые логи и временные файлы

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода заголовка
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

# Функция для проверки размера перед очисткой
check_size() {
    local path=$1
    if [ -d "$path" ] || [ -f "$path" ]; then
        du -sh "$path" 2>/dev/null | awk '{print $1}'
    else
        echo "0"
    fi
}

# Функция для безопасной очистки с подтверждением
clean_with_confirm() {
    local name=$1
    local cmd=$2
    local path=$3
    
    if [ -n "$path" ]; then
        size=$(check_size "$path")
        if [ "$size" != "0" ] && [ "$size" != "" ]; then
            echo -e "${YELLOW}Найдено: $name - $size${NC}"
            read -p "Очистить? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                eval "$cmd"
                echo -e "${GREEN}✓ Очищено: $name${NC}"
                return 0
            else
                echo -e "${YELLOW}⊘ Пропущено: $name${NC}"
                return 1
            fi
        else
            echo -e "${YELLOW}⊘ $name - не найдено или пусто${NC}"
            return 1
        fi
    else
        read -p "Выполнить: $name? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            eval "$cmd"
            echo -e "${GREEN}✓ Выполнено: $name${NC}"
            return 0
        else
            echo -e "${YELLOW}⊘ Пропущено: $name${NC}"
            return 1
        fi
    fi
}

# Функция для выполнения команд с sudo (если нужно)
run_sudo() {
    if [ "$EUID" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

# Определение команды для привилегированных операций
if [ "$EUID" -eq 0 ]; then
    echo -e "${YELLOW}Запуск от root - sudo не требуется${NC}\n"
else
    echo -e "${YELLOW}Запуск от обычного пользователя - будет использоваться sudo${NC}\n"
fi

# Главная функция
main() {
    print_header "Очистка системы - Освобождение места"
    
    echo -e "${YELLOW}Этот скрипт безопасно очистит кэши, логи и временные файлы.${NC}"
    echo -e "${YELLOW}Вы можете выбрать, что именно очищать.${NC}\n"
    
    total_freed=0
    
    # 1. Pip кэш
    print_header "1. Pip кэш"
    clean_with_confirm "Pip кэш (Python пакеты)" \
        "rm -rf /root/.cache/pip/*" \
        "/root/.cache/pip"
    
    # 2. Playwright кэш
    print_header "2. Playwright кэш"
    clean_with_confirm "Playwright браузеры" \
        "rm -rf /root/.cache/ms-playwright/*" \
        "/root/.cache/ms-playwright"
    
    # 3. APT кэш
    print_header "3. APT кэш"
    clean_with_confirm "APT кэш (.deb пакеты)" \
        "run_sudo apt clean" \
        "/var/cache/apt/archives"
    
    # 4. APT списки
    print_header "4. APT списки пакетов"
    clean_with_confirm "Устаревшие APT списки" \
        "run_sudo apt autoclean" \
        "/var/lib/apt/lists"
    
    # 5. Старые ядра Linux
    print_header "5. Старые ядра Linux"
    echo -e "${YELLOW}Текущее ядро: $(uname -r)${NC}"
    echo -e "${YELLOW}Будут удалены старые ядра и заголовки${NC}"
    clean_with_confirm "Старые ядра Linux" \
        "run_sudo apt autoremove --purge -y" \
        ""
    
    # 6. Systemd журналы
    print_header "6. Systemd журналы"
    echo -e "${YELLOW}Оставить логи за последние 7 дней${NC}"
    clean_with_confirm "Systemd журналы (оставить 7 дней)" \
        "run_sudo journalctl --vacuum-time=7d" \
        "/var/log/journal"
    
    # 7. Atop логи
    print_header "7. Atop логи мониторинга"
    clean_with_confirm "Atop логи (старше 7 дней)" \
        "run_sudo find /var/log/atop -type f -mtime +7 -delete" \
        "/var/log/atop"
    
    # 8. Временные файлы /tmp
    print_header "8. Временные файлы /tmp"
    clean_with_confirm "Файлы в /tmp (старше 7 дней)" \
        "run_sudo find /tmp -type f -atime +7 -delete 2>/dev/null || true" \
        "/tmp"
    
    # 9. Python кэш (__pycache__, .pyc)
    print_header "9. Python кэш проекта"
    echo -e "${YELLOW}Будут удалены __pycache__ и .pyc файлы в /home/crypto${NC}"
    clean_with_confirm "Python кэш" \
        "find /home/crypto -type d -name '__pycache__' -exec rm -r {} + 2>/dev/null || true; find /home/crypto -name '*.pyc' -delete 2>/dev/null || true; find /home/crypto -name '*.pyo' -delete 2>/dev/null || true" \
        ""
    
    # 10. Jesse temp кэш
    print_header "10. Jesse temp кэш"
    clean_with_confirm "Jesse кэш свечей (pickle файлы)" \
        "rm -f /home/crypto/sites/cryptotrader.com/jesse-test/jesse-master/storage/temp/*.pickle 2>/dev/null || true" \
        "/home/crypto/sites/cryptotrader.com/jesse-test/jesse-master/storage/temp"
    
    # 11. Snap старые версии
    print_header "11. Snap старые версии"
    echo -e "${YELLOW}Будут удалены старые версии snap пакетов${NC}"
    clean_with_confirm "Snap старые версии" \
        "run_sudo snap list --all | awk '/disabled/{print \$1, \$3}' | while read snapname revision; do run_sudo snap remove \"\$snapname\" --revision=\"\$revision\" 2>/dev/null || true; done" \
        "/var/lib/snapd"
    
    # Итоговая статистика
    print_header "Очистка завершена"
    echo -e "${GREEN}Все выбранные операции выполнены!${NC}"
    echo -e "\n${YELLOW}Рекомендации:${NC}"
    echo -e "  • Pip кэш можно очищать периодически (раз в месяц)"
    echo -e "  • APT кэш очищается автоматически при обновлении"
    echo -e "  • Логи рекомендуется чистить раз в неделю"
    echo -e "  • Python кэш пересоздаётся автоматически"
    echo -e "\n${BLUE}Для проверки свободного места: df -h${NC}\n"
}

# Запуск
main

