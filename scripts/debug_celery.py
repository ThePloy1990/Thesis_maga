#!/usr/bin/env python
"""
Скрипт для отладки Celery задачи отправки сообщений.
"""
import os
import sys
import logging
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Добавляем корневую директорию проекта в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загружаем переменные окружения
load_dotenv()

def debug_celery_task():
    """Отлаживает задачу Celery напрямую, без брокера."""
    # Импортируем необходимые функции и объекты
    from src.celery_app import send_newsletter_task, BOT_TOKEN, bot, send_telegram_message
    
    # Проверяем настройки бота
    logger.debug(f"BOT_TOKEN доступен: {bool(BOT_TOKEN)}")
    logger.debug(f"Бот инициализирован: {bool(bot)}")
    
    # Тестируем вспомогательную функцию
    test_user_id = None
    
    # Проверяем базу данных
    from src.models import SessionLocal, User
    session = SessionLocal()
    users = session.query(User).all()
    logger.debug(f"Пользователей в базе: {len(users)}")
    for user in users:
        logger.debug(f"ID: {user.telegram_id}, Имя: {user.name}")
        if test_user_id is None:
            test_user_id = user.telegram_id
    session.close()
    
    if test_user_id:
        # Тестируем прямую отправку одному пользователю
        logger.debug(f"Тестируем отправку сообщения пользователю {test_user_id}")
        test_result = send_telegram_message(test_user_id, "Тестовое сообщение из debug_celery.py (одиночная отправка)")
        logger.debug(f"Результат прямой отправки: {test_result}")
    
    # Запускаем задачу напрямую (без Celery)
    message = "Тестовое сообщение из debug_celery.py (без брокера)"
    logger.debug(f"Отправляем сообщение всем пользователям: {message}")
    
    try:
        # Вызов функции напрямую, не через Celery
        send_newsletter_task(message)
        logger.debug("Задача выполнена")
    except Exception as e:
        logger.error(f"Ошибка при выполнении задачи: {e}", exc_info=True)

if __name__ == "__main__":
    print("Запускаем отладку Celery задачи...")
    debug_celery_task()
    print("Отладка завершена.") 