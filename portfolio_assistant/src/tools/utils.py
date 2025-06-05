"""
Утилитарные функции для модуля tools.

Содержит общие функции, используемые несколькими инструментами.
"""

import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def get_models_path() -> Path:
    """
    Возвращает путь к директории с моделями CatBoost.
    
    Returns:
        Path: Путь к директории models
    """
    return Path(__file__).absolute().parent.parent.parent.parent / "models"


def get_available_tickers() -> List[str]:
    """
    Получает список доступных тикеров на основе наличия моделей CatBoost.
    Централизованная версия функции для всего модуля tools.
    
    Returns:
        List[str]: Отсортированный список доступных тикеров
    """
    models_path = get_models_path()
    available_tickers = []
    
    try:
        for model_file in models_path.glob("catboost_*.cbm"):
            ticker = model_file.stem.replace("catboost_", "")
            if ticker and ticker.upper() not in ["TEST", "DUMMY"]:  # Исключаем тестовые модели
                available_tickers.append(ticker)
        
        logger.debug(f"Found {len(available_tickers)} available ticker models")
        return sorted(available_tickers)  # Возвращаем отсортированный список
        
    except Exception as e:
        logger.error(f"Error scanning for available tickers: {e}")
        return []


def validate_tickers(tickers: List[str]) -> tuple[List[str], List[str]]:
    """
    Проверяет список тикеров на доступность.
    
    Args:
        tickers: Список тикеров для проверки
    
    Returns:
        tuple: (доступные_тикеры, недоступные_тикеры)
    """
    if not tickers:
        return [], []
    
    available_tickers = get_available_tickers()
    valid_tickers = [t for t in tickers if t in available_tickers]
    invalid_tickers = [t for t in tickers if t not in available_tickers]
    
    return valid_tickers, invalid_tickers


def check_ticker_model_exists(ticker: str) -> bool:
    """
    Проверяет существование модели для конкретного тикера.
    
    Args:
        ticker: Тикер для проверки
    
    Returns:
        bool: True если модель существует
    """
    models_path = get_models_path()
    model_path = models_path / f"catboost_{ticker}.cbm"
    return model_path.exists()


def format_error_response(error_message: str, **additional_fields) -> dict:
    """
    Форматирует стандартный ответ об ошибке для инструментов.
    
    Args:
        error_message: Сообщение об ошибке
        **additional_fields: Дополнительные поля для включения в ответ
    
    Returns:
        dict: Стандартизированный ответ об ошибке
    """
    response = {
        "error": error_message,
        **additional_fields
    }
    
    # Добавляем список доступных тикеров если его нет
    if "available_tickers" not in response:
        available = get_available_tickers()
        response["available_tickers"] = available[:10] if len(available) > 10 else available
    
    return response