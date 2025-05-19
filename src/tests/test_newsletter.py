#!/usr/bin/env python
"""
Скрипт для тестирования функции рассылки через Celery.
"""
import os
import sys
import json
import requests
import logging
from datetime import datetime
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Добавляем корневую директорию проекта в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загружаем переменные окружения
load_dotenv()

def test_newsletter():
    """Отправляет тестовое сообщение через API рассылки."""
    logger.info("=== Тестирование API рассылки сообщений ===")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"Тестовое сообщение рассылки от {timestamp}. Это сообщение отправлено через Celery!"
    api_url = "http://localhost:8000/newsletter/"
    
    try:
        logger.info(f"Отправка сообщения: '{message}'")
        response = requests.post(api_url, json={"message": message})
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Успешно! Задача поставлена в очередь: {result}")
            
            # Сохраняем успешный результат
            save_result(True, result)
            return True
        else:
            logger.error(f"❌ Ошибка: {response.status_code}, {response.text}")
            
            # Сохраняем неудачный результат
            save_result(False, {"error": f"HTTP {response.status_code}", "details": response.text})
            return False
    except requests.RequestException as e:
        error_msg = f"❌ Ошибка соединения: {e}"
        logger.error(error_msg)
        logger.error("Убедитесь, что API запущен через scripts/run_api.sh")
        
        # Сохраняем информацию об ошибке
        save_result(False, {"error": "ConnectionError", "details": str(e)})
        return False

def save_result(success, details):
    """Сохраняет результаты теста в JSON файл."""
    results_dir = os.path.join("data", "test_results")
    os.makedirs(results_dir, exist_ok=True)
    
    results_file = os.path.join(results_dir, f"newsletter_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    
    result = {
        "timestamp": datetime.now().isoformat(),
        "success": success,
        "details": details
    }
    
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Результаты теста сохранены в {results_file}")

if __name__ == "__main__":
    success = test_newsletter()
    logger.info("=== Тестирование завершено ===")
    sys.exit(0 if success else 1) 