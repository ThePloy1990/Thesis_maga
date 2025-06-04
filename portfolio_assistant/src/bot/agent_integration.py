import logging
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Tuple, List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import yfinance as yf
import pandas as pd
import os
from openai import OpenAI
import tempfile
import matplotlib.pyplot as plt
from dotenv import load_dotenv

from ..pf_agents import Runner
from ..tools.forecast_tool import forecast_tool  
from ..tools.optimize_tool import optimize_tool
from ..tools.sentiment_tool import sentiment_tool
from ..tools.scenario_tool import scenario_adjust_tool
from ..tools.performance_tool import performance_tool
from ..tools.index_composition_tool import index_composition_tool, list_available_indices
from ..tools.risk_analysis_tool import risk_analysis_tool
from ..tools.efficient_frontier_tool import efficient_frontier_tool
from ..tools.correlation_tool import correlation_tool
from ..market_snapshot.registry import SnapshotRegistry
from ..market_snapshot.model import MarketSnapshot, SnapshotMeta

# Загружаем переменные окружения из .env файла
load_dotenv()

logger = logging.getLogger(__name__)

# Пул исполнителей для асинхронного запуска агента
_executor = ThreadPoolExecutor(max_workers=4)

# Константы для директорий с моделями
MODELS_DIR = Path("../models")  # Путь к директории с моделями CatBoost относительно portfolio_assistant

# Кеш для списка доступных тикеров
_available_tickers_cache = None
_available_tickers_last_update = None

def _update_all_users_snapshot_id_sync(snapshot_id: str) -> Tuple[int, str]:
    """
    Синхронная версия обновления ID снапшота для всех пользователей.
    
    Args:
        snapshot_id: ID нового снапшота
    
    Returns:
        Tuple[int, str]: Кортеж с количеством обновленных пользователей и ID установленного снапшота
    """
    try:
        # Импортируем необходимые модули здесь чтобы избежать циклических импортов
        import redis
        from .state import USER_STATE_PREFIX, update_snapshot_id
        from .config import REDIS_URL
        
        # Подключение к Redis
        try:
            redis_client = redis.from_url(REDIS_URL)
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            return (0, f"Redis connection error: {str(e)}")
        
        logger.info(f"Updating all users to snapshot: {snapshot_id}")
        
        # Получаем всех пользователей из Redis
        user_keys = redis_client.keys(f"{USER_STATE_PREFIX}*")
        updated_count = 0
        
        for user_key in user_keys:
            try:
                # Получаем ID пользователя из ключа (преобразуем bytes в str)
                user_key_str = user_key.decode('utf-8') if isinstance(user_key, bytes) else user_key
                user_id_str = user_key_str.replace(USER_STATE_PREFIX, "")
                user_id = int(user_id_str)
                
                # Обновляем ID снапшота для пользователя
                result = update_snapshot_id(user_id, snapshot_id)
                if result:
                    updated_count += 1
                    logger.debug(f"Updated snapshot ID for user {user_id}")
                else:
                    logger.warning(f"Failed to update snapshot ID for user {user_id}")
            except Exception as e:
                logger.error(f"Error updating user {user_key}: {str(e)}")
                continue
        
        logger.info(f"Successfully updated {updated_count} users to snapshot {snapshot_id}")
        return (updated_count, snapshot_id)
    except Exception as e:
        logger.error(f"Error updating all users' snapshot ID: {str(e)}")
        return (0, f"Error: {str(e)}")

def get_available_tickers(use_cache: bool = True) -> List[str]:
    """
    Получает список доступных тикеров на основе наличия моделей CatBoost.
    
    Args:
        use_cache: Использовать ли кешированный список тикеров (True по умолчанию)
    
    Returns:
        Список тикеров, для которых есть модели
    """
    global _available_tickers_cache, _available_tickers_last_update
    
    # Если есть кешированный список и запрошено использование кеша
    current_time = datetime.now(timezone.utc)
    if use_cache and _available_tickers_cache is not None and _available_tickers_last_update is not None:
        # Проверяем, не устарел ли кеш (используем кеш до 1 часа)
        if (current_time - _available_tickers_last_update).total_seconds() < 3600:  # 1 час в секундах
            logger.debug(f"Используем кеш с {len(_available_tickers_cache)} тикерами")
            return _available_tickers_cache
    
    tickers = []
    
    try:
        # Получаем абсолютный путь к директории models/
        models_path = Path(__file__).absolute().parent.parent.parent.parent / "models"
        logger.info(f"Ищу модели в директории: {models_path}")
        
        # Смотрим содержимое директории models/
        files = list(models_path.glob("catboost_*.cbm"))
        
        if not files:
            logger.warning(f"Не найдены файлы моделей в {models_path}")
            return []
            
        logger.info(f"Найдено {len(files)} файлов моделей")
        
        for file in files:
            # Извлекаем имя тикера из имени файла (catboost_AAPL.cbm -> AAPL)
            ticker = file.stem.replace("catboost_", "")
            if ticker:
                tickers.append(ticker)
                
        logger.info(f"Доступные тикеры: {', '.join(tickers[:5])}... (всего {len(tickers)})")
        
        # Обновляем кеш
        _available_tickers_cache = tickers
        _available_tickers_last_update = current_time
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка доступных тикеров: {e}")
    
    return tickers

async def run_portfolio_manager(text: str, state: Dict[str, Any], user_id: int = None) -> Tuple[str, List[str]]:
    """
    Асинхронно запускает портфельного агента-менеджера.
    
    Args:
        text: Запрос пользователя
        state: Состояние пользователя
        user_id: ID пользователя
        
    Returns:
        Кортеж из markdown-текста и списка путей к изображениям
    """
    logger.info(f"Running portfolio manager with text: {text[:100]}...")
    
    try:
        # Запускаем выполнение в отдельном потоке, чтобы не блокировать event loop
        return await asyncio.get_event_loop().run_in_executor(
            _executor, _run_portfolio_manager_sync, text, state, user_id
        )
    except Exception as e:
        logger.error(f"Error running portfolio manager: {str(e)}")
        return f"Произошла ошибка при обработке запроса: {str(e)}", []

