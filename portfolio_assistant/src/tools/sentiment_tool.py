import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import json
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from newsapi import NewsApiClient
import redis

logger = logging.getLogger(__name__)

# --- Конфигурация --- #
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
if not NEWSAPI_KEY:
    logger.warning("NEWSAPI_KEY environment variable not set. Sentiment tool will not fetch live news.")

MODEL_NAME = "ProsusAI/finbert"
CACHE_TTL_SECONDS = 900  # 15 минут
REDIS_HOST = 'localhost'
REDIS_PORT = 6379
REDIS_DB = 0 # Используйте другую БД, если основная занята

# --- Инициализация --- #
_tokenizer = None
_model = None
_redis_client = None
_newsapi_client = None

def _get_tokenizer_model():
    global _tokenizer, _model
    if _tokenizer is None or _model is None:
        logger.info(f"Loading tokenizer and model for {MODEL_NAME}...")
        try:
            _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
            _model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
            logger.info(f"Tokenizer and model {MODEL_NAME} loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading HuggingFace model {MODEL_NAME}: {e}", exc_info=True)
            # Не поднимаем исключение, чтобы инструмент мог вернуть ошибку штатно
    return _tokenizer, _model

def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
            _redis_client.ping() # Проверка соединения
            logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Redis connection failed for sentiment_tool: {e}. Caching will be disabled.")
            _redis_client = None # Отключаем кэширование при ошибке
    return _redis_client

def _get_newsapi_client():
    global _newsapi_client
    if NEWSAPI_KEY and _newsapi_client is None:
        _newsapi_client = NewsApiClient(api_key=NEWSAPI_KEY)
    return _newsapi_client

def _fetch_news_from_api(ticker: str, window_days: int) -> List[Dict[str, Any]]:
    client = _get_newsapi_client()
    if not client:
        logger.warning("NewsAPI client not initialized (likely missing API key). Returning no news.")
        return []

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=window_days)

    try:
        logger.info(f"Fetching news for '{ticker}' from {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}")
        # Используем тикер как основной поисковый запрос. Можно добавить название компании, если оно известно.
        # NewsAPI предпочитает более общие запросы для лучших результатов.
        # q = f'{ticker} OR "{company_name_map.get(ticker, ticker)}"' # Пример с картой компаний
        q = ticker 
        articles_response = client.get_everything(
            q=q,
            from_param=from_date.strftime('%Y-%m-%d'),
            to=to_date.strftime('%Y-%m-%d'),
            language='en',
            sort_by='relevancy', # или 'publishedAt' или 'popularity'
            page_size=20 # Ограничим количество статей для скорости
        )
        if articles_response['status'] == 'ok':
            logger.info(f"Fetched {len(articles_response['articles'])} articles for '{ticker}'.")
            return articles_response['articles']
        else:
            logger.error(f"NewsAPI error for '{ticker}': {articles_response.get('message')}")
            return []
    except Exception as e:
        logger.error(f"Exception fetching news for '{ticker}': {e}", exc_info=True)
        return []

def _calculate_sentiment_score(headlines: List[str]) -> float:
    if not headlines:
        return 0.0

    tokenizer, model = _get_tokenizer_model()
    if tokenizer is None or model is None: # <--- ВОТ ОНА!
        logger.error("Sentiment model not available. Cannot calculate score.")
        return 0.0

    sentiment_scores = []
    try:
        with torch.no_grad(): # Отключаем расчет градиентов для инференса
            for headline in headlines:
                if not headline or not isinstance(headline, str):
                    continue
                inputs = tokenizer(headline, return_tensors="pt", truncation=True, max_length=512, padding=True)
                outputs = model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
                # probs[0] это [positive_prob, negative_prob, neutral_prob]
                positive_prob = probs[0][0].item() # Индекс 0 для positive в ProsusAI/finbert
                negative_prob = probs[0][1].item() # Индекс 1 для negative
                # neutral_prob = probs[0][2].item()
                sentiment_scores.append(positive_prob - negative_prob)
    except Exception as e:
        logger.error(f"Error during sentiment calculation with FinBERT: {e}", exc_info=True)
        return 0.0 # Возвращаем нейтральный в случае ошибки модели

    if not sentiment_scores:
        return 0.0
    return sum(sentiment_scores) / len(sentiment_scores)


