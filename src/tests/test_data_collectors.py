#!/usr/bin/env python3
"""
Тестовый скрипт для проверки компонентов сбора данных:
- StockDataCollector - сбор данных о ценах акций через yfinance
- CryptoDataCollector - сбор данных о криптовалютах через ccxt
- NewsCollector - сбор новостей через NewsAPI
- SentimentAnalyzer - анализ сентимента через FinBERT
"""

import os
import sys
import logging
import json
from pathlib import Path
from datetime import datetime

# Добавляем корневую директорию проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Правильный импорт из модуля, когда запускаем из папки src
from data_collection import (
    StockDataCollector, 
    CryptoDataCollector, 
    NewsCollector, 
    SentimentAnalyzer
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка .env
from dotenv import load_dotenv
load_dotenv()

# Флаги для определения, какие тесты запускать
USE_MOCK_DATA = False  # Использовать настоящие данные вместо заглушек
RUN_STOCK_TEST = True
RUN_CRYPTO_TEST = True
RUN_NEWS_TEST = True
RUN_SENTIMENT_TEST = True


def test_stock_collector():
    """Тест сбора данных о ценах акций"""
    logger.info("=== Тестирование StockDataCollector ===")
    
    collector = StockDataCollector()
    tickers = ["AAPL", "MSFT", "GOOGL"]
    
    try:
        # Получение исторических данных
        logger.info(f"Получение исторических данных для {tickers}")
        data = collector.get_historical_data(tickers, period="1mo", interval="1d")
        logger.info(f"Получено {data.shape[0]} строк и {data.shape[1]} столбцов")
        
        # Получение текущих цен
        logger.info("Получение текущих цен")
        prices = collector.get_latest_prices(tickers)
        for ticker, price in prices.items():
            logger.info(f"{ticker}: {price}")
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при тестировании StockDataCollector: {e}")
        return False


def test_crypto_collector():
    """Тест сбора данных о криптовалютах"""
    logger.info("=== Тестирование CryptoDataCollector ===")
    
    try:
        collector = CryptoDataCollector()
        symbol = "BTC/USDT"
        
        # Проверка доступности CCXT
        if collector.exchange is None:
            logger.warning("CCXT не установлен или не удалось инициализировать биржу")
            return False
        
        # Получение исторических данных
        logger.info(f"Получение исторических данных для {symbol}")
        data = collector.get_historical_data(symbol, timeframe="1d", limit=30)
        
        if data.empty:
            logger.warning(f"Не удалось получить данные для {symbol}")
            return False
        
        logger.info(f"Получено {data.shape[0]} строк и {data.shape[1]} столбцов")
        return True
    except Exception as e:
        logger.error(f"Ошибка при тестировании CryptoDataCollector: {e}")
        return False


def test_news_collector():
    """Тест сбора новостей"""
    logger.info("=== Тестирование NewsCollector ===")
    
    try:
        collector = NewsCollector()
        
        # Проверка доступности API ключа
        if not collector.api_key or collector.api_key == "ВАШ_КЛЮЧ_API_NEWSAPI":
            logger.warning("API ключ NewsAPI не найден или не валидный")
            return False
        
        # Получение новостей о компании
        company = "Apple"
        logger.info(f"Получение новостей о {company}")
        company_news = collector.get_company_news(company, days=3)
        logger.info(f"Получено {len(company_news)} новостей о {company}")
        
        # Получение новостей по категории
        category = "business"
        logger.info(f"Получение новостей категории {category}")
        category_news = collector.get_market_news(category=category)
        logger.info(f"Получено {len(category_news)} новостей категории {category}")
        
        # Сохранение примера новостей
        if category_news:
            example_file = os.path.join("data", "news_example.json")
            os.makedirs("data", exist_ok=True)
            with open(example_file, "w", encoding="utf-8") as f:
                json.dump(category_news[:3], f, ensure_ascii=False, indent=2)
            logger.info(f"Пример новостей сохранен в {example_file}")
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при тестировании NewsCollector: {e}")
        return False


def test_sentiment_analyzer():
    """Тест анализа сентимента"""
    logger.info("=== Тестирование SentimentAnalyzer ===")
    
    try:
        # Создаем анализатор без заглушки
        analyzer = SentimentAnalyzer(use_mock_data=USE_MOCK_DATA)
        
        # Проверим, загрузилась ли модель
        if not analyzer.model:
            logger.warning("Модель FinBERT не загружена")
            return False
        
        # Тестовые тексты для анализа
        test_texts = [
            "Компания Apple объявила о рекордной квартальной выручке",
            "Акции Tesla упали на 10% после публикации квартального отчета",
            "Рынок находится в состоянии неопределенности в ожидании решения ФРС"
        ]
        
        # Анализ сентимента текстов
        logger.info("Анализ сентимента тестовых текстов")
        for text in test_texts:
            sentiment = analyzer.analyze_text(text)
            logger.info(f'Текст: "{text[:50]}..."')
            logger.info(f"Сентимент: {sentiment}")
        
        # Тест анализа новостей
        logger.info("Тест анализа сентимента новостей")
        
        # Создаем тестовые данные новостей
        test_news = [
            {
                "title": "Компания Apple представила новый iPhone",
                "description": "На презентации были показаны новые модели смартфонов"
            },
            {
                "title": "Акции Tesla выросли на 5% после отчета",
                "description": "Компания отчиталась о рекордной квартальной прибыли"
            }
        ]
        
        # Анализируем их
        enriched_news = analyzer.analyze_news(test_news)
        logger.info(f"Проанализировано {len(enriched_news)} новостей")
        
        # Сохраняем результаты
        example_file = os.path.join("data", "sentiment_example.json")
        with open(example_file, "w", encoding="utf-8") as f:
            json.dump(enriched_news, f, ensure_ascii=False, indent=2)
        logger.info(f"Пример анализа сентимента сохранен в {example_file}")
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при тестировании SentimentAnalyzer: {e}")
        return False


if __name__ == "__main__":
    logger.info("Начало тестирования компонентов сбора данных")
    
    # Создаем директорию для данных, если она не существует
    os.makedirs("data", exist_ok=True)
    
    results = {}
    
    if RUN_STOCK_TEST:
        results["stock_collector"] = test_stock_collector()
        
    if RUN_CRYPTO_TEST:
        results["crypto_collector"] = test_crypto_collector()
        
    if RUN_NEWS_TEST:
        results["news_collector"] = test_news_collector()
        
    if RUN_SENTIMENT_TEST:
        results["sentiment_analyzer"] = test_sentiment_analyzer()
    
    # Выводим результаты
    logger.info("\n=== Результаты тестирования ===")
    for component, success in results.items():
        logger.info(f"{component}: {'✅ УСПЕШНО' if success else '❌ ОШИБКА'}")
    
    # Сохраняем результаты
    results_file = os.path.join("data", f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "mock_data_used": USE_MOCK_DATA
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Результаты сохранены в {results_file}") 