def _run_portfolio_manager_sync(text: str, state: Dict[str, Any], user_id: int = None) -> Tuple[str, List[str]]:
    """
    Синхронная версия запуска портфельного агента с использованием OpenAI API.
    
    Args:
        text: Запрос пользователя
        state: Состояние пользователя
        user_id: ID пользователя
        
    Returns:
        Кортеж из markdown-текста и списка путей к изображениям
    """
    try:
        # Получаем ключевые параметры из состояния пользователя
        risk_profile = state.get('risk_profile', 'не указан')
        budget = state.get('budget', 0)
        positions = state.get('positions', {})
        snapshot_id = state.get('last_snapshot_id')
        
        # Получаем историю диалога
        dialog_memory = state.get('dialog_memory', [])
        
        # Получаем API ключ из переменных окружения (загруженных через load_dotenv)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY не найден в переменных окружения")
            return "OPENAI_API_KEY не найден. Убедитесь, что файл .env содержит правильный ключ.", []
            
        # Создаем клиента OpenAI с полученным ключом
        client = OpenAI(api_key=api_key)
        
        # Получаем информацию о последнем снапшоте
        registry = SnapshotRegistry()
        latest_snapshot = None
        snapshot_info = "Снапшот отсутствует"
        
        if snapshot_id:
            latest_snapshot = registry.load(snapshot_id)
        else:
            latest_snapshot = registry.latest()
            if latest_snapshot:
                snapshot_id = latest_snapshot.meta.id
                state['last_snapshot_id'] = snapshot_id
        
        if latest_snapshot:
            # Получаем данные о снапшоте
            tickers = getattr(latest_snapshot.meta, "tickers", []) or getattr(latest_snapshot.meta, "asset_universe", [])
            timestamp = getattr(latest_snapshot.meta, "timestamp", None) or getattr(latest_snapshot.meta, "created_at", None)
            snapshot_info = f"Снапшот {snapshot_id} от {timestamp.isoformat()}, содержит {len(tickers)} тикеров"
        
        # Получаем список доступных тикеров из моделей CatBoost
        available_tickers = get_available_tickers()
        if not available_tickers:
            logger.warning("Не найдены доступные модели для тикеров")
        
        # Группируем тикеры по 5 для лучшей читаемости
        tickers_chunks = []
        for i in range(0, len(available_tickers), 5):
            chunk = available_tickers[i:i+5]
            tickers_chunks.append(", ".join(chunk))
        tickers_display = "\n".join(tickers_chunks)
        
        # Формируем базовый контекст для агента
        system_message = f"""
        Ты - ИИ-портфельный ассистент. Ты помогаешь пользователю анализировать и оптимизировать инвестиционный портфель.
        
        Информация о пользователе:
        - Риск-профиль: {risk_profile}
        - Бюджет: ${budget:,.2f}
        - Текущие позиции: {positions}
        
        Доступная информация о рынке:
        - {snapshot_info}
        
        Доступные тикеры ({len(available_tickers)}):
        {tickers_display}
        
        ВАЖНО: 
        - Ты можешь работать ТОЛЬКО с указанными выше тикерами (~{len(available_tickers)} шт.), для которых есть предобученные модели CatBoost.
        - Все прогнозы модели рассчитаны на горизонт 3 МЕСЯЦА (квартальные прогнозы).
        - Оптимизация портфеля по умолчанию использует алгоритм HRP (Hierarchical Risk Parity) для лучшей диверсификации.
        - Также доступна оптимизация под целевую доходность (method="target_return" с параметром target_return).
        - Никогда не предлагай тикеры, которых нет в списке доступных.
        
        Ты можешь использовать следующие инструменты:
        
        БАЗОВЫЕ ИНСТРУМЕНТЫ:
        1. get_forecast - получить 3-месячный прогноз доходности и риска для тикера
        2. optimize_portfolio - оптимизировать портфель по тикерам (HRP, Markowitz, Black-Litterman, target_return)
        3. analyze_sentiment - анализировать настроения рынка по тикеру
        4. adjust_scenario - создать сценарий с изменением ожидаемой доходности
        5. plot_portfolio - создать график распределения портфеля
        6. analyze_performance - анализировать РЕАЛЬНУЮ производительность портфеля на исторических данных
        
        НОВЫЕ РАСШИРЕННЫЕ ИНСТРУМЕНТЫ:
        7. get_index_composition - получить состав популярных индексов (S&P 500 топ-10, Dow 30, tech giants, секторы)
        8. analyze_risks - углубленный анализ рисков (VaR, Expected Shortfall, максимальная просадка, корреляции)
        9. build_efficient_frontier - построить эффективную границу для оптимальных портфелей по риск/доходность
        10. analyze_correlations - анализ корреляций между активами с визуализацией
        11. update_portfolio - обновить и зафиксировать позиции пользователя в портфеле (использовать когда пользователь просит "обновить портфель", "зафиксировать портфель", "принять портфель")
        12. get_portfolio_metrics - получить уже известные метрики портфеля из истории диалога (коэффициент Шарпа, доходность, риск)
        
        ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ НОВЫХ ИНСТРУМЕНТОВ:
        - "Создай консервативный портфель из топ-10 S&P 500" → get_index_composition("sp500_top10") + optimize_portfolio
        - "Оптимизируй мой портфель под 15% годовых" → optimize_portfolio(method="target_return", target_return=0.15)
        - "Проанализируй риски портфеля с Tesla и Apple" → analyze_risks(["TSLA", "AAPL"], weights)
        - "Покажи эффективную границу для технологических акций" → build_efficient_frontier(sector="tech_giants")
        - "Какова корреляция между BTC и золотом?" → analyze_correlations для криптовалют и золота
        - "Обнови портфель" или "Зафиксируй портфель" → update_portfolio (автоматически найдет веса из предыдущего ответа)
        - "Какой коэффициент Шарпа у моего портфеля?" → get_portfolio_metrics (найдет в истории диалога)
        - "Какая доходность моего портфеля?" → get_portfolio_metrics (извлечет уже известные метрики)
        
        При создании портфеля:
        - Указывай что прогнозы на 3 месяца (квартальные)
        - Используй analyze_performance для расчета реальных метрик (годовая доходность, Alpha, Beta)
        - Объясняй пользователю разницу между теоретическими прогнозами и реальной исторической производительностью
        - Подчеркивай что Alpha показывает превышение доходности над рынком (S&P 500)
        - Beta показывает чувствительность портфеля к рыночным движениям
        - Используй новые инструменты для более глубокого анализа
        
        ВАЖНО: Когда пользователь спрашивает про метрики своего портфеля (коэффициент Шарпа, доходность, риск), ВСЕГДА сначала используй get_portfolio_metrics чтобы получить уже известные значения из истории диалога. НЕ пытайся вычислить эти метрики самостоятельно или задавать значение 0.0 - используй инструмент!
        
        Отвечай на вопросы пользователя, используя доступные инструменты.
        Твой ответ должен быть в формате Markdown.
        """
        
        # Преобразуем историю диалога в формат OpenAI
        messages = [{"role": "system", "content": system_message}]
        
        # Добавляем историю диалога, если она есть (макс. последние 10 сообщений)
        recent_dialog = dialog_memory[-10:] if len(dialog_memory) > 10 else dialog_memory
        for msg in recent_dialog:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # Пропускаем сообщения типа 'tool', так как они требуют особой обработки
            if role != 'tool':
                messages.append({"role": role, "content": content})
        
        # Добавляем текущий запрос пользователя
        messages.append({"role": "user", "content": text})
        
        # Определяем инструменты для OpenAI
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_forecast",
                    "description": "Прогнозирует доходность и риск для указанного тикера",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": f"Тикер акции из доступного списка: {', '.join(available_tickers)}"
                            }
                        },
                        "required": ["ticker"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "optimize_portfolio",
                    "description": "Оптимизирует портфель на основе указанных тикеров",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tickers": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": f"Список тикеров для включения в портфель, выбирайте только из доступных: {', '.join(available_tickers)}"
                            },
                            "risk_aversion": {
                                "type": "number",
                                "description": "Коэффициент неприятия риска (1.0 - нейтральный, >1.0 - консервативный, <1.0 - агрессивный)"
                            },
                            "method": {
                                "type": "string",
                                "description": "Метод оптимизации: hrp, markowitz, black_litterman, target_return"
                            },
                            "target_return": {
                                "type": "number",
                                "description": "Целевая доходность для метода target_return"
                            }
                        },
                        "required": ["tickers"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_sentiment",
                    "description": "Анализирует новостной сентимент для указанного тикера",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": f"Тикер акции из доступного списка: {', '.join(available_tickers)}"
                            },
                            "window_days": {
                                "type": "integer",
                                "description": "Количество дней для анализа новостей"
                            }
                        },
                        "required": ["ticker"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "adjust_scenario",
                    "description": "Создает сценарий с указанными корректировками ожидаемой доходности",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tickers": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": f"Список тикеров для сценария, выбирайте только из доступных: {', '.join(available_tickers)}"
                            },
                            "adjustments": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "number"
                                },
                                "description": "Словарь корректировок в формате {тикер: изменение_в_процентах}"
                            }
                        },
                        "required": ["tickers", "adjustments"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "plot_portfolio",
                    "description": "Создает график распределения портфеля",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "weights": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "number"
                                },
                                "description": "Словарь весов портфеля в формате {тикер: вес}"
                            }
                        },
                        "required": ["weights"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_performance",
                    "description": "Анализирует реальную производительность портфеля на исторических данных (за последние 3 месяца). Рассчитывает годовую доходность, альфу и бету относительно S&P 500.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "weights": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "number"
                                },
                                "description": "Словарь весов портфеля в формате {тикер: вес}"
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Начальная дата анализа в формате YYYY-MM-DD (опционально, по умолчанию 3 месяца назад)"
                            },
                            "end_date": {
                                "type": "string", 
                                "description": "Конечная дата анализа в формате YYYY-MM-DD (опционально, по умолчанию сегодня)"
                            }
                        },
                        "required": ["weights"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_index_composition",
                    "description": "Возвращает состав популярных фондовых индексов для создания портфелей",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "index_name": {
                                "type": "string",
                                "description": "Название индекса: sp500_top10, sp500_top20, dow30, nasdaq_top10, tech_giants, financial_sector, energy_sector, healthcare_sector, consumer_staples"
                            }
                        },
                        "required": ["index_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_risks",
                    "description": "Проводит углубленный анализ рисков портфеля или отдельных активов. Рассчитывает VaR, ожидаемые потери, корреляции.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tickers": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": f"Список тикеров для анализа рисков, выбирайте только из доступных: {', '.join(available_tickers)}"
                            },
                            "weights": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "number"
                                },
                                "description": "Словарь весов портфеля в формате {тикер: вес} (опционально для портфельного анализа)"
                            },
                            "confidence_level": {
                                "type": "number",
                                "description": "Уровень доверия для VaR (0.90, 0.95, 0.99). По умолчанию 0.95"
                            }
                        },
                        "required": ["tickers"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "build_efficient_frontier",
                    "description": "Строит эффективную границу для заданных активов или сектора. Показывает оптимальные портфели по соотношению риск/доходность.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tickers": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": f"Список тикеров для построения границы, выбирайте только из доступных: {', '.join(available_tickers)}"
                            },
                            "sector": {
                                "type": "string",
                                "description": "Название сектора вместо списка тикеров: tech_giants, financial_sector, energy_sector, healthcare_sector, consumer_staples"
                            },
                            "num_portfolios": {
                                "type": "integer",
                                "description": "Количество точек на границе (по умолчанию 100)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_correlations",
                    "description": "Анализирует корреляции между активами. Полезно для диверсификации портфеля.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tickers": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": f"Список тикеров для анализа корреляций, выбирайте только из доступных: {', '.join(available_tickers)}"
                            },
                            "method": {
                                "type": "string",
                                "description": "Метод корреляции: pearson, spearman, kendall (по умолчанию pearson)"
                            },
                            "rolling_window": {
                                "type": "integer",
                                "description": "Размер окна для скользящей корреляции в днях (опционально)"
                            }
                        },
                        "required": ["tickers"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_portfolio",
                    "description": "Обновляет и фиксирует позиции пользователя в портфеле. Используется когда пользователь просит 'обновить портфель', 'зафиксировать портфель', 'принять портфель' или 'установить позиции'. Если веса не переданы, автоматически извлекает их из предыдущего ответа с портфелем.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "weights": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "number"
                                },
                                "description": "Словарь весов портфеля в формате {тикер: вес_в_процентах} например {'AAPL': 25.5, 'MSFT': 30.0}. Опционально - будет извлечен из предыдущего ответа если не указан."
                            },
                            "budget": {
                                "type": "number",
                                "description": "Бюджет пользователя для расчета количества акций (опционально, используется текущий бюджет пользователя)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_portfolio_metrics",
                    "description": "Получает уже известные метрики текущего портфеля пользователя из истории диалога. ОБЯЗАТЕЛЬНО используйте этот инструмент когда пользователь спрашивает о коэффициенте Шарпа, доходности или риске своего портфеля, а не пытайтесь вычислить самостоятельно. Извлекает: коэффициент Шарпа, ожидаемую доходность, риск.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        ]
        
        # Выполняем запрос к OpenAI
        logger.info("Sending request to OpenAI")
        
        # Пути к созданным графикам
        image_paths = []
        
        # Цикл общения с моделью и выполнения действий
        max_turns = 5  # Максимальное количество итераций для предотвращения зацикливания
        response_text = ""
        
        # Определяем функции для инструментов
        def get_forecast(ticker: str) -> Dict[str, Any]:
            """Прогнозирует доходность и риск для указанного тикера."""
            logger.info(f"Using forecast_tool for {ticker}")
            # Проверяем, есть ли такой тикер в доступных
            if ticker not in available_tickers:
                return {"error": f"Тикер {ticker} недоступен для прогнозирования"}
            return forecast_tool(ticker, snapshot_id)
        
        def optimize_portfolio(tickers: List[str], risk_aversion: float = 1.0, method: str = "hrp", target_return: float = None) -> Dict[str, Any]:
            """Оптимизирует портфель на основе указанных тикеров."""
            logger.info(f"Using optimize_tool for {tickers} with method {method}")
            
            # Проверяем, что все тикеры из доступного списка
            valid_tickers = [t for t in tickers if t in available_tickers]
            if len(valid_tickers) < len(tickers):
                invalid_tickers = [t for t in tickers if t not in available_tickers]
                logger.warning(f"Следующие тикеры недоступны и будут исключены: {invalid_tickers}")
                
            if len(valid_tickers) < 3:
                return {"error": "Для оптимизации портфеля требуется минимум 3 доступных тикера", 
                        "weights": {t: 1.0/len(valid_tickers) for t in valid_tickers}}
            
            try:
                # Получаем последний снапшот
                registry = SnapshotRegistry()
                correct_snapshot_id = snapshot_id
                
                if not correct_snapshot_id:
                    # Если ID снэпшота не предоставлен, используем последний
                    latest_snapshot = registry.latest()
                    if latest_snapshot:
                        correct_snapshot_id = latest_snapshot.meta.id
                    else:
                        return {"error": "Не удалось найти актуальный снапшот для оптимизации", 
                                "weights": {t: 1.0/len(valid_tickers) for t in valid_tickers}}
                
                logger.info(f"Доступно {len(available_tickers)} тикеров для оптимизации")
                logger.info(f"Оптимизация портфеля для {len(valid_tickers)} тикеров с использованием снапшота {correct_snapshot_id}")
                
                # Вызываем оптимизацию с правильными параметрами
                return optimize_tool(
                    tickers=valid_tickers, 
                    snapshot_id=correct_snapshot_id, 
                    risk_aversion=risk_aversion,
                    method=method,
                    target_return=target_return
                )
            except Exception as e:
                logger.error(f"Optimization error: {str(e)}")
                # В случае ошибки возвращаем равномерное распределение
                return {"weights": {t: 1.0/len(valid_tickers) for t in valid_tickers},
                        "exp_ret": None, 
                        "risk": None,
                        "sharpe": None,
                        "error": f"Ошибка оптимизации: {str(e)}"}
        
        def analyze_sentiment(ticker: str, window_days: int = 7) -> Dict[str, Any]:
            """Анализирует новостной сентимент для указанного тикера."""
            logger.info(f"Using sentiment_tool for {ticker}")
            # Проверяем, есть ли такой тикер в доступных
            if ticker not in available_tickers:
                return {"error": f"Тикер {ticker} недоступен для анализа сентимента"}
            return sentiment_tool(ticker, window_days=window_days)
        
        def adjust_scenario(tickers: List[str], adjustments: Dict[str, float]) -> Dict[str, Any]:
            """Создает сценарий с указанными корректировками ожидаемой доходности."""
            logger.info(f"Using scenario_adjust_tool with adjustments {adjustments}")
            
            # Проверяем, что все тикеры из доступного списка
            valid_tickers = [t for t in tickers if t in available_tickers]
            if len(valid_tickers) < len(tickers):
                invalid_tickers = [t for t in tickers if t not in available_tickers]
                logger.warning(f"Следующие тикеры недоступны и будут исключены: {invalid_tickers}")
                
            # Также проверяем корректировки
            valid_adjustments = {k: v for k, v in adjustments.items() if k in available_tickers}
            
            try:
                # Вызываем инструмент сценарного моделирования с правильными параметрами
                result = scenario_adjust_tool(
                    tickers=valid_tickers,
                    adjustments=valid_adjustments,
                    base_snapshot_id=snapshot_id
                )
                return result
            except Exception as e:
                logger.error(f"Error in scenario adjustment: {str(e)}", exc_info=True)
                return {
                    "error": f"Ошибка при создании сценария: {str(e)}",
                    "snapshot_id": None
                }
        
        def plot_portfolio(weights: Dict[str, float]) -> str:
            """Создает график распределения портфеля и возвращает путь к изображению."""
            logger.info(f"Creating portfolio plot with weights {weights}")
            
            # Проверяем, есть ли веса для построения графика
            if not weights:
                # Если весов нет, создаем пустой график с сообщением об ошибке
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                    plt.figure(figsize=(10, 6))
                    plt.text(0.5, 0.5, "Нет данных для визуализации", 
                            horizontalalignment='center', verticalalignment='center', fontsize=14)
                    plt.axis('off')
                    plt.savefig(tmp_file.name)
                    plt.close()
                    return tmp_file.name
            
            # Создаем временный файл для графика
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                plt.figure(figsize=(10, 6))
                plt.pie(
                    list(weights.values()), 
                    labels=list(weights.keys()), 
                    autopct='%1.1f%%', 
                    startangle=90
                )
                plt.axis('equal')
                plt.title('Структура портфеля')
                plt.savefig(tmp_file.name)
                plt.close()
                
                return tmp_file.name
        
        def analyze_performance(weights: Dict[str, float], start_date: str = None, end_date: str = None) -> Dict[str, Any]:
            """Анализирует реальную производительность портфеля на исторических данных."""
            logger.info(f"Analyzing performance for portfolio with weights {weights}")
            
            # Проверяем, есть ли веса для анализа
            if not weights:
                logger.info("Weights not provided, trying to extract from dialog history")
                # Пытаемся извлечь веса из истории диалога
                portfolio_info = _find_portfolio_info_in_history()
                if portfolio_info.get('weights'):
                    weights = portfolio_info['weights']
                    logger.info(f"Extracted weights from dialog history: {weights}")
                else:
                    return {"error": "Веса портфеля не предоставлены и не найдены в истории диалога"}
            
            # Проверяем, что все тикеры из доступного списка
            valid_weights = {t: w for t, w in weights.items() if t in available_tickers}
            if len(valid_weights) < len(weights):
                invalid_tickers = [t for t in weights.keys() if t not in available_tickers]
                logger.warning(f"Следующие тикеры недоступны и будут исключены из анализа: {invalid_tickers}")
            
            if not valid_weights:
                return {"error": "Нет доступных тикеров для анализа производительности"}
            
            # Перенормализуем веса
            total_weight = sum(valid_weights.values())
            if total_weight > 0:
                valid_weights = {t: w/total_weight for t, w in valid_weights.items()}
            
            try:
                # Вызываем инструмент анализа производительности
                result = performance_tool(
                    weights=valid_weights,
                    start_date=start_date,
                    end_date=end_date
                )
                
                # Добавляем информацию о горизонте прогноза
                if "error" not in result:
                    result["forecast_horizon"] = "3 months"
                    result["note"] = "Анализ основан на 3-месячных прогнозах доходности"
                
                return result
                
            except Exception as e:
                logger.error(f"Error in performance analysis: {str(e)}")
                return {"error": f"Ошибка анализа производительности: {str(e)}"}
        
        def get_portfolio_metrics() -> Dict[str, Any]:
            """Получает метрики портфеля (включая коэффициент Шарпа) из истории диалога."""
            logger.info("Getting portfolio metrics from dialog history")
            
            try:
                portfolio_info = _find_portfolio_info_in_history()
                
                if not portfolio_info:
                    return {"error": "Информация о портфеле не найдена в истории диалога"}
                
                result = {}
                
                # Добавляем найденные метрики
                if portfolio_info.get('metrics'):
                    metrics = portfolio_info['metrics']
                    result.update(metrics)
                    
                    # Форматируем метрики для лучшего отображения
                    formatted_metrics = {}
                    if 'expected_return' in metrics:
                        formatted_metrics['Ожидаемая доходность'] = f"{metrics['expected_return']:.2f}%"
                    if 'risk' in metrics:
                        formatted_metrics['Риск (стандартное отклонение)'] = f"{metrics['risk']:.2f}%"
                    if 'sharpe_ratio' in metrics:
                        formatted_metrics['Коэффициент Шарпа'] = f"{metrics['sharpe_ratio']:.2f}"
                    
                    result['formatted_metrics'] = formatted_metrics
                
                # Добавляем информацию о весах если найдены
                if portfolio_info.get('weights'):
                    weights = portfolio_info['weights']
                    result['weights_found'] = True
                    result['tickers_count'] = len(weights)
                    result['sample_weights'] = dict(list(weights.items())[:5])  # Показываем первые 5
                else:
                    result['weights_found'] = False
                
                return result
                
            except Exception as e:
                logger.error(f"Error getting portfolio metrics: {str(e)}")
                return {"error": f"Ошибка получения метрик портфеля: {str(e)}"}
        
        def get_index_composition(index_name: str) -> Dict[str, Any]:
            """Получает состав популярного фондового индекса."""
            logger.info(f"Getting index composition for {index_name}")
            try:
                return index_composition_tool(index_name=index_name, filter_available=True)
            except Exception as e:
                logger.error(f"Error getting index composition: {str(e)}")
                return {"error": f"Ошибка получения состава индекса: {str(e)}"}
        
        def analyze_risks(tickers: List[str], weights: Dict[str, float] = None, confidence_level: float = 0.95) -> Dict[str, Any]:
            """Проводит углубленный анализ рисков портфеля или отдельных активов."""
            logger.info(f"Analyzing risks for {tickers}")
            
            # Проверяем доступность тикеров
            valid_tickers = [t for t in tickers if t in available_tickers]
            if len(valid_tickers) < len(tickers):
                invalid_tickers = [t for t in tickers if t not in available_tickers]
                logger.warning(f"Следующие тикеры недоступны: {invalid_tickers}")
            
            if not valid_tickers:
                return {"error": "Нет доступных тикеров для анализа рисков"}
            
            try:
                return risk_analysis_tool(
                    tickers=valid_tickers,
                    weights=weights,
                    confidence_level=confidence_level,
                    snapshot_id=snapshot_id
                )
            except Exception as e:
                logger.error(f"Error in risk analysis: {str(e)}")
                return {"error": f"Ошибка анализа рисков: {str(e)}"}
        
        def build_efficient_frontier(tickers: List[str] = None, sector: str = None, num_portfolios: int = 100) -> Dict[str, Any]:
            """Строит эффективную границу для заданных активов или сектора."""
            if sector:
                logger.info(f"Building efficient frontier for sector: {sector}")
            else:
                logger.info(f"Building efficient frontier for tickers: {tickers}")
            
            try:
                result = efficient_frontier_tool(
                    tickers=tickers,
                    sector=sector,
                    num_portfolios=num_portfolios,
                    snapshot_id=snapshot_id
                )
                
                # Добавляем график в список изображений если он создан
                if "plot_path" in result and result["plot_path"]:
                    image_paths.append(result["plot_path"])
                
                return result
            except Exception as e:
                logger.error(f"Error building efficient frontier: {str(e)}")
                return {"error": f"Ошибка построения эффективной границы: {str(e)}"}
        
        def analyze_correlations(tickers: List[str], method: str = "pearson", rolling_window: int = None) -> Dict[str, Any]:
            """Анализирует корреляции между активами."""
            logger.info(f"Analyzing correlations for {tickers}")
            
            # Проверяем доступность тикеров
            valid_tickers = [t for t in tickers if t in available_tickers]
            if len(valid_tickers) < len(tickers):
                invalid_tickers = [t for t in tickers if t not in available_tickers]
                logger.warning(f"Следующие тикеры недоступны: {invalid_tickers}")
            
            if len(valid_tickers) < 2:
                return {"error": "Для анализа корреляций требуется минимум 2 доступных тикера"}
            
            try:
                result = correlation_tool(
                    tickers=valid_tickers,
                    method=method,
                    rolling_window=rolling_window,
                    snapshot_id=snapshot_id
                )
                
                # Добавляем графики в список изображений если они созданы
                if "heatmap_path" in result and result["heatmap_path"]:
                    image_paths.append(result["heatmap_path"])
                if "rolling_plot_path" in result and result["rolling_plot_path"]:
                    image_paths.append(result["rolling_plot_path"])
                
                return result
            except Exception as e:
                logger.error(f"Error analyzing correlations: {str(e)}")
                return {"error": f"Ошибка анализа корреляций: {str(e)}"}
        
        def update_portfolio(weights: Dict[str, float] = None, user_budget: float = None) -> Dict[str, Any]:
            """Обновляет позиции пользователя в портфеле на основе весов."""
            logger.info(f"Updating portfolio with weights: {weights}")
            
            try:
                # Если веса не переданы, пытаемся извлечь их из истории диалога
                if not weights:
                    logger.info("Weights not provided, trying to extract from dialog history")
                    
                    # Получаем историю диалога
                    dialog_memory = state.get('dialog_memory', [])
                    
                    # Ищем последний ответ ассистента с информацией о портфеле
                    for msg in reversed(dialog_memory):
                        if msg.get("role") == "assistant":
                            content = msg.get("content", "")
                            # Пытаемся извлечь веса из текста
                            extracted_weights = _extract_weights_from_text(content)
                            if extracted_weights:
                                weights = extracted_weights
                                logger.info(f"Extracted weights from dialog: {weights}")
                                break
                    
                    # Если не нашли веса в истории, возвращаем ошибку
                    if not weights:
                        return {
                            "status": "error",
                            "error": "Не найдены веса портфеля для обновления. Сначала создайте оптимизированный портфель."
                        }
                
                # Используем переданный бюджет или берем из состояния пользователя
                if user_budget is None:
                    user_budget = budget
                
                # Получаем цены из снапшота
                registry = SnapshotRegistry()
                snapshot = None
                if snapshot_id:
                    snapshot = registry.load(snapshot_id)
                else:
                    snapshot = registry.latest()
                
                prices = {}
                if snapshot and hasattr(snapshot, 'prices') and snapshot.prices:
                    prices = snapshot.prices
                    logger.info(f"Loaded {len(prices)} prices from snapshot")
                else:
                    logger.warning("No prices available, using default prices")
                
                # Конвертируем веса в позиции (количество акций)
                new_positions = {}
                total_allocated = 0.0
                
                for ticker, weight_percent in weights.items():
                    if ticker not in available_tickers:
                        logger.warning(f"Ticker {ticker} not in available tickers, skipping")
                        continue
                    
                    # Получаем цену акции (по умолчанию $100)
                    stock_price = prices.get(ticker, 100.0)
                    
                    # Рассчитываем сумму для инвестирования в этот актив
                    allocation_amount = user_budget * (weight_percent / 100.0)
                    total_allocated += allocation_amount
                    
                    # Рассчитываем количество акций
                    shares_count = allocation_amount / stock_price
                    new_positions[ticker] = shares_count
                    
                    logger.debug(f"{ticker}: {weight_percent}% = ${allocation_amount:.2f} / ${stock_price:.2f} = {shares_count:.4f} shares")
                
                # Проверяем что мы не превысили бюджет
                if total_allocated > user_budget * 1.01:  # Небольшой допуск на округления
                    logger.warning(f"Total allocation ${total_allocated:.2f} exceeds budget ${user_budget:.2f}")
                
                # Импортируем функцию обновления позиций
                from .state import update_positions
                
                # Получаем user_id из параметра функции
                if user_id is None:
                    logger.error("user_id не передан в функцию update_portfolio")
                    return {
                        "status": "error",
                        "error": "Отсутствует идентификатор пользователя"
                    }
                
                # Обновляем позиции пользователя
                success = update_positions(user_id, new_positions)
                
                if success:
                    # Формируем детальный отчет по каждому тикеру
                    detailed_breakdown = []
                    for ticker, shares_count in new_positions.items():
                        stock_price = prices.get(ticker, 100.0)
                        position_value = shares_count * stock_price
                        weight_percent = weights.get(ticker, 0)
                        
                        detailed_breakdown.append({
                            "ticker": ticker,
                            "weight_percent": weight_percent,
                            "shares": shares_count,
                            "price_per_share": stock_price,
                            "total_value": position_value
                        })
                    
                    return {
                        "status": "success",
                        "message": f"Портфель успешно обновлен. Позиции установлены для {len(new_positions)} тикеров.",
                        "positions": new_positions,
                        "total_allocated": total_allocated,
                        "budget_used_percent": (total_allocated / user_budget) * 100 if user_budget > 0 else 0,
                        "detailed_breakdown": detailed_breakdown,
                        "budget": user_budget
                    }
                else:
                    return {
                        "status": "error", 
                        "error": "Не удалось сохранить обновленные позиции в базе данных"
                    }
                
            except Exception as e:
                logger.error(f"Error updating portfolio: {str(e)}")
                return {
                    "status": "error",
                    "error": f"Ошибка при обновлении портфеля: {str(e)}"
                }
        
        def _extract_weights_from_text(text: str) -> Dict[str, float]:
            """Извлекает веса портфеля из текста ответа модели."""
            weights = {}
            
            try:
                import re
                
                # Метод 1: Поиск таблицы в Markdown формате (2 колонки: Тикер и Вес)
                # Ищем строки вида: | AOS | 2.47 |
                table_pattern_2col = r'\|\s*([A-Z]{1,5})\s*\|\s*(\d+\.?\d*)\s*\|'
                table_matches_2col = re.findall(table_pattern_2col, text)
                
                if table_matches_2col:
                    logger.info(f"Found {len(table_matches_2col)} weights in 2-column table format")
                    for ticker, percentage_str in table_matches_2col:
                        # Пропускаем заголовки таблицы
                        if ticker.upper() in ['ТИКЕР', 'TICKER', 'ВЕС', 'WEIGHT']:
                            continue
                        percentage = float(percentage_str)
                        weights[ticker] = percentage
                
                # Метод 2: Поиск таблицы в Markdown формате (3 колонки: Тикер, Компания, Вес)
                # Ищем строки вида: | TICKER | Company Name | 6.55% |
                if not weights:
                    table_pattern_3col = r'\|\s*([A-Z]{1,5})\s*\|[^|]*\|\s*(\d+\.?\d*)%?\s*\|'
                    table_matches_3col = re.findall(table_pattern_3col, text)
                    
                    if table_matches_3col:
                        logger.info(f"Found {len(table_matches_3col)} weights in 3-column table format")
                        for ticker, percentage_str in table_matches_3col:
                            percentage = float(percentage_str)
                            weights[ticker] = percentage
                
                # Метод 3: Поиск в тексте формата "TICKER: percentage%"
                if not weights:
                    text_pattern = r'([A-Z]{1,5})[\s\-:]+(\d+\.?\d*)%'
                    text_matches = re.findall(text_pattern, text)
                    
                    if text_matches:
                        logger.info(f"Found {len(text_matches)} weights in text format")
                        for ticker, percentage_str in text_matches:
                            percentage = float(percentage_str)
                            weights[ticker] = percentage
                
                # Метод 4: Поиск JSON-подобных структур с весами
                if not weights:
                    # Ищем паттерны вида "TICKER": 12.34
                    json_pattern = r'"([A-Z]{1,5})"[\s]*:[\s]*(\d+\.?\d*)'
                    json_matches = re.findall(json_pattern, text)
                    
                    if json_matches:
                        logger.info(f"Found {len(json_matches)} weights in JSON format")
                        for ticker, percentage_str in json_matches:
                            percentage = float(percentage_str)
                            weights[ticker] = percentage
                
                logger.info(f"Extracted weights: {weights}")
                return weights
                
            except Exception as e:
                logger.error(f"Error extracting weights from text: {e}")
                return {}
        
        def _extract_portfolio_metrics_from_text(text: str) -> Dict[str, float]:
            """Извлекает метрики портфеля (доходность, риск, Шарп) из текста ответа модели."""
            metrics = {}
            
            try:
                import re
                
                # Поиск различных вариантов записи метрик
                patterns = [
                    # Ожидаемая доходность
                    (r'[Оо]жидаемая\s+доходность.*?(\d+\.?\d*)%', 'expected_return'),
                    (r'[Дд]оходность.*?(\d+\.?\d*)%', 'expected_return'),
                    (r'Expected\s+[Rr]eturn.*?(\d+\.?\d*)%', 'expected_return'),
                    
                    # Риск (стандартное отклонение)
                    (r'[Рр]иск.*?(\d+\.?\d*)%', 'risk'),
                    (r'[Сс]тандартное\s+отклонение.*?(\d+\.?\d*)%', 'risk'),
                    (r'Risk.*?(\d+\.?\d*)%', 'risk'),
                    (r'Standard\s+[Dd]eviation.*?(\d+\.?\d*)%', 'risk'),
                    
                    # Коэффициент Шарпа - улучшенные паттерны
                    (r'[Кк]оэффициент\s+[Шш]арпа[:\s]*(\d+\.?\d*)', 'sharpe_ratio'),
                    (r'Sharpe[:\s]*(\d+\.?\d*)', 'sharpe_ratio'),
                    (r'[Шш]арп[:\s]*(\d+\.?\d*)', 'sharpe_ratio'),
                    # Добавляем поиск в строке вида "- Коэффициент Шарпа: 1.81"
                    (r'-\s*[Кк]оэффициент\s+[Шш]арпа[:\s]*(\d+\.?\d*)', 'sharpe_ratio'),
                    # Поиск после двоеточия
                    (r'[Шш]арпа[:\s]+(\d+\.?\d*)', 'sharpe_ratio'),
                ]
                
                for pattern, metric_name in patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    if matches:
                        try:
                            # Берем последнее найденное значение (наиболее релевантное)
                            value = float(matches[-1])
                            metrics[metric_name] = value
                            logger.debug(f"Found {metric_name}: {value} using pattern: {pattern}")
                        except ValueError:
                            continue
                
                logger.info(f"Extracted portfolio metrics: {metrics}")
                return metrics
                
            except Exception as e:
                logger.error(f"Error extracting portfolio metrics from text: {e}")
                return {}
        
        def _find_portfolio_info_in_history() -> Dict[str, Any]:
            """Ищет информацию о портфеле в истории диалога пользователя."""
            portfolio_info = {}
            
            try:
                # Получаем историю диалога
                dialog_memory = state.get('dialog_memory', [])
                
                # Ищем в истории диалога информацию о портфеле
                for msg in reversed(dialog_memory):
                    if msg.get("role") == "assistant":
                        content = msg.get("content", "")
                        
                        # Извлекаем веса если их еще нет
                        if not portfolio_info.get('weights'):
                            weights = _extract_weights_from_text(content)
                            if weights:
                                portfolio_info['weights'] = weights
                                logger.info(f"Found portfolio weights in history: {len(weights)} tickers")
                        
                        # Извлекаем метрики портфеля
                        if not portfolio_info.get('metrics'):
                            metrics = _extract_portfolio_metrics_from_text(content)
                            if metrics:
                                portfolio_info['metrics'] = metrics
                                logger.info(f"Found portfolio metrics in history: {list(metrics.keys())}")
                        
                        # Если нашли и веса и метрики, можем остановиться
                        if portfolio_info.get('weights') and portfolio_info.get('metrics'):
                            break
                
                return portfolio_info
                
            except Exception as e:
                logger.error(f"Error finding portfolio info in history: {e}")
                return {}
        
        for turn in range(max_turns):
            # Вызываем модель OpenAI
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Используем доступную модель
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            
            # Добавляем сообщение от ассистента в историю
            messages.append({"role": "assistant", "content": response_message.content or "", "tool_calls": response_message.tool_calls or []})
            
            # Проверяем, запрасил ли ассистент использование инструмента
            if response_message.tool_calls:
                # Для каждого вызова инструмента
                for tool_call in response_message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    
                    # Выполняем запрошенный инструмент
                    tool_result = None
                    
                    if tool_name == "get_forecast":
                        tool_result = get_forecast(tool_args["ticker"])
                    elif tool_name == "optimize_portfolio":
                        risk_aversion = tool_args.get("risk_aversion", 1.0)
                        method = tool_args.get("method", "hrp")
                        target_return = tool_args.get("target_return")
                        tool_result = optimize_portfolio(tool_args["tickers"], risk_aversion, method, target_return)
                    elif tool_name == "analyze_sentiment":
                        window_days = tool_args.get("window_days", 7)
                        tool_result = analyze_sentiment(tool_args["ticker"], window_days)
                    elif tool_name == "adjust_scenario":
                        # Проверяем наличие необходимых аргументов
                        if "tickers" not in tool_args:
                            logger.error("Tool 'adjust_scenario' called without 'tickers' parameter")
                            tool_result = {
                                "error": "Отсутствует параметр 'tickers'",
                                "snapshot_id": None
                            }
                        elif "adjustments" not in tool_args and "delta" not in tool_args:
                            logger.error("Tool 'adjust_scenario' called without 'adjustments' parameter")
                            # Проверяем другие возможные форматы аргументов
                            if "ticker" in tool_args and "delta_percent" in tool_args:
                                # Формат для одного тикера
                                ticker = tool_args["ticker"]
                                delta = tool_args["delta_percent"]
                                adjustments = {ticker: delta}
                                tool_result = adjust_scenario([ticker], adjustments)
                            else:
                                tool_result = {
                                    "error": "Отсутствуют параметры 'adjustments' или 'delta'",
                                    "snapshot_id": None
                                }
                        else:
                            # Стандартный формат аргументов
                            adjustments = tool_args.get("adjustments", {})
                            if "delta" in tool_args and "ticker" in tool_args:
                                # Альтернативный формат для одного тикера
                                ticker = tool_args["ticker"]
                                delta = tool_args["delta"]
                                adjustments = {ticker: delta}
                                
                            tool_result = adjust_scenario(tool_args["tickers"], adjustments)
                    elif tool_name == "plot_portfolio":
                        # Проверка на наличие ключа 'weights' в аргументах
                        if "weights" not in tool_args:
                            logger.warning("Tool 'plot_portfolio' called without 'weights' parameter")
                            empty_result = {"image_path": None, "status": "error", "error": "Отсутствует параметр 'weights'"}
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "content": json.dumps(empty_result)
                            })
                            continue
                        
                        weights = tool_args["weights"]
                        if not isinstance(weights, dict) or not weights:
                            logger.warning(f"Tool 'plot_portfolio' called with invalid weights: {weights}")
                            weights = {"Ошибка": 1.0}
                        
                        img_path = plot_portfolio(weights)
                        image_paths.append(img_path)
                        tool_result = {"image_path": img_path, "status": "success"}
                    elif tool_name == "analyze_performance":
                        # Проверка на наличие ключа 'weights' в аргументах
                        if "weights" not in tool_args:
                            logger.warning("Tool 'analyze_performance' called without 'weights' parameter")
                            tool_result = {"error": "Отсутствует параметр 'weights'"}
                        else:
                            weights = tool_args["weights"]
                            start_date = tool_args.get("start_date")
                            end_date = tool_args.get("end_date")
                            tool_result = analyze_performance(weights, start_date, end_date)
                    elif tool_name == "get_index_composition":
                        index_name = tool_args["index_name"]
                        tool_result = get_index_composition(index_name)
                    elif tool_name == "analyze_risks":
                        tickers = tool_args["tickers"]
                        weights = tool_args.get("weights")
                        confidence_level = tool_args.get("confidence_level", 0.95)
                        tool_result = analyze_risks(tickers, weights, confidence_level)
                    elif tool_name == "build_efficient_frontier":
                        tickers = tool_args.get("tickers")
                        sector = tool_args.get("sector")
                        num_portfolios = tool_args.get("num_portfolios", 100)
                        tool_result = build_efficient_frontier(tickers, sector, num_portfolios)
                    elif tool_name == "analyze_correlations":
                        tickers = tool_args["tickers"]
                        method = tool_args.get("method", "pearson")
                        rolling_window = tool_args.get("rolling_window")
                        tool_result = analyze_correlations(tickers, method, rolling_window)
                    elif tool_name == "update_portfolio":
                        weights = tool_args.get("weights")  # Используем .get() вместо прямого доступа
                        budget = tool_args.get("budget", budget)
                        tool_result = update_portfolio(weights, budget)
                    elif tool_name == "get_portfolio_metrics":
                        tool_result = get_portfolio_metrics()
                    
                    # Добавляем результат инструмента в историю
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(tool_result)
                    })
            else:
                # Если модель не запрашивает инструмент, то это финальный ответ
                response_text = response_message.content or ""
                break
        
        # Если после всех итераций не получили окончательный ответ, используем последний
        if not response_text and response_message.content:
            response_text = response_message.content
        
        # Если у нас по-прежнему нет ответа, сгенерируем сообщение об ошибке
        if not response_text:
            response_text = "Не удалось сформировать ответ на ваш запрос. Пожалуйста, уточните свой вопрос."
        
        return response_text, image_paths
        
    except Exception as e:
        logger.error(f"Error in portfolio manager: {str(e)}", exc_info=True)
        return f"Произошла ошибка при обработке запроса: {str(e)}", []

