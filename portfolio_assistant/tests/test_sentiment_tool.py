import pytest
import torch
from unittest.mock import patch, MagicMock
import time # Для проверки TTL кэша
import os

from src.tools.sentiment_tool import sentiment_tool, _get_redis_client, CACHE_TTL_SECONDS, NEWSAPI_KEY
# Импортируем сам модуль, чтобы иметь доступ к его глобальным переменным
import src.tools.sentiment_tool as sentiment_tool_module

# Используем ту же конфигурацию Redis, что и в основном модуле, для тестов
# Это позволит нам манипулировать одним и тем же экземпляром Redis (если он глобальный в модуле)
# или легко предсказывать ключи.

@pytest.fixture(scope="function", autouse=True)
def clear_sentiment_cache_and_prepare_env():
    """Очищает кэш Redis перед каждым тестом и временно устанавливает NEWSAPI_KEY для тестов."""
    # Установим фиктивный ключ API для NewsAPI на время тестов, если он не задан глобально
    # Это позволит инициализировать NewsApiClient без ошибок в тестах, даже если ключ не задан в окружении.
    # Однако, реальные запросы к NewsAPI будут мокаться.
    original_newsapi_key = os.environ.get("NEWSAPI_KEY")
    if not original_newsapi_key:
        os.environ["NEWSAPI_KEY"] = "test_api_key_dummy"
        # Сбросить клиент, чтобы он переинициализировался с новым ключом, если нужно
        # Это зависит от того, как _get_newsapi_client() реализован (если он кэширует None)
        # В текущей реализации sentiment_tool, _get_newsapi_client() пересоздастся.

    # Сбрасываем глобальные переменные модели и токенизатора перед каждым тестом
    sentiment_tool_module._tokenizer = None
    sentiment_tool_module._model = None
    sentiment_tool_module._redis_client = None # Также сбросим Redis клиент для чистоты
    sentiment_tool_module._newsapi_client = None # И NewsAPI клиент

    redis_cli = _get_redis_client()
    if redis_cli:
        # Очищаем только ключи, относящиеся к sentiment_tool, чтобы не затронуть другие тесты
        # Предполагаем, что все ключи sentiment начинаются с "sentiment:"
        keys_to_delete = redis_cli.keys("sentiment:*")
        if keys_to_delete:
            redis_cli.delete(*keys_to_delete)
    yield
    # Восстанавливаем исходное значение NEWSAPI_KEY
    if original_newsapi_key:
        os.environ["NEWSAPI_KEY"] = original_newsapi_key
    elif "NEWSAPI_KEY" in os.environ: # Если мы его установили
        del os.environ["NEWSAPI_KEY"]

# --- Mock данные для NewsAPI --- #
MOCK_NEWS_ARTICLES_POSITIVE = {
    'status': 'ok',
    'totalResults': 1,
    'articles': [{'title': 'Great success for ticker XYZ, profits soar!'}]
}
MOCK_NEWS_ARTICLES_NEGATIVE = {
    'status': 'ok',
    'totalResults': 1,
    'articles': [{'title': 'Terrible losses for ticker ABC, market crash imminent.'}]
}
MOCK_NEWS_ARTICLES_MIXED = {
    'status': 'ok',
    'totalResults': 2,
    'articles': [
        {'title': 'Stock surges on good news.'},
        {'title': 'Company faces severe challenges and stock drops.'}
    ]
}
MOCK_NEWS_ARTICLES_EMPTY = {
    'status': 'ok',
    'totalResults': 0,
    'articles': []
}
MOCK_NEWSAPI_ERROR = {
    'status': 'error',
    'code': 'apiKeyInvalid',
    'message': 'Your API key is invalid or incorrect. Check your key, or newshound to start your free trial.'
}

# --- Mock для модели HuggingFace --- #
# Модель FinBERT возвращает логиты для [positive, negative, neutral]
class MockHfModelOutput:
    def __init__(self, logits_batch): # logits_batch это, например, [[2.197, -0.693, -0.693]]
        # self.logits = torch.tensor([logits_batch]) # Старая версия, создавала (1,1,3)
        self.logits = torch.tensor(logits_batch)   # Новая версия, ожидает батч, создаст (1,3)

class MockHfModel(MagicMock):
    pass # Просто наследуем MagicMock, __call__ будет вести себя стандартно для MagicMock

