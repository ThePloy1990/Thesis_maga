import logging
import asyncio
import json
from typing import Tuple, List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from ..pf_agents import Runner
from ..tools.forecast_tool import forecast_tool  
from ..tools.optimize_tool import optimize_tool
from ..tools.sentiment_tool import sentiment_tool
from ..tools.scenario_tool import scenario_adjust_tool
from ..market_snapshot.registry import SnapshotRegistry

logger = logging.getLogger(__name__)

# Пул исполнителей для асинхронного запуска агента
_executor = ThreadPoolExecutor(max_workers=4)

async def run_portfolio_manager(text: str, state: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Асинхронно запускает портфельного агента-менеджера.
    
    Args:
        text: Запрос пользователя
        state: Состояние пользователя
        
    Returns:
        Кортеж из markdown-текста и списка путей к изображениям
    """
    logger.info(f"Running portfolio manager with text: {text[:100]}...")
    
    try:
        # Запускаем выполнение в отдельном потоке, чтобы не блокировать event loop
        return await asyncio.get_event_loop().run_in_executor(
            _executor, _run_portfolio_manager_sync, text, state
        )
    except Exception as e:
        logger.error(f"Error running portfolio manager: {str(e)}")
        return f"Произошла ошибка при обработке запроса: {str(e)}", []

def _run_portfolio_manager_sync(text: str, state: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Синхронная версия запуска портфельного агента.
    
    Args:
        text: Запрос пользователя
        state: Состояние пользователя
        
    Returns:
        Кортеж из markdown-текста и списка путей к изображениям
    """
    # Здесь будет вызов агента-менеджера из ядра
    # Пока используем заглушку для примера
    response_text = f"Обработка запроса: {text}\n\nРиск-профиль: {state.get('risk_profile', 'не указан')}\nБюджет: ${state.get('budget', 0):,.2f}"
    
    # Список путей к изображениям (пустой в заглушке)
    image_paths = []
    
    # TODO: Интегрировать с реальным агентом-менеджером
    # runner = Runner()
    # result = runner.run(...)
    
    # Добавляем disclaimer в конец только если его нет
    return response_text, image_paths

async def build_snapshot() -> str:
    """
    Асинхронно запускает билд нового снапшота.
    
    Returns:
        ID нового снапшота или сообщение об ошибке
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            _executor, _build_snapshot_sync
        )
    except Exception as e:
        logger.error(f"Error building snapshot: {str(e)}")
        return f"Ошибка при обновлении снапшота: {str(e)}"

def _build_snapshot_sync() -> str:
    """
    Синхронная версия билда снапшота.
    
    Returns:
        ID нового снапшота
    """
    # Здесь будет код для создания нового снапшота
    # В будущем интегрировать с реальным кодом построения снапшота
    
    registry = SnapshotRegistry()
    # Получаем последний снапшот
    latest_snapshot = registry.latest()
    
    if latest_snapshot:
        return f"Снапшот обновлен: {latest_snapshot.meta.id}"
    else:
        return "Ошибка: не удалось получить снапшот"

async def get_latest_snapshot_info() -> Dict[str, Any]:
    """
    Асинхронно получает информацию о последнем снапшоте.
    
    Returns:
        Словарь с информацией о последнем снапшоте
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            _executor, _get_latest_snapshot_info_sync
        )
    except Exception as e:
        logger.error(f"Error getting snapshot info: {str(e)}")
        return {"error": str(e)}

def _get_latest_snapshot_info_sync() -> Dict[str, Any]:
    """
    Синхронная версия получения информации о последнем снапшоте.
    
    Returns:
        Словарь с информацией о последнем снапшоте
    """
    registry = SnapshotRegistry()
    latest_snapshot = registry.latest()
    
    if latest_snapshot:
        return {
            "snapshot_id": latest_snapshot.meta.id,
            "timestamp": latest_snapshot.meta.timestamp.isoformat(),
            "tickers": latest_snapshot.meta.tickers,
            "error": None
        }
    else:
        return {
            "snapshot_id": None,
            "timestamp": None,
            "tickers": None,
            "error": "Не удалось получить снапшот"
        } 