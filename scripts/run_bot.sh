#!/bin/bash

# Активация виртуального окружения
source venv/bin/activate

# Установка переменных окружения
export TELEGRAM_BOT_TOKEN="ВАШ_ТОКЕН_ТЕЛЕГРАМ_БОТА"
export OPENAI_API_KEY="ВАШ_КЛЮЧ_API_OPENAI"

# Запуск бота
python telegram_bot.py 