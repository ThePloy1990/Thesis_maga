# Telegram-бот Thesis_maga

Этот репозиторий содержит Telegram-бота для оптимизации инвестиционного портфеля с использованием OpenAI и финансовых данных.

## Настройка окружения

1. Создайте и активируйте виртуальное окружение:

Для Linux/Mac:
```bash
python -m venv venv
source venv/bin/activate
```

Для Windows:
```cmd
python -m venv venv
venv\Scripts\activate
```

2. Установите зависимости из `requirements.txt`:

```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` в корневой директории проекта и добавьте необходимые переменные окружения:

```
TELEGRAM_BOT_TOKEN=ваш_токен_бота
OPENAI_API_KEY=ваш_api_ключ
DATABASE_URL=postgresql://user:password@localhost:5432/mydb
REDIS_URL=redis://localhost:6379/0
```

4. Настройте Redis (необходим для работы Celery):

Для Linux/Mac:
```bash
# Установка Redis (для Ubuntu/Debian)
sudo apt install redis-server
```

Для Windows:
```
# Скачайте и установите Redis с официального репозитория:
# https://github.com/tporadowski/redis/releases
```

## Запуск бота

Для Linux/Mac:
```bash
bash scripts/run_bot.sh
```

Для Windows:
```cmd
scripts\run_bot.bat
```

Скрипт активирует окружение и запускает `telegram_bot.py`, который автоматически загрузит переменные из файла `.env`.

## Запуск Celery и API

Для работы с фоновыми задачами и API:

Для Linux/Mac:
```bash
# Запуск Celery worker для обработки фоновых задач
bash scripts/run_celery.sh

# В другом терминале запустите API
bash scripts/run_api.sh
```

Для Windows:
```cmd
# Запуск Celery worker для обработки фоновых задач
scripts\run_celery.bat

# В другом терминале запустите API
scripts\run_api.bat
```

После этого API будет доступен по адресу http://localhost:8000, а документация API - по адресу http://localhost:8000/docs

## Тестирование рассылки сообщений

Для тестирования рассылки используйте:

```bash
python scripts/test_newsletter.py
```

## Функция прогноза

Бот умеет прогнозировать стоимость акций с помощью моделей CatBoost. Файлы моделей находятся в каталоге `models/` и имеют вид `catboost_*.cbm`, каждая модель соответствует отдельной акции.

## Расположение моделей CatBoost

Все обученные модели CatBoost находятся в директории `models`. Скрипты бота предполагают, что она расположена в корне репозитория.