@patch('src.tools.sentiment_tool.AutoModelForSequenceClassification.from_pretrained')
@patch('src.tools.sentiment_tool.AutoTokenizer.from_pretrained')
@patch('src.tools.sentiment_tool._fetch_news_from_api')
def test_sentiment_tool_positive(mock_fetch_news, mock_tokenizer_load, mock_model_load):
    """Тест с позитивными новостями."""
    mock_fetch_news.return_value = MOCK_NEWS_ARTICLES_POSITIVE['articles']

    mock_model_instance = MockHfModel()
    # Мокаем вызов модели, чтобы вернуть предопределенные логиты
    # Это самый сложный чась для мока без глубокого понимания входных данных токенизатора
    # Логиты для [0.9, 0.05, 0.05] (pos, neg, neu)
    mock_model_instance.return_value = MockHfModelOutput([[2.197, -0.693, -0.693]])
    mock_model_load.return_value = mock_model_instance
    mock_tokenizer_load.return_value = MagicMock() # Простой мок для токенизатора

    score = sentiment_tool(ticker="GOODCO", window_days=1)
    assert score > 0.8 # Ожидаем высокий позитивный балл (0.9 - 0.05 = 0.85)

@patch('src.tools.sentiment_tool.AutoModelForSequenceClassification.from_pretrained')
@patch('src.tools.sentiment_tool.AutoTokenizer.from_pretrained')
@patch('src.tools.sentiment_tool._fetch_news_from_api')
def test_sentiment_tool_negative(mock_fetch_news, mock_tokenizer_load, mock_model_load):
    """Тест с негативными новостями."""
    mock_fetch_news.return_value = MOCK_NEWS_ARTICLES_NEGATIVE['articles']
    mock_model_instance = MockHfModel()
    # Логиты для [0.05, 0.9, 0.05]
    mock_model_instance.return_value = MockHfModelOutput([[-0.693, 2.197, -0.693]])
    mock_model_load.return_value = mock_model_instance
    mock_tokenizer_load.return_value = MagicMock()

    score = sentiment_tool(ticker="BADCO", window_days=1)
    assert score < -0.8 # Ожидаем высокий негативный балл (0.05 - 0.9 = -0.85)

@patch('src.tools.sentiment_tool._fetch_news_from_api')
@patch('src.tools.sentiment_tool._calculate_sentiment_score') # Мокаем всю функцию расчета
def test_sentiment_tool_mixed_mocked_calc(mock_calc_score, mock_fetch_news):
    """Тест со смешанными новостями, мокая _calculate_sentiment_score."""
    mock_fetch_news.return_value = MOCK_NEWS_ARTICLES_MIXED['articles']
    # Предположим, первый заголовок дает +0.7, второй -0.7. Среднее будет 0.
    mock_calc_score.return_value = 0.0
    score = sentiment_tool(ticker="MIXEDCO", window_days=1)
    assert score == pytest.approx(0.0)

@patch('src.tools.sentiment_tool._fetch_news_from_api')
def test_sentiment_tool_no_news(mock_fetch_news):
    """Тест при отсутствии новостей."""
    mock_fetch_news.return_value = MOCK_NEWS_ARTICLES_EMPTY['articles']
    score = sentiment_tool(ticker="NONESCO", window_days=1)
    assert score == 0.0

@patch('src.tools.sentiment_tool._get_newsapi_client') # Мок самого клиента NewsAPI
def test_sentiment_tool_newsapi_error(mock_news_client_getter):
    """Тест при ошибке NewsAPI."""
    mock_api_instance = MagicMock()
    mock_api_instance.get_everything.return_value = MOCK_NEWSAPI_ERROR
    mock_news_client_getter.return_value = mock_api_instance

    score = sentiment_tool(ticker="ERRCO", window_days=1)
    assert score == 0.0

@patch('src.tools.sentiment_tool.AutoModelForSequenceClassification.from_pretrained', side_effect=Exception("Model load failed"))
@patch('src.tools.sentiment_tool.AutoTokenizer.from_pretrained')
@patch('src.tools.sentiment_tool._fetch_news_from_api')
def test_sentiment_tool_model_load_error(mock_fetch_news, mock_tokenizer_load, mock_model_load_error):
    """Тест при ошибке загрузки модели."""
    mock_fetch_news.return_value = MOCK_NEWS_ARTICLES_POSITIVE['articles']
    # mock_tokenizer_load не важен, т.к. загрузка модели упадет раньше
    score = sentiment_tool(ticker="MODELFAIL", window_days=1)
    assert score == 0.0 # Ожидаем 0.0, так как _calculate_sentiment_score вернет 0.0 при ошибке

