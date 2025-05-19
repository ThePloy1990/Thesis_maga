#!/bin/bash

# Активация виртуального окружения
source venv/bin/activate

# Настройка переменных окружения через .env файл
cd $(dirname $0)/..

# Запуск Celery worker
celery -A src.services.celery_app worker --loglevel=info 