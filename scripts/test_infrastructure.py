#!/usr/bin/env python3
"""
Тестовый скрипт для проверки инфраструктуры проекта:
- Импорты из всех пакетов
- Доступ к основным компонентам системы
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

def test_imports():
    """Тест импортов из всех пакетов"""
    logger.info("=== Тестирование импортов ===")
    
    imports = [
        # Сборщики данных
        "from src.data_collection import StockDataCollector, CryptoDataCollector, NewsCollector, SentimentAnalyzer",
        
        # Основная бизнес-логика - импортируем напрямую из модулей
        "from src.core.portfolio_optimizer import optimize_portfolio, compute_correlation_matrix",
        "from src.core.visualization import create_performance_chart, create_allocation_pie",
        "from src.core.llm_agents import forecast_tool",
        
        # Сервисы
        "from src.services import User, SessionLocal, Base",
        "from src.services.celery_app import celery, collect_stock_data_task",
    ]
    
    for import_stmt in imports:
        try:
            logger.info(f"Проверка импорта: {import_stmt}")
            exec(import_stmt)
            logger.info("✅ Импорт успешен")
        except ImportError as e:
            logger.error(f"❌ Ошибка импорта: {e}")
            return False
    
    return True

def test_components():
    """Тест основных компонентов системы"""
    logger.info("=== Тестирование компонентов ===")
    
    try:
        # Импорт и проверка компонентов
        from src.data_collection import StockDataCollector
        from src.core.portfolio_optimizer import optimize_portfolio
        from src.services.models import User
        
        # Создаем экземпляр сборщика данных
        stock_collector = StockDataCollector()
        logger.info("✅ StockDataCollector успешно создан")
        
        # Проверяем, что функция оптимизации портфеля существует
        assert callable(optimize_portfolio)
        logger.info("✅ optimize_portfolio является вызываемой функцией")
        
        # Проверяем, что класс User определен правильно
        assert hasattr(User, '__tablename__')
        logger.info("✅ Класс User имеет атрибут __tablename__")
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании компонентов: {e}")
        return False

if __name__ == "__main__":
    logger.info("Начало тестирования инфраструктуры проекта")
    
    results = {
        "imports": test_imports(),
        "components": test_components()
    }
    
    # Выводим результаты
    logger.info("\n=== Результаты тестирования ===")
    for component, success in results.items():
        logger.info(f"{component}: {'✅ УСПЕШНО' if success else '❌ ОШИБКА'}")
    
    # Если есть ошибки, завершаем с кодом ошибки
    if not all(results.values()):
        sys.exit(1) 