#!/usr/bin/env python3
"""
Скрипт для инициализации базы данных пользователей
в Redis с начальным состоянием.
"""

import logging
import os
import sys
import json
from typing import Dict, Any
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.bot.state import redis_client, create_default_state, USER_STATE_PREFIX

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def check_redis_connection():
    """Проверяет соединение с Redis."""
    try:
        if not redis_client:
            logger.error("Redis client is None. Check Redis connection settings.")
            return False
        
        # Тестируем соединение
        redis_client.ping()
        logger.info("Successfully connected to Redis")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        return False


def list_users():
    """Получает список всех пользователей в базе данных."""
    try:
        if not check_redis_connection():
            return []
        
        # Получаем все ключи пользователей
        user_keys = redis_client.keys(f"{USER_STATE_PREFIX}*")
        users = []
        
        for user_key in user_keys:
            # Извлекаем ID пользователя из ключа (преобразуем bytes в str)
            user_key_str = user_key.decode('utf-8') if isinstance(user_key, bytes) else user_key
            user_id_str = user_key_str.replace(USER_STATE_PREFIX, "")
            try:
                user_id = int(user_id_str)
                
                # Получаем состояние пользователя
                state_json = redis_client.get(user_key)
                if state_json:
                    state = json.loads(state_json)
                    users.append({
                        "user_id": user_id,
                        "risk_profile": state.get("risk_profile"),
                        "budget": state.get("budget"),
                        "positions": state.get("positions"),
                        "last_snapshot_id": state.get("last_snapshot_id")
                    })
            except ValueError:
                logger.warning(f"Invalid user key format: {user_key}")
                continue
        
        return users
    except Exception as e:
        logger.error(f"Error listing users: {str(e)}")
        return []


def create_user(user_id: int, risk_profile: str = "moderate", budget: float = 10000, positions: Dict[str, float] = None):
    """Создает пользователя с указанными параметрами."""
    try:
        if not check_redis_connection():
            return False
        
        # Создаем состояние по умолчанию
        state = create_default_state(user_id)
        
        # Обновляем параметры, если они указаны
        state["risk_profile"] = risk_profile
        state["budget"] = budget
        if positions:
            state["positions"] = positions
        
        # Сохраняем пользователя в Redis
        state_json = json.dumps(state)
        redis_client.set(f"{USER_STATE_PREFIX}{user_id}", state_json)
        logger.info(f"User {user_id} created with parameters: risk_profile={risk_profile}, budget={budget}")
        return True
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {str(e)}")
        return False


def delete_user(user_id: int):
    """Удаляет пользователя из базы данных."""
    try:
        if not check_redis_connection():
            return False
        
        # Удаляем пользователя из Redis
        result = redis_client.delete(f"{USER_STATE_PREFIX}{user_id}")
        if result:
            logger.info(f"User {user_id} deleted")
            return True
        else:
            logger.warning(f"User {user_id} not found")
            return False
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        return False


def reset_db():
    """Сбрасывает всю базу данных пользователей."""
    try:
        if not check_redis_connection():
            return False
        
        # Получаем все ключи пользователей
        user_keys = redis_client.keys(f"{USER_STATE_PREFIX}*")
        
        if user_keys:
            # Преобразуем ключи в строки если они bytes
            user_keys_fixed = []
            for key in user_keys:
                if isinstance(key, bytes):
                    user_keys_fixed.append(key.decode('utf-8'))
                else:
                    user_keys_fixed.append(key)
            
            # Удаляем все ключи
            redis_client.delete(*user_keys_fixed)
            logger.info(f"Deleted {len(user_keys_fixed)} user records from database")
        else:
            logger.info("No users found in database")
        
        return True
    except Exception as e:
        logger.error(f"Error resetting database: {str(e)}")
        return False


def main():
    """Основная функция для интерактивной работы с базой данных."""
    print("=== Portfolio Assistant Database Management ===")
    
    if not check_redis_connection():
        print("Ошибка подключения к Redis. Проверьте настройки соединения.")
        sys.exit(1)
    
    while True:
        print("\nВыберите действие:")
        print("1. Просмотреть список пользователей")
        print("2. Создать нового пользователя")
        print("3. Удалить пользователя")
        print("4. Сбросить базу данных")
        print("0. Выйти")
        
        choice = input("Ваш выбор: ")
        
        if choice == "1":
            users = list_users()
            if users:
                print(f"\nНайдено {len(users)} пользователей:")
                for user in users:
                    print(f"ID: {user['user_id']}, Риск-профиль: {user['risk_profile']}, " 
                          f"Бюджет: ${user['budget']}, Позиции: {user['positions']}")
            else:
                print("\nПользователи не найдены.")
        
        elif choice == "2":
            try:
                user_id = int(input("Введите ID пользователя: "))
                risk_profile = input("Введите риск-профиль (conservative/moderate/aggressive) [moderate]: ") or "moderate"
                budget_str = input("Введите бюджет [10000]: ") or "10000"
                budget = float(budget_str)
                
                positions_str = input("Введите позиции в формате JSON (например, {\"AAPL\": 10}) [{}]: ") or "{}"
                positions = json.loads(positions_str)
                
                if create_user(user_id, risk_profile, budget, positions):
                    print(f"Пользователь {user_id} успешно создан.")
                else:
                    print(f"Ошибка при создании пользователя {user_id}.")
            except ValueError as e:
                print(f"Ошибка ввода: {str(e)}")
            except json.JSONDecodeError:
                print("Ошибка в формате JSON для позиций.")
        
        elif choice == "3":
            try:
                user_id = int(input("Введите ID пользователя для удаления: "))
                if delete_user(user_id):
                    print(f"Пользователь {user_id} успешно удален.")
                else:
                    print(f"Пользователь {user_id} не найден или произошла ошибка.")
            except ValueError as e:
                print(f"Ошибка ввода: {str(e)}")
        
        elif choice == "4":
            confirm = input("Вы уверены, что хотите сбросить ВСЮ базу данных? (y/N): ")
            if confirm.lower() == "y":
                if reset_db():
                    print("База данных успешно сброшена.")
                else:
                    print("Ошибка при сбросе базы данных.")
            else:
                print("Сброс базы данных отменен.")
        
        elif choice == "0":
            print("Выход из программы.")
            break
        
        else:
            print("Неверный выбор. Попробуйте еще раз.")


if __name__ == "__main__":
    main() 