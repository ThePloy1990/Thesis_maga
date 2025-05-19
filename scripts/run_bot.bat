@echo off
REM Активация виртуального окружения
call venv\Scripts\activate.bat

REM Переход в корневую директорию проекта
cd %~dp0\..

REM Установка переменной окружения PYTHONPATH
set PYTHONPATH=%PYTHONPATH%;%CD%

REM Настройка для тестирования
set DATABASE_URL=sqlite:///users.db

REM Запуск бота с использованием .env файла
echo Запуск Telegram бота...
python src\bot\telegram_bot.py 