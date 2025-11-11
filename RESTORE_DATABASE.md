# Инструкция по восстановлению базы данных

## Восстановление из SQL дампа

```bash
# Создать базу данных (если не существует)
createdb -h 127.0.0.1 -U jesse_user jesse_test_db

# Восстановить из SQL дампа
PGPASSWORD=jesse_password psql -h 127.0.0.1 -U jesse_user -d jesse_test_db < jesse_test_db_backup.sql
```

## Восстановление из бинарного дампа (.dump)

```bash
# Создать базу данных (если не существует)
createdb -h 127.0.0.1 -U jesse_user jesse_test_db

# Восстановить из бинарного дампа
PGPASSWORD=jesse_password pg_restore -h 127.0.0.1 -U jesse_user -d jesse_test_db jesse_test_db_backup.dump
```

## Параметры подключения

- **Host:** 127.0.0.1
- **Port:** 5432
- **Database:** jesse_test_db
- **User:** jesse_user
- **Password:** jesse_password

## Проверка восстановления

```bash
# Подключиться к базе данных
PGPASSWORD=jesse_password psql -h 127.0.0.1 -U jesse_user -d jesse_test_db

# Проверить таблицы
\dt

# Проверить количество свечей
SELECT COUNT(*) FROM candle;

# Проверить сессии бектеста
SELECT COUNT(*) FROM backtest_session;
```


