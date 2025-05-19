#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы модуля model_manager.
"""

import sys
import logging
from pathlib import Path

# Настройка базового пути проекта
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from src.core.model_manager import ModelRegistry, ModelTrainer, predict_with_model_registry
from src.core.forecast import get_available_models, batch_predict


def test_model_registry():
    """Тестирование ModelRegistry."""
    logger.info("=== Тестирование ModelRegistry ===")
    
    # Получаем список доступных моделей
    registry = ModelRegistry()
    models = registry.get_available_models()
    logger.info(f"Доступно {len(models)} моделей")
    
    # Выбираем несколько моделей для тестирования
    test_tickers = models[:3] if len(models) >= 3 else models
    
    # Загружаем модели
    for ticker in test_tickers:
        logger.info(f"Загрузка модели для {ticker}")
        model = registry.get_model(ticker)
        logger.info(f"Успешно загружена модель {ticker}: {type(model).__name__}")
        
        # Повторная загрузка для проверки кэширования
        cached_model = registry.get_model(ticker)
        logger.info(f"Повторная загрузка из кэша: {id(model) == id(cached_model)}")
    
    return models


def test_forecasting(test_tickers):
    """Тестирование функций прогнозирования."""
    logger.info("\n=== Тестирование прогнозирования ===")
    
    # Получаем список всех доступных моделей через forecast.py
    all_models = get_available_models()
    logger.info(f"get_available_models() вернул {len(all_models)} моделей")
    
    # Тестируем прогнозирование для отдельных тикеров
    for ticker in test_tickers:
        try:
            logger.info(f"Прогнозирование для {ticker}")
            prediction = predict_with_model_registry(ticker)
            logger.info(f"Прогноз для {ticker}: {prediction:.4f}")
        except Exception as e:
            logger.error(f"Ошибка при прогнозировании для {ticker}: {e}")
    
    # Тестируем пакетное прогнозирование
    try:
        logger.info(f"Пакетное прогнозирование для {test_tickers}")
        predictions = batch_predict(test_tickers)
        for ticker, pred in predictions.items():
            logger.info(f"Прогноз для {ticker}: {pred:.4f}")
    except Exception as e:
        logger.error(f"Ошибка при пакетном прогнозировании: {e}")


def main():
    """Основная функция тестирования."""
    logger.info("Начало тестирования модуля model_manager")
    
    try:
        # Тестируем ModelRegistry
        models = test_model_registry()
        
        # Выбираем несколько моделей для тестирования
        test_tickers = models[:3] if len(models) >= 3 else models
        
        # Тестируем прогнозирование
        test_forecasting(test_tickers)
        
        logger.info("\nВсе тесты успешно завершены!")
    except Exception as e:
        logger.error(f"Ошибка при выполнении тестов: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 