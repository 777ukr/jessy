# Как открыть Jesse Test в отдельном окне

## Способ 1: Через меню File (Рекомендуется)

1. **File → Open Workspace from File...**
2. Перейдите в: `/home/crypto/sites/cryptotrader.com/jesse-test/`
3. Выберите файл: `jesse.code-workspace`
4. Нажмите **Open**

Jesse Test откроется в текущем окне Cursor.

## Способ 2: Открыть в новом окне

### Вариант A: Через командную палитру

1. Нажмите `Ctrl+Shift+P` (или `Cmd+Shift+P` на Mac)
2. Введите: `Workspaces: Duplicate Workspace in New Window`
3. Выберите команду
4. Jesse Test откроется в новом окне

### Вариант B: Через терминал

```bash
# Открыть в новом окне Cursor
cursor /home/crypto/sites/cryptotrader.com/jesse-test/jesse.code-workspace --new-window

# Или через code (если установлен)
code /home/crypto/sites/cryptotrader.com/jesse-test/jesse.code-workspace --new-window
```

### Вариант C: Через контекстное меню

1. В проводнике (Explorer) найдите файл `jesse.code-workspace`
2. Правый клик → **Open in New Window**

## Способ 3: Быстрый запуск через скрипт

Создайте скрипт для быстрого открытия:

```bash
#!/bin/bash
# Открыть Jesse Test в новом окне
cursor /home/crypto/sites/cryptotrader.com/jesse-test/jesse.code-workspace --new-window
```

## Проверка

После открытия проверьте:

1. ✅ В заголовке окна должно быть: `jesse.code-workspace`
2. ✅ В Explorer должна быть только папка `jesse-test`
3. ✅ `.cursorrules` должен быть применен (проверьте через `@rules`)

## Запуск сервера

После открытия workspace:

```bash
cd /home/crypto/sites/cryptotrader.com/jesse-test
./start_test_server_simple.sh
```

Сервер запустится на порту **9001**: http://localhost:9001

