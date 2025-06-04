import json
import redis
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timezone

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
    # Автоматически назначаем последний снапшот для нового пользователя
    last_snapshot_id = None
    try:
        from ..market_snapshot.registry import SnapshotRegistry
        registry = SnapshotRegistry()
        latest_snapshot = registry.latest()
        if latest_snapshot:
            last_snapshot_id = latest_snapshot.meta.id or latest_snapshot.meta.snapshot_id
            logger.info(f"Assigned latest snapshot {last_snapshot_id} to new user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to get latest snapshot for new user {user_id}: {e}")
    
    return {
        "user_id": user_id,
        "risk_profile": "moderate",
        "budget": 10000,  # Значение по умолчанию 10,000 USD
        "positions": {},  # Пустой портфель по умолчанию
        "last_snapshot_id": last_snapshot_id,  # Автоматически назначается последний снапшот
        "dialog_memory": [],  # Пустая история диалога
        "portfolio_history": []  # История портфельных позиций
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

def save_portfolio_snapshot(user_id: int, snapshot_name: str = None) -> bool:
    """
    Сохраняет текущие позиции пользователя в историю портфеля.
    
    Args:
        user_id: ID пользователя в Telegram
        snapshot_name: Опциональное имя снэпшота портфеля
        
    Returns:
        True при успешном сохранении, False при ошибке
    """
    try:
        state = get_user_state(user_id)
        current_positions = state.get("positions", {})
        
        if not current_positions:
            logger.warning(f"Attempted to save empty portfolio for user {user_id}")
            return False
            
        # Получаем данные о текущих ценах для расчета стоимости
        from ..market_snapshot.registry import SnapshotRegistry
        registry = SnapshotRegistry()
        latest_snapshot = registry.latest()
        
        # Установка цен по умолчанию (100 за единицу)
        default_price = 100.0
        prices = {}
        
        # Безопасное получение цен из снапшота
        try:
            if latest_snapshot:
                if hasattr(latest_snapshot, 'prices') and latest_snapshot.prices:
                    prices = latest_snapshot.prices
                    logger.info(f"Got prices from snapshot for {len(prices)} tickers")
        except Exception as price_error:
            logger.warning(f"Error getting prices from snapshot: {price_error}")
        
        # Рассчитываем стоимость портфеля
        portfolio_value = 0
        position_values = {}
        
        for ticker, amount in current_positions.items():
            # Безопасное получение цены с обработкой всех возможных ошибок
            try:
                price = prices.get(ticker)
                if price is None or not isinstance(price, (int, float)):
                    price = default_price
                    logger.debug(f"Using default price {default_price} for {ticker}")
            except Exception:
                price = default_price
                logger.debug(f"Error getting price for {ticker}, using default price {default_price}")
                
            value = float(amount) * float(price)
            portfolio_value += value
            position_values[ticker] = value
        
        # Создаем снимок портфеля
        timestamp = datetime.now(timezone.utc)
        portfolio_snapshot = {
            "timestamp": timestamp.isoformat(),
            "name": snapshot_name or f"Portfolio {timestamp.strftime('%Y-%m-%d')}",
            "positions": current_positions.copy(),
            "position_values": position_values,
            "portfolio_value": portfolio_value,
            "snapshot_id": state.get("last_snapshot_id")
        }
        
        # Добавляем снимок в историю портфеля
        if "portfolio_history" not in state:
            state["portfolio_history"] = []
        
        state["portfolio_history"].append(portfolio_snapshot)
        
        # Сохраняем обновленное состояние
        return save_user_state(user_id, state)
    
    except Exception as e:
        logger.error(f"Error saving portfolio snapshot: {str(e)}")
        return False

def get_portfolio_history(user_id: int) -> List[Dict[str, Any]]:
    """
    Получает историю портфельных позиций пользователя.
    
    Args:
        user_id: ID пользователя в Telegram
        
    Returns:
        Список снапшотов портфеля
    """
    try:
        state = get_user_state(user_id)
        return state.get("portfolio_history", [])
    except Exception as e:
        logger.error(f"Error getting portfolio history: {str(e)}")
        return []

def get_all_user_ids() -> List[int]:
    """
    Получает список всех пользователей из Redis.
    
    Returns:
        Список ID всех пользователей
    """
    if not redis_client:
        logger.warning("Redis client not available. Returning empty list.")
        return []
    
    try:
        # Получаем все ключи с префиксом пользователей
        user_keys = redis_client.keys(f"{USER_STATE_PREFIX}*")
        user_ids = []
        
        for key in user_keys:
            # Преобразуем bytes в str если необходимо
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            # Извлекаем user_id из ключа
            user_id_str = key_str.replace(USER_STATE_PREFIX, "")
            try:
                user_id = int(user_id_str)
                user_ids.append(user_id)
            except ValueError:
                logger.warning(f"Invalid user ID in key: {key_str}")
                continue
        
        return sorted(user_ids)
    except Exception as e:
        logger.error(f"Error getting all user IDs: {str(e)}")
        return [] 