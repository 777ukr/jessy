# Быстрый старт Jesse Test Server

## Минимальная настройка

1. **Установите Redis** (обязательно):
   ```bash
   sudo apt update
   sudo apt install redis-server redis-tools
   sudo systemctl start redis
   ```

2. **Установите python3-venv** (опционально, для venv):
   ```bash
   sudo apt install python3.10-venv
   ```

3. **Запустите скрипт**:
   ```bash
   cd /home/crypto/sites/cryptotrader.com/jesse-test
   ./start_test_server_simple.sh
   ```

Скрипт автоматически:
- Создаст виртуальное окружение (если нужно)
- Установит все зависимости
- Запустит сервер на порту **9001**

## Доступ к серверу

После запуска откройте в браузере:
- http://localhost:9001

## Важные файлы

- `.env` - конфигурация (порт, база данных, Redis)
- `start_test_server.sh` - скрипт запуска
- `README.md` - полная документация

## Остановка сервера

Нажмите `Ctrl+C` в терминале, где запущен сервер.



