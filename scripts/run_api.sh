#!/bin/bash

# Активация виртуального окружения
source venv/bin/activate

# Настройка переменных окружения через .env файл
cd $(dirname $0)/..

# Запуск FastAPI через Uvicorn
uvicorn src.services.api:app --reload --host 0.0.0.0 --port 8000 