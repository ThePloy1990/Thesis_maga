import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
from celery import Celery
from telegram import Bot
import logging
import asyncio
from telegram.error import TelegramError
import pandas as pd
from datetime import datetime
import json
from celery.schedules import crontab

if __name__ == "__main__":
    # При запуске как скрипт
    from services.models import SessionLocal, User
else:
    # При импорте как модуль
    from .models import SessionLocal, User

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных из .env файла
load_dotenv()

# Конфигурация брокера и бэкенда
# Для тестирования можно использовать "memory://" (только для разработки)
# или "sqla+sqlite:///celery.db" для SQLite
REDIS_URL = os.getenv('REDIS_URL', 'memory://')
celery = Celery('tasks', broker=REDIS_URL)

# Отключаем бэкенд результатов для упрощения тестирования
celery.conf.update(
    task_ignore_result=True,
)

# Настройка расписания задач
celery.conf.beat_schedule = {
    'collect-stock-data-daily': {
        'task': 'services.celery_app.collect_stock_data_task',
        'schedule': crontab(hour=0, minute=0),  # Каждый день в полночь
        'args': (['^SPY', 'AAPL', 'MSFT', 'GOOGL', 'AMZN'], '1d', '1d'),
    },
    'collect-crypto-data-hourly': {
        'task': 'services.celery_app.collect_crypto_data_task',
        'schedule': crontab(minute=0),  # Каждый час
        'args': (['BTC/USDT', 'ETH/USDT'], '1h'),
    },
    'collect-news-30min': {
        'task': 'services.celery_app.collect_news_task',
        'schedule': crontab(minute='*/30'),  # Каждые 30 минут
        'args': (['business', 'technology'], 'us'),
    },
    'analyze-market-daily': {
        'task': 'services.celery_app.analyze_market_task',
        'schedule': crontab(hour=1, minute=0),  # Каждый день в 1:00
    },
}

# Настройка бота
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = None
if BOT_TOKEN:
    bot = Bot(token=BOT_TOKEN)
else:
    logger.warning("TELEGRAM_BOT_TOKEN не задан. Отправка сообщений не будет работать.")

# Функция для синхронной отправки сообщений через бота
def send_telegram_message(chat_id, message):
    """Синхронная версия отправки сообщения для Telegram бота."""
    # Создаем новый event loop для каждой отправки
    try:
        # Проверка, закрыт ли текущий event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # Если event loop не найден
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Выполняем корутину send_message синхронно
        coroutine = bot.send_message(chat_id=chat_id, text=message)
        result = loop.run_until_complete(coroutine)
        return result
    except TelegramError as e:
        logger.error(f"Ошибка Telegram при отправке сообщения: {e}")
        return None
    except Exception as e:
        logger.error(f"Общая ошибка при отправке сообщения: {e}")
        return None

@celery.task
def send_newsletter_task(message: str):
    """Отправляет сообщение всем зарегистрированным пользователям"""
    if not bot:
        logger.error("Bot не инициализирован. Невозможно отправить сообщения.")
        return
        
    session = SessionLocal()
    try:
        users = session.query(User).all()
        logger.info(f"Найдено {len(users)} пользователей для рассылки")
        
        successful_count = 0
        for user in users:
            if user.telegram_id:
                try:
                    logger.info(f"Отправка сообщения пользователю {user.telegram_id}")
                    result = send_telegram_message(user.telegram_id, message)
                    if result:
                        successful_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при отправке пользователю {user.telegram_id}: {e}")
        
        logger.info(f"Рассылка завершена. Отправлено {successful_count} из {len(users)} сообщений")
    finally:
        session.close()


@celery.task
def collect_stock_data_task(tickers, period="1d", interval="1d"):
    """Задача для сбора данных о ценах акций"""
    from data_collection import StockDataCollector
    
    logger.info(f"Запуск сбора данных о ценах акций: {tickers}")
    collector = StockDataCollector()
    try:
        data = collector.get_historical_data(
            tickers=tickers,
            period=period,
            interval=interval,
            force_refresh=True
        )
        logger.info(f"Данные акций успешно получены: {data.shape}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сборе данных акций: {e}")
        return False


