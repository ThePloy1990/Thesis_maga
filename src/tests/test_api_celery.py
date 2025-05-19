#!/usr/bin/env python
"""
Скрипт для тестирования полного цикла работы API и Celery.
"""
import os
import sys
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Добавляем корневую директорию проекта в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загружаем переменные окружения
load_dotenv()

def test_api_status():
    """Проверяем статус API сервера"""
    logger.info("Проверка статуса API сервера")
    
    try:
        api_url = "http://localhost:8000/docs"
        response = requests.get(api_url)
        if response.status_code == 200:
            logger.info("✅ API сервер работает")
            return True
        else:
            logger.error(f"❌ API сервер вернул статус-код {response.status_code}")
            return False
    except requests.RequestException as e:
        logger.error(f"❌ API сервер недоступен: {e}")
        logger.error("Убедитесь, что API сервер запущен (scripts/run_api.bat)")
        return False

def test_users_endpoint():
    """Проверяем API эндпоинт пользователей"""
    logger.info("Проверка API эндпоинта пользователей")
    
    try:
        users_url = "http://localhost:8000/users/"
        response = requests.get(users_url)
        if response.status_code == 200:
            users = response.json()
            logger.info(f"✅ API вернул {len(users)} пользователей")
            return True, users
        else:
            logger.error(f"❌ Не удалось получить список пользователей: {response.status_code} - {response.text}")
            return False, []
    except Exception as e:
        logger.error(f"❌ Ошибка при получении пользователей: {e}")
        return False, []

def test_newsletter():
    """Проверяем рассылку сообщений через API"""
    logger.info("Проверка API рассылки сообщений")
    
    try:
        newsletter_url = "http://localhost:8000/newsletter/"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"Тестовое сообщение отправлено через API в {timestamp}"
        response = requests.post(newsletter_url, json={"message": message})
        
        if response.status_code == 200:
            task_id = response.json().get("task_id")
            logger.info(f"✅ Задача рассылки поставлена в очередь: {task_id}")
            return True, task_id
        else:
            logger.error(f"❌ Не удалось создать задачу рассылки: {response.status_code} - {response.text}")
            return False, None
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке рассылки: {e}")
        return False, None

def test_full_cycle():
    """Проверяем полный цикл работы с API, Celery, и Telegram."""
    logger.info("=== Начало полного тестирования системы ===")
    
    # 1. Проверяем, что API сервер запущен
    if not test_api_status():
        return False
    
    # 2. Получаем список пользователей через API
    users_success, users = test_users_endpoint()
    if not users_success:
        return False
    
    if len(users) == 0:
        logger.warning("⚠️ В системе нет зарегистрированных пользователей")
        logger.warning("Зарегистрируйте пользователя через бот командой /register")
        return False
    
    # 3. Отправляем тестовое сообщение через API
    newsletter_success, task_id = test_newsletter()
    if not newsletter_success:
        return False
    
    # 4. Ожидаем завершения задачи
    logger.info("Ожидаем обработки задачи Celery...")
    time.sleep(5)  # Даем время на обработку задачи
    
    logger.info(f"✅ Полное тестирование успешно выполнено")
    logger.info("⚠️ Проверьте логи Celery worker для подтверждения обработки задачи")
    logger.info("⚠️ Также проверьте сообщение в Telegram для подтверждения доставки")
    
    return True

if __name__ == "__main__":
    success = test_full_cycle()
    logger.info("=== Тестирование завершено ===")
    
    # Сохраняем результаты
    results_file = os.path.join("data", f"api_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    os.makedirs("data", exist_ok=True)
    
    with open(results_file, "w", encoding="utf-8") as f:
        import json
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "success": success
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Результаты сохранены в {results_file}")
    
    sys.exit(0 if success else 1) 