async def build_snapshot() -> str:
    """
    Асинхронно запускает билд нового снапшота с реальными рыночными данными.
    
    Returns:
        ID нового снапшота или сообщение об ошибке
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            _executor, _build_snapshot_sync
        )
    except Exception as e:
        logger.error(f"Error building snapshot: {str(e)}")
        return f"Ошибка при обновлении снапшота: {str(e)}"

def _build_snapshot_sync() -> str:
    """
    Синхронная версия билда снапшота с реальными рыночными данными.
    
    Returns:
        ID нового снапшота
    """
    try:
        # Получаем список доступных тикеров из предобученных моделей
        available_tickers = get_available_tickers()
        
        if not available_tickers:
            logger.warning("Не найдены доступные модели для тикеров")
            return "Ошибка: не найдены модели для тикеров. Убедитесь, что директория с моделями (models/) содержит необходимые файлы."
        
        # Используем только доступные тикеры для создания снапшота
        tickers = available_tickers
        
        logger.info(f"Building new snapshot with {len(tickers)} tickers")
        
        # Создаем метаданные снапшота
        snapshot_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
        meta = SnapshotMeta(
            snapshot_id=snapshot_id,
            timestamp=datetime.now(timezone.utc),
            tickers=tickers,
            description="Live market snapshot with quarterly forecasts",
            source="yfinance",
            properties={"horizon_days": 90}  # 3 месяца = 90 дней
        )
        
        # Получаем исторические данные для всех тикеров
        end_date = datetime.now(timezone.utc)
        start_date = end_date.replace(tzinfo=None) - timedelta(days=3*365)  # 3 года истории
        
        # Скачиваем исторические данные для всех тикеров
        logger.info(f"Downloading historical data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        # Инициализируем словари для ожидаемой доходности и ковариации
        mu = {}
        sigma = {ticker: {} for ticker in tickers}
        market_caps = {}
        prices = {}
        
        # Обрабатываем каждый тикер отдельно для большей надежности
        all_returns = {}
        
        for ticker in tickers:
            try:
                # Загружаем данные для отдельного тикера
                # С версии 0.2.28 yfinance изменил формат данных и auto_adjust=True по умолчанию
                ticker_data = yf.download(
                    ticker, 
                    start=start_date.strftime("%Y-%m-%d"), 
                    end=end_date.strftime("%Y-%m-%d"),
                    progress=False,
                    auto_adjust=True  # С версии 0.2.28 это значение True по умолчанию
                )
                
                # Пропускаем пустые данные
                if ticker_data.empty:
                    logger.warning(f"No data for {ticker}, skipping")
                    continue
                
                # Получаем данные о ценах закрытия
                # В новых версиях yfinance с auto_adjust=True возвращается только 'Close' вместо 'Adj Close'
                close_column = 'Close'
                
                # Проверяем формат данных - обычный DataFrame или MultiIndex 
                if isinstance(ticker_data.columns, pd.MultiIndex):
                    # Обрабатываем MultiIndex формат (новая версия yfinance)
                    # Структура: ('Price', 'Ticker') - например: ('Close', 'AAPL')
                    try:
                        close_prices = ticker_data.xs('Close', level=0, axis=1)
                        # Если это Series (для одного тикера), преобразуем в DataFrame
                        if isinstance(close_prices, pd.Series):
                            close_prices = pd.DataFrame(close_prices)
                        logger.debug(f"Using MultiIndex format for {ticker}")
                    except Exception as e:
                        logger.error(f"Error accessing MultiIndex data for {ticker}: {e}")
                        continue
                else:
                    # Обрабатываем обычный DataFrame (старая версия или одиночный тикер)
                    # Проверяем наличие колонок
                    if close_column not in ticker_data.columns:
                        # Пробуем альтернативную колонку
                        alternative_close = 'Adj Close' if 'Adj Close' in ticker_data.columns else None
                        if alternative_close:
                            close_column = alternative_close
                        else:
                            logger.warning(f"No price column found for {ticker}, skipping")
                            continue
                    
                    close_prices = ticker_data[close_column]
                    logger.debug(f"Using standard format with column {close_column} for {ticker}")
                
                # Получаем ежедневные логарифмические доходности
                log_returns = np.log(close_prices / close_prices.shift(1)).dropna()
                
                # Сохраняем для последующего расчета ковариации
                all_returns[ticker] = log_returns
                
                # Рассчитываем историческую квартальную доходность и применяем коэффициент 8.0
                quarterly_returns = log_returns.resample('63D').sum()
                mean_value = quarterly_returns.mean()
                
                # Безопасно получаем значение: для Series или DataFrame
                if hasattr(mean_value, 'iloc'):
                    historical_mu = float(mean_value.iloc[0])
                elif isinstance(mean_value, pd.Series):
                    historical_mu = float(mean_value.values[0])  
                else:
                    historical_mu = float(mean_value)
                
                mu_value = historical_mu * 8.0
                logger.info(f"Enhanced forecast for {ticker}: historical={historical_mu:.4f}, enhanced={mu_value:.4f}")
                    
                mu[ticker] = mu_value
                
                # Записываем текущую цену
                # Безопасно получаем последнее значение
                try:
                    if isinstance(close_prices, pd.DataFrame):
                        close_value = close_prices.iloc[-1, 0]
                    elif isinstance(close_prices, pd.Series):
                        close_value = close_prices.iloc[-1]
                    else:
                        close_value = float(ticker_data[close_column].iloc[-1])
                        
                    prices[ticker] = float(close_value)
                    logger.debug(f"Price for {ticker}: ${prices[ticker]:.2f}")
                except Exception as price_error:
                    logger.warning(f"Error getting price for {ticker}: {price_error}")
                    # Ставим цену по умолчанию
                    prices[ticker] = 100.0
                
                # Получаем рыночную капитализацию, если это возможно
                try:
                    ticker_info = yf.Ticker(ticker).info
                    market_cap = ticker_info.get('marketCap')
                    if market_cap:
                        market_caps[ticker] = float(market_cap)
                except Exception as e:
                    logger.warning(f"Failed to get market cap for {ticker}: {e}")
                
                logger.info(f"Processed {ticker}: mu={mu[ticker]:.4f}, price=${prices.get(ticker, 0):.2f}")
                
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                # Пропускаем этот тикер и продолжаем с остальными
        
        # Фильтруем список тикеров только до тех, для которых есть данные
        valid_tickers = list(mu.keys())
        meta.tickers = valid_tickers
        
        # Рассчитываем ковариационную матрицу (только для тикеров с данными)
        if all_returns:
            # Здесь все_returns - словарь {ticker: Series}, где Series - временные ряды с разными индексами
            # Создаем общий индекс для всех рядов
            common_index = pd.DatetimeIndex([])
            for ticker, returns in all_returns.items():
                common_index = common_index.union(returns.index)
            
            # Теперь создаем DataFrame с общим индексом и заполняем его доходностями
            returns_df = pd.DataFrame(index=common_index)
            for ticker, returns in all_returns.items():
                returns_df[ticker] = returns
            
            # Заполняем ковариационную матрицу
            for i in valid_tickers:
                for j in valid_tickers:
                    if i in returns_df.columns and j in returns_df.columns:
                        # Рассчитываем квартальную ковариацию (умножаем дневную на 63)
                        cov_value = returns_df[i].cov(returns_df[j]) * 63
                        sigma[i][j] = float(cov_value)
        
        # Создаем снапшот
        snapshot = MarketSnapshot(
            meta=meta,
            mu=mu,
            sigma=sigma,
            raw_features_path=None,
            market_caps=market_caps,
            prices=prices
        )
        
        # Сохраняем снапшот
        registry = SnapshotRegistry()
        snapshot_id = registry.save(snapshot)
        
        # АВТОМАТИЧЕСКИ ОБНОВЛЯЕМ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ НА НОВЫЙ СНАПШОТ
        try:
            from .handlers import update_all_users_snapshot_id
            # Вызываем синхронную версию обновления пользователей
            updated_count, _ = _update_all_users_snapshot_id_sync(snapshot_id)
            logger.info(f"Automatically updated {updated_count} users to new snapshot {snapshot_id}")
        except Exception as update_error:
            logger.warning(f"Failed to auto-update users for new snapshot {snapshot_id}: {update_error}")
            # Продолжаем выполнение, так как снапшот уже создан
        
        logger.info(f"Created new snapshot {snapshot_id} with {len(valid_tickers)} tickers")
        return f"Создан новый снапшот: {snapshot_id} ({len(valid_tickers)} тикеров)"
    
    except Exception as e:
        logger.error(f"Error building snapshot: {e}", exc_info=True)
        return f"Ошибка при создании снапшота: {str(e)}"

async def get_latest_snapshot_info() -> Dict[str, Any]:
    """
    Асинхронно получает информацию о последнем снапшоте.
    
    Returns:
        Словарь с информацией о последнем снапшоте
    """
    try:
        return await asyncio.get_event_loop().run_in_executor(
            _executor, _get_latest_snapshot_info_sync
        )
    except Exception as e:
        logger.error(f"Error getting snapshot info: {str(e)}")
        return {"error": str(e)}

def _get_latest_snapshot_info_sync() -> Dict[str, Any]:
    """
    Синхронная версия получения информации о последнем снапшоте.
    
    Returns:
        Словарь с информацией о последнем снапшоте
    """
    try:
        registry = SnapshotRegistry()
        latest_snapshot = registry.latest()
        
        if latest_snapshot:
            # Получаем ID из соответствующего поля (snapshot_id или id)
            snapshot_id = getattr(latest_snapshot.meta, "snapshot_id", None) or getattr(latest_snapshot.meta, "id", None)
            
            # Получаем timestamp из соответствующего поля (timestamp или created_at)
            timestamp = getattr(latest_snapshot.meta, "timestamp", None) or getattr(latest_snapshot.meta, "created_at", None)
            
            # Получаем список тикеров из соответствующего поля (tickers или asset_universe)
            tickers = getattr(latest_snapshot.meta, "tickers", None) or getattr(latest_snapshot.meta, "asset_universe", None)
            
            return {
                "snapshot_id": snapshot_id,
                "timestamp": timestamp.isoformat() if timestamp else None,
                "tickers": tickers,
                "error": None
            }
        else:
            return {
                "snapshot_id": None,
                "timestamp": None,
                "tickers": None,
                "error": "Не удалось получить снапшот"
            }
    except Exception as e:
        logger.error(f"Error getting latest snapshot info: {e}", exc_info=True)
        return {
            "snapshot_id": None,
            "timestamp": None,
            "tickers": None,
            "error": f"Ошибка при получении информации о снапшоте: {str(e)}"
        } 