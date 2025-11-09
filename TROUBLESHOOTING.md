# Решение проблем

## Проблема: "ConnectionRefusedError: Connect call failed ('127.0.0.1', 6379)"

**Причина**: Redis не запущен

**Решение**:
```bash
# Проверка статуса Redis
redis-cli ping

# Запуск Redis
sudo systemctl start redis
# или
sudo service redis start

# Автозапуск при загрузке системы
sudo systemctl enable redis
```

## Проблема: "Current directory is not a Jesse project"

**Причина**: Отсутствуют папки `strategies` и `storage`

**Решение**:
```bash
cd /home/crypto/sites/cryptotrader.com/jesse-test/jesse-master
mkdir -p strategies storage
```

## Проблема: "python: command not found"

**Причина**: В скрипте используется неправильная команда Python

**Решение**: Используйте обновленный скрипт `start_test_server_simple.sh`

## Проблема: "No module named jesse"

**Причина**: Jesse не установлен

**Решение**:
```bash
cd /home/crypto/sites/cryptotrader.com/jesse-test/jesse-master
pip3 install --user -e .
```

## Проблема: Порт 9001 не отвечает

**Проверьте**:
1. Redis запущен: `redis-cli ping`
2. PostgreSQL запущен (если используется)
3. Структура проекта создана: `ls strategies storage`
4. .env файл существует и содержит `APP_PORT=9001`
5. Сервер запущен без ошибок

**Проверка порта**:
```bash
netstat -tlnp | grep 9001
# или
ss -tlnp | grep 9001
```


