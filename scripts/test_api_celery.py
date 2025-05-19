#!/usr/bin/env python
"""
Скрипт для тестирования полного цикла работы API и Celery.
"""
import os
import sys
import requests
import time
from dotenv import load_dotenv
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Добавляем корневую директорию проекта в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загружаем переменные окружения
load_dotenv()

def test_full_cycle():
    """Проверяем полный цикл работы с API, Celery, и Telegram."""
    logger.info("Начинаем полное тестирование системы")
    
    # 1. Проверяем, что API сервер запущен
    try:
        api_url = "http://localhost:8000/docs"
        response = requests.get(api_url)
        if response.status_code == 200:
            logger.info("✅ API сервер работает")
        else:
            logger.error(f"❌ API сервер вернул статус-код {response.status_code}")
            return
    except requests.RequestException as e:
        logger.error(f"❌ API сервер недоступен: {e}")
        logger.error("Убедитесь, что API сервер запущен (scripts/run_api.bat)")
        return
        
    # 2. Получаем список пользователей через API
    try:
        users_url = "http://localhost:8000/users/"
        response = requests.get(users_url)
        if response.status_code == 200:
            users = response.json()
            logger.info(f"✅ API вернул {len(users)} пользователей")
            if len(users) == 0:
                logger.warning("⚠️ В системе нет зарегистрированных пользователей")
                logger.warning("Зарегистрируйте пользователя через бот командой /register")
                return
        else:
            logger.error(f"❌ Не удалось получить список пользователей: {response.status_code} - {response.text}")
            return
    except Exception as e:
        logger.error(f"❌ Ошибка при получении пользователей: {e}")
        return
        
    # 3. Отправляем тестовое сообщение через API
    try:
        newsletter_url = "http://localhost:8000/newsletter/"
        message = f"Тестовое сообщение отправлено через API в {time.strftime('%H:%M:%S')}"
        response = requests.post(newsletter_url, json={"message": message})
        
        if response.status_code == 200:
            logger.info(f"✅ Задача рассылки поставлена в очередь: {response.json()}")
            logger.info("⚠️ Проверьте логи Celery worker для подтверждения обработки задачи")
            logger.info("⚠️ Также проверьте сообщение в Telegram для подтверждения доставки")
        else:
            logger.error(f"❌ Не удалось создать задачу рассылки: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке рассылки: {e}")
    
    logger.info("Тестирование завершено")

if __name__ == "__main__":
    test_full_cycle() 