def sentiment_tool(ticker: str, window_days: int = 3) -> Dict[str, Any]:
    """
    Calculates the sentiment score for a given ticker based on recent news headlines.

    The score is derived from news fetched via NewsAPI over the specified window_days,
    analyzed by the ProsusAI/finbert model. Results are cached in Redis.

    Args:
        ticker: The stock ticker symbol (e.g., "AAPL").
        window_days: The number of past days to fetch news for (default is 3).

    Returns:
        A dictionary with sentiment score and metadata.
        Example: {"score": 0.75, "articles_count": 10, "error": None}
    """
    # Проверяем существование модели для данного тикера
    models_path = Path(__file__).absolute().parent.parent.parent.parent / "models"
    model_path = models_path / f"catboost_{ticker}.cbm"
    if not model_path.exists():
        logger.warning(f"Модель для тикера {ticker} не найдена в {models_path}")
        return {
            "score": 0.0,
            "articles_count": 0,
            "error": f"Тикер {ticker} недоступен: модель не найдена"
        }

    if not NEWSAPI_KEY:
        logger.warning("NEWSAPI_KEY is not set. Sentiment tool cannot fetch news.")
        # Можно вернуть ошибку или нейтральное значение
        return {
            "score": 0.0,
            "articles_count": 0,
            "error": "API ключ для новостей не настроен. Анализ настроений недоступен."
        }

    # Инициализация клиентов (ленивая)
    _get_tokenizer_model() # Загружаем модель заранее, если еще не загружена
    redis_cli = _get_redis_client()
    
    cache_key = f"sentiment:{ticker}:{window_days}" # Добавляем window_days в ключ кэша

    if redis_cli:
        try:
            cached_result = redis_cli.get(cache_key)
            if cached_result is not None:
                logger.info(f"Returning cached sentiment for '{ticker}' (window: {window_days} days)")
                try:
                    result = json.loads(cached_result)
                    return result
                except json.JSONDecodeError:
                    # Если в кэше не словарь, а просто число (обратная совместимость)
                    return {
                        "score": float(cached_result),
                        "articles_count": 0,
                        "error": None
                    }
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis GET error for key {cache_key}: {e}. Proceeding without cache.")
            # Не перевыбрасываем, чтобы продолжить без кэша

    logger.info(f"Calculating sentiment for '{ticker}' (window: {window_days} days), no cache or cache expired.")
    news_articles = _fetch_news_from_api(ticker, window_days)
    
    headlines = []
    for article in news_articles:
        title = article.get('title')
        if title: # Убедимся, что заголовок есть
            headlines.append(title)
    
    if not headlines:
        logger.info(f"No relevant headlines found for '{ticker}' in the last {window_days} days.")
        final_result = {
            "score": 0.0,
            "articles_count": 0,
            "error": f"Не найдены новости для тикера {ticker} за последние {window_days} дней."
        }
    else:
        final_score = _calculate_sentiment_score(headlines)
        final_result = {
            "score": final_score,
            "articles_count": len(headlines),
            "error": None
        }

    if redis_cli:
        try:
            redis_cli.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(final_result))
            logger.info(f"Cached sentiment for '{ticker}' (window: {window_days} days)")
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis SETEX error for key {cache_key}: {e}.")
            # Не перевыбрасываем, ошибка кэширования не должна ломать основную логику

    return final_result

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    if not NEWSAPI_KEY:
        print("Please set the NEWSAPI_KEY environment variable to run this example.")
        print("E.g., export NEWSAPI_KEY='your_actual_api_key'")
    else:
        # --- Пример использования --- # 
        # Убедитесь, что Redis запущен
        print("--- Example: Sentiment for Apple (AAPL) ---")
        aapl_sentiment = sentiment_tool(ticker="AAPL", window_days=3)
        print(f"Sentiment score for AAPL (3 days): {aapl_sentiment}")

        print("\n--- Example: Sentiment for Microsoft (MSFT) --- (should use cache on 2nd run if soon enough)")
        msft_sentiment_1 = sentiment_tool(ticker="MSFT", window_days=2)
        print(f"Sentiment score for MSFT (2 days, 1st call): {msft_sentiment_1}")
        msft_sentiment_2 = sentiment_tool(ticker="MSFT", window_days=2) # Повторный вызов
        print(f"Sentiment score for MSFT (2 days, 2nd call): {msft_sentiment_2}")

        print("\n--- Example: Sentiment for a less common ticker (might have fewer news) --- ")
        # Используйте тикер, по которому может быть мало новостей
        other_sentiment = sentiment_tool(ticker="RDSA.AS", window_days=5) # Shell PLC (Amsterdam)
        print(f"Sentiment score for RDSA.AS (5 days): {other_sentiment}")

        # Пример с отсутствующим ключом API (если закомментировать NEWSAPI_KEY или он не установлен)
        # print("\n--- Example: No API Key (simulated) ---")
        # original_key = NEWSAPI_KEY
        # NEWSAPI_KEY = None # Временно отключаем
        # _newsapi_client = None # Сбрасываем клиент
        # no_key_sentiment = sentiment_tool(ticker="GOOG")
        # print(f"Sentiment with no API key for GOOG: {no_key_sentiment}")
        # NEWSAPI_KEY = original_key # Восстанавливаем
        # _newsapi_client = None # Сбрасываем клиент 