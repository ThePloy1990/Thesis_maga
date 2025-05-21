import json
import redis
from typing import Dict, Any, Optional
import logging

from .config import REDIS_URL

# Настраиваем логирование
logger = logging.getLogger(__name__)

# Подключение к Redis
try:
    redis_client = redis.from_url(REDIS_URL)
    logger.info(f"Connected to Redis at {REDIS_URL}")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {str(e)}")
    redis_client = None

# Префикс для ключей пользователей в Redis
USER_STATE_PREFIX = "user_state:"

def get_user_state(user_id: int) -> Dict[str, Any]:
    """
    Получает состояние пользователя из Redis.
    
    Args:
        user_id: ID пользователя в Telegram
        
    Returns:
        Dictionary с состоянием пользователя или пустой словарь, если состояние не найдено
    """
    if not redis_client:
        logger.warning("Redis client not available. Returning default state.")
        return create_default_state(user_id)
    
    try:
        state_json = redis_client.get(f"{USER_STATE_PREFIX}{user_id}")
        if state_json:
            return json.loads(state_json)
        else:
            return create_default_state(user_id)
    except Exception as e:
        logger.error(f"Error retrieving user state: {str(e)}")
        return create_default_state(user_id)

def save_user_state(user_id: int, state: Dict[str, Any]) -> bool:
    """
    Сохраняет состояние пользователя в Redis.
    
    Args:
        user_id: ID пользователя в Telegram
        state: словарь с состоянием пользователя
        
    Returns:
        True при успешном сохранении, False при ошибке
    """
    if not redis_client:
        logger.warning("Redis client not available. State not saved.")
        return False
    
    try:
        state_json = json.dumps(state)
        redis_client.set(f"{USER_STATE_PREFIX}{user_id}", state_json)
        return True
    except Exception as e:
        logger.error(f"Error saving user state: {str(e)}")
        return False

def create_default_state(user_id: int) -> Dict[str, Any]:
    """
    Создает состояние пользователя по умолчанию.
    
    Args:
        user_id: ID пользователя в Telegram
        
    Returns:
        Dictionary с состоянием пользователя по умолчанию
    """
    return {
        "user_id": user_id,
        "risk_profile": "moderate",
        "budget": 10000,  # Значение по умолчанию 10,000 USD
        "positions": {},  # Пустой портфель по умолчанию
        "last_snapshot_id": None,  # Будет заполнено при первом запросе снапшота
        "dialog_memory": []  # Пустая история диалога
    }

def update_dialog_memory(user_id: int, message: str, role: str = "user") -> bool:
    """
    Добавляет сообщение в историю диалога пользователя.
    
    Args:
        user_id: ID пользователя в Telegram
        message: текст сообщения
        role: роль отправителя ('user' или 'assistant')
        
    Returns:
        True при успешном обновлении, False при ошибке
    """
    try:
        state = get_user_state(user_id)
        state["dialog_memory"].append({
            "role": role,
            "content": message
        })
        
        # Ограничиваем историю диалога последними 10 сообщениями
        if len(state["dialog_memory"]) > 10:
            state["dialog_memory"] = state["dialog_memory"][-10:]
        
        return save_user_state(user_id, state)
    except Exception as e:
        logger.error(f"Error updating dialog memory: {str(e)}")
        return False

def reset_user_state(user_id: int) -> bool:
    """
    Сбрасывает состояние пользователя на значения по умолчанию.
    
    Args:
        user_id: ID пользователя в Telegram
        
    Returns:
        True при успешном сбросе, False при ошибке
    """
    try:
        default_state = create_default_state(user_id)
        return save_user_state(user_id, default_state)
    except Exception as e:
        logger.error(f"Error resetting user state: {str(e)}")
        return False

def update_risk_profile(user_id: int, risk_profile: str) -> bool:
    """
    Обновляет профиль риска пользователя.
    
    Args:
        user_id: ID пользователя в Telegram
        risk_profile: профиль риска ('conservative', 'moderate', 'aggressive')
        
    Returns:
        True при успешном обновлении, False при ошибке
    """
    if risk_profile not in ['conservative', 'moderate', 'aggressive']:
        logger.warning(f"Invalid risk profile: {risk_profile}")
        return False
    
    try:
        state = get_user_state(user_id)
        state["risk_profile"] = risk_profile
        return save_user_state(user_id, state)
    except Exception as e:
        logger.error(f"Error updating risk profile: {str(e)}")
        return False

def update_budget(user_id: int, budget: float) -> bool:
    """
    Обновляет бюджет пользователя.
    
    Args:
        user_id: ID пользователя в Telegram
        budget: бюджет в USD
        
    Returns:
        True при успешном обновлении, False при ошибке
    """
    try:
        state = get_user_state(user_id)
        state["budget"] = budget
        return save_user_state(user_id, state)
    except Exception as e:
        logger.error(f"Error updating budget: {str(e)}")
        return False

def update_positions(user_id: int, positions: Dict[str, float]) -> bool:
    """
    Обновляет текущие позиции пользователя.
    
    Args:
        user_id: ID пользователя в Telegram
        positions: словарь с позициями {ticker: количество}
        
    Returns:
        True при успешном обновлении, False при ошибке
    """
    try:
        state = get_user_state(user_id)
        state["positions"] = positions
        return save_user_state(user_id, state)
    except Exception as e:
        logger.error(f"Error updating positions: {str(e)}")
        return False

def update_snapshot_id(user_id: int, snapshot_id: str) -> bool:
    """
    Обновляет ID последнего использованного снапшота.
    
    Args:
        user_id: ID пользователя в Telegram
        snapshot_id: ID снапшота
        
    Returns:
        True при успешном обновлении, False при ошибке
    """
    try:
        state = get_user_state(user_id)
        state["last_snapshot_id"] = snapshot_id
        return save_user_state(user_id, state)
    except Exception as e:
        logger.error(f"Error updating snapshot ID: {str(e)}")
        return False 