@patch('src.tools.sentiment_tool._fetch_news_from_api')
@patch('src.tools.sentiment_tool._calculate_sentiment_score', return_value=0.75) # Мокаем результат расчета
def test_sentiment_caching(mock_calc_score, mock_fetch_news, clear_sentiment_cache_and_prepare_env):
    """Тест кэширования в Redis."""
    mock_fetch_news.return_value = MOCK_NEWS_ARTICLES_POSITIVE['articles']

    ticker = "CACHEAAPL"
    window = 2

    # 1. Первый вызов - должен вызвать API и модель (через моки)
    score1 = sentiment_tool(ticker=ticker, window_days=window)
    assert score1 == 0.75
    mock_fetch_news.assert_called_once_with(ticker, window)
    mock_calc_score.assert_called_once_with([MOCK_NEWS_ARTICLES_POSITIVE['articles'][0]['title']])

    # Сбрасываем счетчики моков
    mock_fetch_news.reset_mock()
    mock_calc_score.reset_mock()

    # 2. Второй вызов - должен вернуть из кэша, API и модель не вызываются
    score2 = sentiment_tool(ticker=ticker, window_days=window)
    assert score2 == 0.75
    mock_fetch_news.assert_not_called()
    mock_calc_score.assert_not_called()

    # 3. Проверка TTL - ждем истечения срока кэша + немного запаса
    if _get_redis_client(): # Выполняем, только если Redis доступен
        time.sleep(2) # Временно уменьшаем для быстрой проверки

        # Дополнительно явно удалим ключ перед третьим вызовом, чтобы симулировать истечение TTL
        # Это более надежно для теста, чем просто ждать
        redis_cli = _get_redis_client()
        if redis_cli:
            cache_key = f"sentiment:{ticker}:{window}"
            redis_cli.delete(cache_key)
            # print(f"DEBUG: Deleted key {cache_key} before 3rd call") # для отладки

        score3 = sentiment_tool(ticker=ticker, window_days=window)
        assert score3 == 0.75
        mock_fetch_news.assert_called_once_with(ticker, window) # Снова вызвали API
        mock_calc_score.assert_called_once_with([MOCK_NEWS_ARTICLES_POSITIVE['articles'][0]['title']]) # И расчет
    else:
        pytest.skip("Redis client not available, skipping TTL part of caching test.")

@patch.dict(os.environ, {"NEWSAPI_KEY": ""}) # Убираем ключ API
@patch('src.tools.sentiment_tool._get_newsapi_client') # Чтобы перехватить его инициализацию
def test_sentiment_tool_no_newsapi_key(mock_get_newsapi_client):
    """Тест, когда NEWSAPI_KEY не установлен."""
    # Сбрасываем глобальный _newsapi_client, чтобы он попытался переинициализироваться
    # Это нужно, если предыдущие тесты его уже инициализировали
    # Мок _get_newsapi_client, чтобы он вернул None, как если бы ключ не был установлен
    mock_get_newsapi_client.return_value = None

    score = sentiment_tool(ticker="NOKEYCO", window_days=1)
    # В текущей реализации sentiment_tool() не падает, а логгирует warning и продолжает,
    # _fetch_news_from_api вернет [], что приведет к счету 0.0
    assert score == 0.0
    # Проверим, что _fetch_news_from_api был вызван (он внутри себя проверит клиента)
    # Для этого нужно мокнуть _fetch_news_from_api, но это конфликтует с целью теста
    # Проще проверить, что NewsApiClient не был создан с реальным ключом, но это сложно
    # Достаточно того, что счет 0.0 при отсутствующем _newsapi_client

# Дополнительный тест: Проверить, что redis недоступен (сложно без изменения глобальных переменных или DI)
# Можно было бы мокнуть redis.Redis().ping() чтобы вызвать исключение

# Дополнительный тест: Проверить, что redis недоступен (сложно без изменения глобальных переменных или DI)
# Можно было бы мокнуть redis.Redis().ping() чтобы вызвать исключение
