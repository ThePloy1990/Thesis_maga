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

async def run_portfolio_manager(text: str, state: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Асинхронно запускает портфельного агента-менеджера.
    
    Args:
        text: Запрос пользователя
        state: Состояние пользователя
        
    Returns:
        Кортеж из markdown-текста и списка путей к изображениям
    """
    logger.info(f"Running portfolio manager with text: {text[:100]}...")
    
    try:
        # Запускаем выполнение в отдельном потоке, чтобы не блокировать event loop
        return await asyncio.get_event_loop().run_in_executor(
            _executor, _run_portfolio_manager_sync, text, state
        )
    except Exception as e:
        logger.error(f"Error running portfolio manager: {str(e)}")
        return f"Произошла ошибка при обработке запроса: {str(e)}", []

def _run_portfolio_manager_sync(text: str, state: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Синхронная версия запуска портфельного агента с использованием OpenAI API.
    
    Args:
        text: Запрос пользователя
        state: Состояние пользователя
        
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
        
        Доступные тикеры:
        {tickers_display}
        
        ВАЖНО: Ты можешь работать ТОЛЬКО с указанными выше тикерами, для которых есть предобученные модели CatBoost.
        Никогда не предлагай тикеры, которых нет в этом списке. Игнорируй любые запросы пользователя на анализ недоступных тикеров.
        Просто отвечай, что тикер недоступен и лучше будет использовать другие инструменты для большей доходности.
        
        Ты можешь использовать следующие инструменты:
        1. get_forecast - получить прогноз доходности и риска для тикера
        2. optimize_portfolio - оптимизировать портфель по тикерам
        3. analyze_sentiment - анализировать настроения рынка по тикеру
        4. adjust_scenario - создать сценарий с изменением ожидаемой доходности
        5. plot_portfolio - создать график распределения портфеля
        
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
        
        def optimize_portfolio(tickers: List[str], risk_aversion: float = 1.0) -> Dict[str, Any]:
            """Оптимизирует портфель на основе указанных тикеров."""
            logger.info(f"Using optimize_tool for {tickers}")
            
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
                return optimize_tool(tickers=valid_tickers, snapshot_id=correct_snapshot_id, risk_aversion=risk_aversion)
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
                        tool_result = optimize_portfolio(tool_args["tickers"], risk_aversion)
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
            description="Live market snapshot",
            source="yfinance",
            properties={"horizon_days": 30}
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
                
                # Преобразуем в месячные доходности (примерно 21 торговый день)
                monthly_returns = log_returns.resample('21D').sum()
                
                # Рассчитываем ожидаемую месячную доходность (среднее значение)
                mean_value = monthly_returns.mean()
                # Безопасно получаем значение: для Series или DataFrame
                if hasattr(mean_value, 'iloc'):
                    mu_value = float(mean_value.iloc[0])
                elif isinstance(mean_value, pd.Series):
                    mu_value = float(mean_value.values[0])  
                else:
                    mu_value = float(mean_value)
                    
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
                        # Рассчитываем месячную ковариацию (умножаем дневную на 21)
                        cov_value = returns_df[i].cov(returns_df[j]) * 21
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