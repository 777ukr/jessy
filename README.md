# Jesse Test Environment

Это отдельная установка Jesse для тестирования на порту 9001.

## Структура

```
jesse-test/
├── jesse-master/          # Распакованный архив Jesse
├── start_test_server.sh   # Скрипт для запуска тестового сервера
└── README.md             # Этот файл
```

## Настройка

### 1. Установка python3-venv (если нужно)

```bash
sudo apt install python3.10-venv
```

### 2. Создание виртуального окружения

```bash
cd jesse-test/jesse-master
python3 -m venv venv
source venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### 4. Настройка базы данных

Убедитесь, что PostgreSQL запущен и создайте базу данных:

```bash
# Создание базы данных (если нужно)
createdb jesse_test_db

# Или через psql:
psql -U postgres -c "CREATE DATABASE jesse_test_db;"
psql -U postgres -c "CREATE USER jesse_user WITH PASSWORD 'jesse_password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE jesse_test_db TO jesse_user;"
```

### 5. Установка и настройка Redis

Jesse требует Redis для работы. Установите и запустите Redis:

```bash
# Установка Redis
sudo apt update
sudo apt install redis-server redis-tools

# Запуск Redis
sudo systemctl start redis
sudo systemctl enable redis  # автозапуск при загрузке

# Проверка Redis
redis-cli ping
# Должен ответить: PONG
```

## Запуск

### Быстрый запуск

Используйте готовый скрипт:

```bash
cd /home/crypto/sites/cryptotrader.com/jesse-test
./start_test_server.sh
```

### Ручной запуск

```bash
cd jesse-test/jesse-master
source venv/bin/activate
python -m jesse
```

## Доступ

После запуска сервер будет доступен по адресу:

- **URL**: http://localhost:9001
- **Порт**: 9001 (отдельный от основного установки)

## Конфигурация

Настройки находятся в файле `.env` в директории `jesse-master/`:

- `APP_PORT=9001` - порт для тестирования
- `POSTGRES_NAME=jesse_test_db` - отдельная база данных для тестов
- `REDIS_DB=1` - отдельная база Redis для тестов

## Примечания

- Эта установка использует отдельный порт (9001) и отдельную базу данных
- Не конфликтует с основной установкой Jesse
- Подходит для тестирования и разработки стратегий

