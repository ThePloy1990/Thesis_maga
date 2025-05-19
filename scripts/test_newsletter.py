#!/usr/bin/env python
"""
Скрипт для тестирования функции рассылки через Celery.
"""
import os
import sys
import requests
from dotenv import load_dotenv

# Добавляем корневую директорию проекта в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загружаем переменные окружения
load_dotenv()

def test_newsletter():
    """Отправляет тестовое сообщение через API рассылки."""
    message = "Тестовое сообщение рассылки. Это сообщение отправлено через Celery!"
    api_url = "http://localhost:8000/newsletter/"
    
    try:
        response = requests.post(api_url, json={"message": message})
        if response.status_code == 200:
            print(f"Успешно! Ответ API: {response.json()}")
        else:
            print(f"Ошибка: {response.status_code}, {response.text}")
    except requests.RequestException as e:
        print(f"Ошибка соединения: {e}")
        print("Убедитесь, что API запущен через scripts/run_api.sh")

if __name__ == "__main__":
    test_newsletter() 