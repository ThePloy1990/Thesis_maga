"""
Пакет для сбора и обработки данных:
- Ценовые данные (акции, криптовалюты)
- Новости
- Анализ сентимента
"""

from data_collection.data_collectors import (
    StockDataCollector,
    CryptoDataCollector,
    NewsCollector,
    SentimentAnalyzer
)

__all__ = [
    'StockDataCollector',
    'CryptoDataCollector',
    'NewsCollector',
    'SentimentAnalyzer'
] 