@echo off
REM Активация виртуального окружения
call venv\Scripts\activate.bat

REM Переход в корневую директорию проекта
cd %~dp0\..

REM Установка переменной окружения PYTHONPATH
set PYTHONPATH=%PYTHONPATH%;%CD%

REM Настройка для тестирования без Redis
set CELERY_BROKER_URL=memory://
set DATABASE_URL=sqlite:///users.db

REM Запуск FastAPI через Uvicorn
echo Запуск API сервера на http://localhost:8000 ...
uvicorn src.services.api:app --reload --host 0.0.0.0 --port 8000 