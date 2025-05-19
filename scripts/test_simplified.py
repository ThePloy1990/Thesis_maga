#!/usr/bin/env python3
"""
Упрощенный тестовый скрипт для проверки импортов
"""

import os
import sys
import logging
from pathlib import Path

# Добавляем корневую директорию проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_direct_imports():
    """Тест прямых импортов из всех модулей"""
    logger.info("=== Тестирование прямых импортов ===")
    
    imports = [
        # Сборщики данных
        "from src.data_collection.data_collectors import StockDataCollector",
        
        # Основная бизнес-логика
        "from src.core.portfolio_optimizer import optimize_portfolio",
        
        # Сервисы
        "from src.services.models import User",
        "from src.services.celery_app import celery",
        
        # Бот
        "from src.bot.telegram_bot import setup_bot"
    ]
    
    success = True
    for import_stmt in imports:
        try:
            logger.info(f"Проверка импорта: {import_stmt}")
            exec(import_stmt)
            logger.info("✅ Импорт успешен")
        except ImportError as e:
            logger.error(f"❌ Ошибка импорта: {e}")
            success = False
    
    return success

if __name__ == "__main__":
    logger.info("Начало тестирования импортов")
    
    success = test_direct_imports()
    
    # Выводим результаты
    logger.info("\n=== Результат тестирования ===")
    logger.info(f"Импорты: {'✅ УСПЕШНО' if success else '❌ ОШИБКА'}")
    
    # Если есть ошибки, завершаем с кодом ошибки
    if not success:
        sys.exit(1) 