#!/usr/bin/env python
"""
Тестовый скрипт для проверки импортов из всех модулей проекта.
"""
import os
import sys
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Текущий каталог
logger.info(f"Текущий каталог: {os.getcwd()}")

def test_data_collection_imports():
    """Проверяем импорты из модуля data_collection"""
    logger.info("=== Тестирование импортов из data_collection ===")
    try:
        from data_collection import (
            StockDataCollector,
            CryptoDataCollector,
            NewsCollector,
            SentimentAnalyzer
        )
        logger.info("✅ Импорты из data_collection успешны")
        return True
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта из data_collection: {e}")
        return False

def test_core_imports():
    """Проверяем импорты из модуля core"""
    logger.info("=== Тестирование импортов из core ===")
    try:
        from core import (
            load_price_data,
            calculate_returns,
            optimize_portfolio,
            calculate_var_cvar,
            predict_with_catboost,
            PortfolioManagerAgent,
            create_performance_chart
        )
        logger.info("✅ Импорты из core успешны")
        return True
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта из core: {e}")
        return False

def test_services_imports():
    """Проверяем импорты из модуля services"""
    logger.info("=== Тестирование импортов из services ===")
    try:
        from services import User, SessionLocal, Base
        logger.info("✅ Импорты из services успешны")
        return True
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта из services: {e}")
        return False

def test_bot_imports():
    """Проверяем импорты из модуля bot"""
    logger.info("=== Тестирование импортов из bot ===")
    try:
        from bot import setup_bot, create_report_page
        logger.info("✅ Импорты из bot успешны")
        return True
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта из bot: {e}")
        return False

if __name__ == "__main__":
    logger.info("Начало тестирования импортов")
    results = {}
    
    results["data_collection"] = test_data_collection_imports()
    results["core"] = test_core_imports()
    results["services"] = test_services_imports()
    results["bot"] = test_bot_imports()
    
    # Выводим результаты
    logger.info("\n=== Результаты тестирования импортов ===")
    for module, success in results.items():
        logger.info(f"{module}: {'✅ УСПЕШНО' if success else '❌ ОШИБКА'}")
    
    # Проверка на общий успех
    all_success = all(results.values())
    logger.info(f"{'✅ ВСЕ ИМПОРТЫ УСПЕШНЫ' if all_success else '❌ ЕСТЬ ПРОБЛЕМЫ С ИМПОРТАМИ'}")
    
    sys.exit(0 if all_success else 1) 