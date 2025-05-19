#!/usr/bin/env python
"""
Скрипт для тестирования отправки сообщения напрямую пользователю.
"""
import os
import sys
import asyncio
from dotenv import load_dotenv
from telegram import Bot
import sqlite3
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Добавляем корневую директорию проекта в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загружаем переменные окружения
load_dotenv()

async def send_telegram_message(bot, chat_id, text):
    """Асинхронно отправляет сообщение через Telegram бота."""
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке: {e}")
        return False

async def send_messages_async():
    """Асинхронная функция для отправки всех сообщений."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.error("ОШИБКА: Не задан TELEGRAM_BOT_TOKEN в .env")
        return
        
    # Инициализируем бота
    bot = Bot(token=bot_token)
    
    # Получаем список пользователей из базы данных
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id FROM users")
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        logger.error("ОШИБКА: В базе данных нет пользователей")
        return
        
    # Отправляем сообщение каждому пользователю
    message = "Тестовое сообщение, отправленное напрямую через бота (не через Celery)!"
    success_count = 0
    
    for user in users:
        telegram_id = user[0]
        success = await send_telegram_message(bot, telegram_id, message)
        if success:
            logger.info(f"Сообщение успешно отправлено пользователю {telegram_id}")
            success_count += 1
    
    logger.info(f"Сообщения отправлены {success_count} из {len(users)} пользователей")

def send_direct_message():
    """Отправляет тестовое сообщение напрямую пользователю."""
    asyncio.run(send_messages_async())

if __name__ == "__main__":
    send_direct_message() 