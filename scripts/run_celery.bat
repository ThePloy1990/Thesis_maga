@echo off
REM Активация виртуального окружения
call venv\Scripts\activate.bat

REM Переход в корневую директорию проекта
cd %~dp0\..

REM Установка переменной окружения PYTHONPATH
set PYTHONPATH=%PYTHONPATH%;%CD%

REM Настройка для тестирования без Redis
set CELERY_BROKER_URL=memory://

REM Запуск Celery worker
echo Запуск Celery worker в режиме отладки (без Redis)...
celery -A src.services.celery_app worker -l info --pool=solo 