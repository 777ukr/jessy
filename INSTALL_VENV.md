# Установка python3-venv

Для правильной работы виртуального окружения нужно установить пакет `python3-venv`.

## Установка

```bash
sudo apt update
sudo apt install python3.10-venv
```

## После установки

Пересоздайте виртуальное окружение:

```bash
cd /home/crypto/sites/cryptotrader.com/jesse-test/jesse-master
rm -rf venv
python3 -m venv venv
```

Затем запустите основной скрипт:

```bash
cd /home/crypto/sites/cryptotrader.com/jesse-test
./start_test_server.sh
```

## Альтернатива (без venv)

Если не хотите устанавливать python3-venv, используйте упрощенный скрипт:

```bash
cd /home/crypto/sites/cryptotrader.com/jesse-test
./start_test_server_simple.sh
```

**Внимание**: Упрощенный скрипт использует системный Python и может установить пакеты в пользовательскую директорию (`~/.local`).


