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
        snapshot_id = state.get('snapshot_id')
        
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
                state['snapshot_id'] = snapshot_id
        
        if latest_snapshot:
            # Получаем данные о снапшоте
            tickers = getattr(latest_snapshot.meta, "tickers", []) or getattr(latest_snapshot.meta, "asset_universe", [])
            timestamp = getattr(latest_snapshot.meta, "timestamp", None) or getattr(latest_snapshot.meta, "created_at", None)
            snapshot_info = f"Снапшот {snapshot_id} от {timestamp.isoformat()}, содержит {len(tickers)} тикеров"
        
        # Формируем базовый контекст для агента
        system_message = f"""
        Ты - ИИ-портфельный ассистент. Ты помогаешь пользователю анализировать и оптимизировать инвестиционный портфель.
        
        Информация о пользователе:
        - Риск-профиль: {risk_profile}
        - Бюджет: ${budget:,.2f}
        - Текущие позиции: {positions}
        
        Доступная информация о рынке:
        - {snapshot_info}
        
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
                                "description": "Тикер акции или ETF (например, AAPL, SPY, BTC-USD)"
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
                                "description": "Список тикеров для включения в портфель"
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
                                "description": "Тикер акции или ETF"
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
                                "description": "Список тикеров для сценария"
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
            return forecast_tool(ticker, snapshot_id)
        
        def optimize_portfolio(tickers: List[str], risk_aversion: float = 1.0) -> Dict[str, Any]:
            """Оптимизирует портфель на основе указанных тикеров."""
            logger.info(f"Using optimize_tool for {tickers}")
            return optimize_tool(snapshot_id, risk_aversion=risk_aversion)
        
        def analyze_sentiment(ticker: str, window_days: int = 7) -> Dict[str, Any]:
            """Анализирует новостной сентимент для указанного тикера."""
            logger.info(f"Using sentiment_tool for {ticker}")
            return sentiment_tool(ticker, window_days=window_days)
        
        def adjust_scenario(tickers: List[str], adjustments: Dict[str, float]) -> Dict[str, Any]:
            """Создает сценарий с указанными корректировками ожидаемой доходности."""
            logger.info(f"Using scenario_adjust_tool with adjustments {adjustments}")
            return scenario_adjust_tool(tickers, adjustments, base_snapshot_id=snapshot_id)
        
        def plot_portfolio(weights: Dict[str, float]) -> str:
            """Создает график распределения портфеля и возвращает путь к изображению."""
            logger.info(f"Creating portfolio plot with weights {weights}")
            
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
                model="gpt-4-turbo",  # Используем доступную модель
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            
            # Добавляем сообщение от ассистента в историю
            messages.append({"role": "assistant", "content": response_message.content or "", "tool_calls": response_message.tool_calls or []})
            
            # Проверяем, запросил ли ассистент использование инструмента
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
                        tool_result = adjust_scenario(tool_args["tickers"], tool_args["adjustments"])
                    elif tool_name == "plot_portfolio":
                        img_path = plot_portfolio(tool_args["weights"])
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
        # Список тикеров для обновления
        # В реальном приложении можно загружать из конфигурации или базы данных
        tickers = [
            # Акции США
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "JPM", "V", "JNJ",
            # ETF
            "SPY", "QQQ", "VTI", "VOO", "VEA", "VWO", "BND", "AGG", 
            # Криптовалюты
            "BTC-USD", "ETH-USD"
        ]
        
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
                ticker_data = yf.download(
                    ticker, 
                    start=start_date.strftime("%Y-%m-%d"), 
                    end=end_date.strftime("%Y-%m-%d"),
                    progress=False,
                    auto_adjust=True
                )
                
                # Пропускаем пустые данные
                if ticker_data.empty:
                    logger.warning(f"No data for {ticker}, skipping")
                    continue
                
                # Проверяем наличие данных о ценах закрытия
                if 'Close' not in ticker_data.columns:
                    logger.warning(f"No 'Close' column for {ticker}, skipping")
                    continue
                
                # Получаем ежедневные логарифмические доходности
                log_returns = np.log(ticker_data['Close'] / ticker_data['Close'].shift(1)).dropna()
                
                # Сохраняем для последующего расчета ковариации
                all_returns[ticker] = log_returns
                
                # Преобразуем в месячные доходности (примерно 21 торговый день)
                monthly_returns = log_returns.resample('21D').sum()
                
                # Рассчитываем ожидаемую месячную доходность (среднее значение)
                mean_value = monthly_returns.mean()
                mu[ticker] = float(mean_value.iloc[0]) if hasattr(mean_value, 'iloc') else float(mean_value)
                
                # Записываем текущую цену
                close_value = ticker_data['Close'].iloc[-1]
                prices[ticker] = float(close_value.iloc[0]) if hasattr(close_value, 'iloc') else float(close_value)
                
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