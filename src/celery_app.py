import os
from celery import Celery
from models import SessionLocal, User
from telegram import Bot
import logging

# Конфигурация брокера и бэкенда
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
celery = Celery('tasks', broker=REDIS_URL, backend=REDIS_URL)

# Настройка бота
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@celery.task
def send_newsletter_task(message: str):
    """Отправляет сообщение всем зарегистрированным пользователям"""
    session = SessionLocal()
    try:
        users = session.query(User).all()
        for user in users:
            if user.telegram_id:
                try:
                    bot.send_message(chat_id=user.telegram_id, text=message)
                except Exception as e:
                    logger.error(f"Ошибка при отправке пользователю {user.telegram_id}: {e}")
    finally:
        session.close() 