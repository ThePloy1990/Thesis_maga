"""
Модуль для сбора данных из различных источников:
- Ценовые данные с Yahoo Finance (акции)
- Ценовые данные с биржи криптовалют (CCXT)
- Новости из NewsAPI
- Обработка сентимента с FinBERT
"""

import os
import logging
import pandas as pd
import numpy as np
import yfinance as yf
from typing import List, Dict, Optional, Union, Tuple
from datetime import datetime, timedelta
import json
import requests
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Получение API ключей из переменных окружения
NEWS_API_KEY = os.getenv("NEWS_API_KEY")


class StockDataCollector:
    """Класс для сбора данных о ценах акций с Yahoo Finance"""
    
    def __init__(self, cache_dir: str = "data"):
        """
        Инициализация коллектора данных для акций
        
        Args:
            cache_dir: Директория для кеширования данных
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
    def get_historical_data(self, 
                          tickers: List[str], 
                          period: str = "1y", 
                          interval: str = "1d",
                          force_refresh: bool = False) -> pd.DataFrame:
        """
        Получение исторических данных для списка тикеров
        
        Args:
            tickers: Список тикеров
            period: Период данных ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'max')
            interval: Интервал ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')
            force_refresh: Принудительное обновление данных
            
        Returns:
            DataFrame с историческими данными
        """
        # Формирование имени файла для кеширования
        timestamp = datetime.now().strftime("%Y%m%d")
        cache_file = os.path.join(
            self.cache_dir, 
            f"stock_data_{'-'.join(tickers)}_{period}_{interval}_{timestamp}.csv"
        )
        
        # Проверка наличия кешированных данных
        if os.path.exists(cache_file) and not force_refresh:
            logger.info(f"Загружаю данные из кеша: {cache_file}")
            return pd.read_csv(cache_file, index_col=0, parse_dates=True)
        
        # Загрузка данных через yfinance
        logger.info(f"Получаю исторические данные для {len(tickers)} тикеров...")
        data = yf.download(
            tickers=tickers, 
            period=period, 
            interval=interval, 
            group_by='ticker', 
            auto_adjust=True,
            threads=True
        )
        
        # Реорганизация данных, если получен один тикер
        if len(tickers) == 1:
            ticker = tickers[0]
            data.columns = pd.MultiIndex.from_product([[ticker], data.columns])
        
        # Сохранение данных в кеш
        data.to_csv(cache_file)
        logger.info(f"Данные сохранены в {cache_file}")
        
        return data
    
    def get_technical_indicators(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """
        Расчет технических индикаторов для данных о ценах
        
        Args:
            price_data: DataFrame с данными о ценах
            
        Returns:
            DataFrame с техническими индикаторами
        """
        # TODO: Реализовать расчет технических индикаторов (SMA, RSI, MACD, etc.)
        return price_data
    
    def get_latest_prices(self, tickers: List[str]) -> Dict[str, float]:
        """
        Получение текущих цен для списка тикеров
        
        Args:
            tickers: Список тикеров
            
        Returns:
            Словарь с текущими ценами
        """
        prices = {}
        for ticker in tickers:
            try:
                data = yf.Ticker(ticker)
                prices[ticker] = data.info.get("regularMarketPrice")
                logger.debug(f"Получена цена для {ticker}: {prices[ticker]}")
            except Exception as e:
                logger.error(f"Ошибка при получении цены для {ticker}: {e}")
                prices[ticker] = None
        
        return prices


class CryptoDataCollector:
    """Класс для сбора данных о криптовалютах через CCXT"""
    
    def __init__(self, exchange: str = "binance", cache_dir: str = "data"):
        """
        Инициализация коллектора данных для криптовалют
        
        Args:
            exchange: Название биржи для получения данных
            cache_dir: Директория для кеширования данных
        """
        self.cache_dir = cache_dir
        self.exchange_name = exchange
        os.makedirs(cache_dir, exist_ok=True)
        
        # Загрузка CCXT только при необходимости
        try:
            import ccxt
            self.ccxt = ccxt
            self.exchange = getattr(ccxt, exchange)()
            logger.info(f"Успешное подключение к бирже {exchange}")
        except ImportError:
            logger.warning("Библиотека CCXT не установлена, установите её с помощью pip install ccxt")
            self.ccxt = None
            self.exchange = None
        except Exception as e:
            logger.error(f"Ошибка при инициализации биржи {exchange}: {e}")
            self.exchange = None
    
    def get_historical_data(self, 
                          symbol: str, 
                          timeframe: str = "1d",
                          limit: int = 365,
                          force_refresh: bool = False) -> pd.DataFrame:
        """
        Получение исторических данных для криптовалюты
        
        Args:
            symbol: Символ криптовалютной пары (например, 'BTC/USDT')
            timeframe: Интервал данных ('1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w')
            limit: Количество исторических баров
            force_refresh: Принудительное обновление данных
            
        Returns:
            DataFrame с историческими данными
        """
        if self.exchange is None:
            logger.error("Биржа не инициализирована")
            return pd.DataFrame()
        
        # Формирование имени файла для кеширования
        timestamp = datetime.now().strftime("%Y%m%d")
        cache_file = os.path.join(
            self.cache_dir, 
            f"crypto_{self.exchange_name}_{symbol.replace('/', '_')}_{timeframe}_{timestamp}.csv"
        )
        
        # Проверка наличия кешированных данных
        if os.path.exists(cache_file) and not force_refresh:
            logger.info(f"Загружаю данные из кеша: {cache_file}")
            return pd.read_csv(cache_file, index_col=0, parse_dates=True)
        
        try:
            # Получение данных через CCXT
            logger.info(f"Получаю исторические данные для {symbol} с {self.exchange_name}...")
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            # Преобразование данных в DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Сохранение данных в кеш
            df.to_csv(cache_file)
            logger.info(f"Данные сохранены в {cache_file}")
            
            return df
        
        except Exception as e:
            logger.error(f"Ошибка при получении данных для {symbol}: {e}")
            return pd.DataFrame()


class NewsCollector:
    """Класс для сбора новостей через NewsAPI"""
    
    def __init__(self, api_key: Optional[str] = None, cache_dir: str = "data"):
        """
        Инициализация коллектора новостей
        
        Args:
            api_key: API ключ для NewsAPI
            cache_dir: Директория для кеширования данных
        """
        self.api_key = api_key or NEWS_API_KEY
        if not self.api_key:
            logger.warning("API ключ NewsAPI не найден. Установите переменную окружения NEWS_API_KEY или передайте ключ при инициализации.")
        
        self.cache_dir = cache_dir
        self.news_dir = os.path.join(cache_dir, "news")
        os.makedirs(self.news_dir, exist_ok=True)
        
        self.base_url = "https://newsapi.org/v2/"
    
    def get_company_news(self, 
                       company: str, 
                       days: int = 1,
                       language: str = "en",
                       force_refresh: bool = False) -> List[Dict]:
        """
        Получение новостей о компании за указанный период
        
        Args:
            company: Название компании
            days: Количество дней для поиска
            language: Язык новостей ('en', 'ru', etc.)
            force_refresh: Принудительное обновление данных
            
        Returns:
            Список новостей
        """
        if not self.api_key:
            logger.error("API ключ NewsAPI не установлен")
            return []
        
        # Формирование имени файла для кеширования
        date_str = datetime.now().strftime("%Y%m%d")
        cache_file = os.path.join(
            self.news_dir, 
            f"news_{company}_{days}d_{language}_{date_str}.json"
        )
        
        # Проверка наличия кешированных данных
        if os.path.exists(cache_file) and not force_refresh:
            logger.info(f"Загружаю новости из кеша: {cache_file}")
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Формирование запроса к NewsAPI
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        params = {
            'q': company,
            'from': from_date,
            'language': language,
            'sortBy': 'publishedAt',
            'apiKey': self.api_key
        }
        
        try:
            # Отправка запроса к NewsAPI
            logger.info(f"Получаю новости о {company} за последние {days} дней...")
            response = requests.get(f"{self.base_url}everything", params=params)
            response.raise_for_status()
            
            data = response.json()
            articles = data.get('articles', [])
            
            # Сохранение данных в кеш
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(articles, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Получено {len(articles)} новостей о {company}")
            return articles
            
        except Exception as e:
            logger.error(f"Ошибка при получении новостей о {company}: {e}")
            return []

    def get_market_news(self,
                      category: str = "business",
                      country: str = "us",
                      force_refresh: bool = False) -> List[Dict]:
        """
        Получение новостей о рынке по категории
        
        Args:
            category: Категория новостей ('business', 'technology', etc.)
            country: Код страны ('us', 'gb', etc.)
            force_refresh: Принудительное обновление данных
            
        Returns:
            Список новостей
        """
        if not self.api_key:
            logger.error("API ключ NewsAPI не установлен")
            return []
        
        # Формирование имени файла для кеширования
        date_str = datetime.now().strftime("%Y%m%d")
        cache_file = os.path.join(
            self.news_dir, 
            f"market_news_{category}_{country}_{date_str}.json"
        )
        
        # Проверка наличия кешированных данных
        if os.path.exists(cache_file) and not force_refresh:
            logger.info(f"Загружаю новости из кеша: {cache_file}")
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Формирование запроса к NewsAPI
        params = {
            'category': category,
            'country': country,
            'apiKey': self.api_key
        }
        
        try:
            # Отправка запроса к NewsAPI
            logger.info(f"Получаю новости категории {category} для страны {country}...")
            response = requests.get(f"{self.base_url}top-headlines", params=params)
            response.raise_for_status()
            
            data = response.json()
            articles = data.get('articles', [])
            
            # Сохранение данных в кеш
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(articles, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Получено {len(articles)} новостей категории {category}")
            return articles
            
        except Exception as e:
            logger.error(f"Ошибка при получении новостей категории {category}: {e}")
            return []


class SentimentAnalyzer:
    """Класс для анализа сентимента текстов с использованием FinBERT"""
    
    def __init__(self, use_mock_data=False):
        """Инициализация анализатора сентимента"""
        self.model = None
        self.tokenizer = None
        self.use_mock_data = use_mock_data
        self.labels = ["positive", "negative", "neutral"]
        if not self.use_mock_data:
            self.load_model()
        
    def load_model(self):
        """Загрузка модели FinBERT для анализа сентимента"""
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            import torch
            
            model_name = "ProsusAI/finbert"
            logger.info(f"Загрузка модели {model_name}...")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.model.eval()  # Переключаем модель в режим оценки
            logger.info("Модель успешно загружена")
            
        except ImportError:
            logger.error("Библиотека transformers не установлена. Установите её с помощью pip install transformers")
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке модели: {e}")
    
    def analyze_text(self, text: str) -> Dict[str, float]:
        """
        Анализ сентимента текста
        
        Args:
            text: Текст для анализа
            
        Returns:
            Словарь с вероятностями классов сентимента
        """
        if self.use_mock_data:
            # В тестовом режиме возвращаем простую имитацию анализа
            if any(word in text.lower() for word in ["рекордной", "рост", "выросли", "прибыль", "успешно"]):
                return {"positive": 0.8, "negative": 0.1, "neutral": 0.1}
            elif any(word in text.lower() for word in ["упали", "снизились", "убыток", "потери", "провал"]):
                return {"positive": 0.1, "negative": 0.8, "neutral": 0.1}
            else:
                return {"positive": 0.2, "negative": 0.2, "neutral": 0.6}
        
        if not self.model or not self.tokenizer:
            logger.error("Модель не загружена")
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0}
        
        try:
            import torch
            
            # Подготовка текста к обработке
            inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512, padding=True)
            
            # Получение прогноза
            with torch.no_grad():
                outputs = self.model(**inputs)
                probabilities = torch.nn.functional.softmax(outputs.logits, dim=1)
            
            # Интерпретация результатов
            result = {}
            for i, label in enumerate(self.labels):
                result[label] = probabilities[0, i].item()
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при анализе текста: {e}")
            return {"positive": 0.0, "negative": 0.0, "neutral": 1.0}
    
    def analyze_news(self, news: List[Dict]) -> List[Dict]:
        """
        Анализ сентимента новостей
        
        Args:
            news: Список новостей
            
        Returns:
            Список новостей с добавленным сентиментом
        """
        if not self.model and not self.use_mock_data:
            logger.warning("Модель не загружена, пропускаем анализ сентимента")
            return news
        
        enriched_news = []
        
        for article in news:
            try:
                # Объединяем заголовок и описание для анализа
                text = f"{article.get('title', '')} {article.get('description', '')}"
                sentiment = self.analyze_text(text)
                
                # Добавляем сентимент к статье
                article_with_sentiment = article.copy()
                article_with_sentiment['sentiment'] = sentiment
                
                # Добавляем общую оценку
                max_sentiment = max(sentiment, key=sentiment.get)
                article_with_sentiment['sentiment_label'] = max_sentiment
                article_with_sentiment['sentiment_score'] = sentiment[max_sentiment]
                
                enriched_news.append(article_with_sentiment)
                
            except Exception as e:
                logger.error(f"Ошибка при анализе новости: {e}")
                enriched_news.append(article)
        
        return enriched_news


# Пример использования
if __name__ == "__main__":
    # Получение данных о ценах акций
    stock_collector = StockDataCollector()
    data = stock_collector.get_historical_data(["AAPL", "MSFT", "GOOGL"], period="1mo")
    print(data.head())
    
    # Попытка получения данных о криптовалютах
    try:
        crypto_collector = CryptoDataCollector()
        btc_data = crypto_collector.get_historical_data("BTC/USDT", timeframe="1d", limit=30)
        print(btc_data.head())
    except Exception as e:
        print(f"Ошибка при работе с криптовалютами: {e}")
    
    # Получение новостей
    news_collector = NewsCollector()
    apple_news = news_collector.get_company_news("Apple", days=3)
    print(f"Получено {len(apple_news)} новостей о Apple") 