@celery.task
def collect_crypto_data_task(symbols, timeframe="1d"):
    """Задача для сбора данных о криптовалютах"""
    from data_collection import CryptoDataCollector
    
    logger.info(f"Запуск сбора данных о криптовалютах: {symbols}")
    collector = CryptoDataCollector()
    results = {}
    
    for symbol in symbols:
        try:
            data = collector.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                force_refresh=True
            )
            results[symbol] = (True, data.shape if not data.empty else "Пустой DataFrame")
            logger.info(f"Данные для {symbol} успешно получены")
        except Exception as e:
            results[symbol] = (False, str(e))
            logger.error(f"Ошибка при получении данных для {symbol}: {e}")
    
    return results


@celery.task
def collect_news_task(categories, country="us"):
    """Задача для сбора новостей по категориям"""
    from data_collection import NewsCollector
    
    logger.info(f"Запуск сбора новостей по категориям: {categories}")
    collector = NewsCollector()
    results = {}
    
    for category in categories:
        try:
            news = collector.get_market_news(
                category=category,
                country=country,
                force_refresh=True
            )
            results[category] = (True, len(news))
            logger.info(f"Получено {len(news)} новостей категории {category}")
        except Exception as e:
            results[category] = (False, str(e))
            logger.error(f"Ошибка при получении новостей категории {category}: {e}")
    
    return results


@celery.task
def analyze_sentiment_task(category="business", country="us"):
    """Задача для анализа сентимента новостей"""
    from data_collection import NewsCollector, SentimentAnalyzer
    
    logger.info(f"Запуск анализа сентимента новостей категории {category}")
    news_collector = NewsCollector()
    sentiment_analyzer = SentimentAnalyzer()
    
    try:
        # Получаем новости
        news = news_collector.get_market_news(
            category=category,
            country=country
        )
        
        if not news:
            logger.warning(f"Новости категории {category} не найдены")
            return False
        
        # Анализируем сентимент
        enriched_news = sentiment_analyzer.analyze_news(news)
        
        # Сохраняем результаты с временной меткой
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"data/sentiment_{category}_{country}_{timestamp}.json"
        os.makedirs("data", exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(enriched_news, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Результаты анализа сентимента сохранены в {output_file}")
        return True
    
    except Exception as e:
        logger.error(f"Ошибка при анализе сентимента: {e}")
        return False


@celery.task
def analyze_market_task():
    """Задача для создания снимка состояния рынка"""
    logger.info("Запуск создания снимка рынка")
    
    # Запускаем сбор данных и анализ параллельно
    collect_stock_data_task.delay(["SPY", "QQQ", "DIA"], "1mo", "1d")
    collect_crypto_data_task.delay(["BTC/USDT", "ETH/USDT"], "1d")
    collect_news_task.delay(["business", "economy"], "us")
    analyze_sentiment_task.delay("business", "us")
    
    # Формируем базовый снимок рынка (основные индексы)
    try:
        from data_collection import StockDataCollector
        collector = StockDataCollector()
        
        # Получаем текущие цены основных индексов
        indices = ["^SPX", "^NDX", "^DJI", "^VIX"]
        prices = collector.get_latest_prices(indices)
        
        # Сохраняем снимок
        timestamp = datetime.now().strftime("%Y%m%d")
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "indices": prices,
            "status": "completed"
        }
        
        snapshot_file = f"data/market_snapshot_{timestamp}.json"
        with open(snapshot_file, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Снимок рынка сохранен в {snapshot_file}")
        
        # Отправляем сообщение админу
        admin_id = os.getenv("ADMIN_TELEGRAM_ID")
        if admin_id and bot:
            message = f"🔄 Ежедневный снимок рынка создан\n📊 S&P 500: {prices.get('^SPX', 'N/A')}\n📈 VIX: {prices.get('^VIX', 'N/A')}"
            send_telegram_message(admin_id, message)
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при создании снимка рынка: {e}")
        return False 