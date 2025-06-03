import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, ContextTypes

from .config import DISCLAIMER, STREAMLIT_URL
from .state import (
    get_user_state,
    save_user_state,
    update_dialog_memory,
    reset_user_state,
    update_risk_profile,
    update_budget,
    update_positions,
    update_snapshot_id,
    redis_client,
    USER_STATE_PREFIX,
    save_portfolio_snapshot,
    get_portfolio_history
)
from .reply import (
    send_markdown,
    send_typing_action,
    send_portfolio_response
)
from .agent_integration import (
    run_portfolio_manager,
    build_snapshot,
    get_latest_snapshot_info,
    get_available_tickers
)
from ..market_snapshot.registry import SnapshotRegistry

logger = logging.getLogger(__name__)

# Справочная информация
START_MESSAGE = """
🤖 *Добро пожаловать в AI Portfolio Assistant!*

Я ваш персональный помощник для управления инвестиционным портфелем. Использую передовые технологии машинного обучения для анализа рынка и оптимизации инвестиций.

🎯 *Что я умею:*
• 📊 Анализировать более 60 финансовых активов
• ⚡ Создавать оптимальные портфели (HRP, Mean-Variance)
• 🔮 Прогнозировать доходность на 3 месяца вперед
• 📈 Анализировать производительность и риски
• 🎪 Моделировать различные сценарии
• 📱 Интегрироваться с веб-интерфейсом
• 💬 Общаться на естественном языке
• 💡 Учитывать и анализировать новосной сентимент

🚀 *Быстрый старт:*
/streamlit - Открыть веб-интерфейс с графиками
/help - Все команды и возможности
/risk moderate - Установить ваш риск-профиль
/budget 10000 - Указать инвестиционный бюджет

💡 *Пример запроса:*
"Создай портфель из AAPL, MSFT, GOOGL на $50,000"

🌐 *Веб-интерфейс:* Используйте `/streamlit` для получения ссылки на полнофункциональный интерфейс с интерактивными графиками!
"""

HELP_MESSAGE = """
📖 *СПРАВОЧНИК AI PORTFOLIO ASSISTANT*

═══════════════════════════

🎯 *ОСНОВНЫЕ КОМАНДЫ*

🏠 `/start` - Приветствие и быстрый старт
❓ `/help` - Эта подробная справка  
🌐 `/streamlit` - Ссылка на веб-интерфейс с графиками
🔄 `/reset` - Сбросить все настройки и контекст

═══════════════════════════

⚙️ *ПЕРСОНАЛЬНЫЕ НАСТРОЙКИ*

🎲 `/risk` `conservative/moderate/aggressive`
   Установить ваш профиль риска

💰 `/budget` `50000`
   Указать инвестиционный бюджет (в USD)

📊 `/positions` `{"AAPL": 100, "MSFT": 50}`
   Задать текущие позиции в JSON формате

═══════════════════════════

📈 *АНАЛИЗ ДАННЫХ*

📸 `/snapshot` - Информация о текущих рыночных данных
🔄 `/update` - Обновить снапшот с реальными данными
🏷️ `/tickers` - Показать все доступные тикеры (~60)

═══════════════════════════

🎯 *ПОРТФЕЛЬНЫЙ АНАЛИЗ*

✅ `/accept` `[название]` - Зафиксировать текущий портфель
📊 `/performance` - Сравнить изменения портфеля во времени

═══════════════════════════

💬 *ПРИМЕРЫ ЗАПРОСОВ*

• "Создай консервативный портфель из топ-10 S&P 500"
• "Оптимизируй мой портфель под 15% годовых"
• "Проанализируй риски портфеля с Tesla и Apple" 
• "Покажи эффективную границу для технологических акций"
• "Сделай сценарий с ростом NVDA на 20%"
• "Какова корреляция между BTC и золотом?"

═══════════════════════════

🔄 *БЫСТРЫЕ ДЕЙСТВИЯ*

📝 "Обнови позиции" - применить последний портфель
⚡ "Применить портфель" - использовать созданные веса
🎯 "Ребалансировка" - пересчитать оптимальное распределение

═══════════════════════════

🌟 *ПРОДВИНУТЫЕ ВОЗМОЖНОСТИ*

🤖 **AI-анализ**: Используются модели CatBoost для прогнозирования
📊 **Методы оптимизации**: HRP, Mean-Variance, Risk Parity
⏰ **Горизонт прогнозов**: 3 месяца (квартальные)
📈 **Метрики**: Коэффициент Шарпа, Alpha, Beta, VaR
🌐 **Веб-интерфейс**: Полнофункциональный Streamlit с графиками

═══════════════════════════

💡 *СОВЕТЫ*

• Начните с команды `/streamlit` для визуального интерфейса
• Установите риск-профиль и бюджет для персонализации
• Используйте `/tickers` чтобы узнать доступные активы
• Фиксируйте портфели через `/accept` для отслеживания
• Команда `/performance` покажет изменения во времени

🎉 *Удачных инвестиций!*
"""

def _extract_portfolio_from_text(text: str, user_budget: float = 10000.0, snapshot_prices: Dict[str, float] = None) -> Dict[str, float]:
    """
    Извлекает информацию о портфеле (тикеры и веса) из текста ответа модели и
    конвертирует проценты в реальное количество акций на основе бюджета и цен.
    
    Args:
        text: Текст ответа модели содержащий информацию о портфеле
        user_budget: Бюджет пользователя в USD
        snapshot_prices: Словарь с текущими ценами акций {ticker: price}
        
    Returns:
        Словарь {ticker: количество_акций} с позициями портфеля
    """
    portfolio_data = {}
    
    try:
        # Метод 1: Поиск таблицы в Markdown формате
        # Ищем строки вида: | TICKER | Company Name | 6.55% |
        table_pattern = r'\|\s*([A-Z]{1,5})\s*\|[^|]*\|\s*(\d+\.?\d*)%?\s*\|'
        table_matches = re.findall(table_pattern, text)
        
        if table_matches:
            logger.info(f"Found {len(table_matches)} tickers in table format")
            for ticker, percentage_str in table_matches:
                percentage = float(percentage_str)
                
                # Вычисляем сумму для этого актива
                allocation_amount = user_budget * (percentage / 100.0)
                
                # Получаем цену акции
                if snapshot_prices and ticker in snapshot_prices:
                    stock_price = snapshot_prices[ticker]
                else:
                    # Если цены нет, используем базовую цену $100
                    stock_price = 100.0
                    logger.warning(f"No price found for {ticker}, using default $100")
                
                # Вычисляем количество акций
                shares_count = allocation_amount / stock_price
                portfolio_data[ticker] = shares_count
                
                logger.info(f"{ticker}: {percentage}% of ${user_budget} = ${allocation_amount:.2f} / ${stock_price:.2f} = {shares_count:.4f} shares")
        
        # Метод 2: Поиск в тексте формата "TICKER: percentage%"
        if not portfolio_data:
            text_pattern = r'([A-Z]{1,5})[\s\-:]+(\d+\.?\d*)%'
            text_matches = re.findall(text_pattern, text)
            
            if text_matches:
                logger.info(f"Found {len(text_matches)} tickers in text format")
                for ticker, percentage_str in text_matches:
                    percentage = float(percentage_str)
                    allocation_amount = user_budget * (percentage / 100.0)
                    
                    if snapshot_prices and ticker in snapshot_prices:
                        stock_price = snapshot_prices[ticker]
                    else:
                        stock_price = 100.0
                        logger.warning(f"No price found for {ticker}, using default $100")
                    
                    shares_count = allocation_amount / stock_price
                    portfolio_data[ticker] = shares_count
        
        # Метод 3: Поиск просто тикеров и присвоение равных весов
        if not portfolio_data:
            # Ищем все тикеры в тексте
            ticker_pattern = r'\b([A-Z]{2,5})\b'
            all_tickers = re.findall(ticker_pattern, text)
            
            # Фильтруем очевидно не-тикеры
            exclude_words = {'USD', 'API', 'CEO', 'ETF', 'IPO', 'NYSE', 'GDP', 'CPI', 'ROI', 'KPI', 'HR', 'IT', 'AI', 'ML', 'UI', 'UX'}
            valid_tickers = [ticker for ticker in set(all_tickers) if ticker not in exclude_words and len(ticker) <= 5]
            
            if valid_tickers:
                logger.info(f"Found {len(valid_tickers)} tickers, assigning equal weights")
                equal_percentage = 100.0 / len(valid_tickers)
                
                for ticker in valid_tickers:
                    allocation_amount = user_budget * (equal_percentage / 100.0)
                    
                    if snapshot_prices and ticker in snapshot_prices:
                        stock_price = snapshot_prices[ticker]
                    else:
                        stock_price = 100.0
                        logger.warning(f"No price found for {ticker}, using default $100")
                    
                    shares_count = allocation_amount / stock_price
                    portfolio_data[ticker] = shares_count
    
    except Exception as e:
        logger.error(f"Error extracting portfolio from text: {e}")
    
    # Проверяем что получили разумные данные
    if portfolio_data:
        # Убираем тикеры с очень маленькими количествами (менее 0.01 акции)
        portfolio_data = {ticker: amount for ticker, amount in portfolio_data.items() if amount >= 0.01}
        
        # Логируем итоговое распределение
        total_value = 0
        for ticker, shares in portfolio_data.items():
            price = snapshot_prices.get(ticker, 100.0) if snapshot_prices else 100.0
            value = shares * price
            total_value += value
            logger.info(f"Final: {ticker} = {shares:.4f} shares × ${price:.2f} = ${value:.2f}")
        
        logger.info(f"Total portfolio value: ${total_value:.2f} (budget: ${user_budget:.2f})")
    
    return portfolio_data

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Создает основную клавиатуру для быстрого доступа к функциям бота.
    
    Returns:
        ReplyKeyboardMarkup с основными командами
    """
    keyboard = [
        [
            KeyboardButton("🌐 Веб-интерфейс"),
            KeyboardButton("📖 Справка")
        ],
        [
            KeyboardButton("🔄 Обновить данные"),
            KeyboardButton("🏷️ Тикеры")
        ],
        [
            KeyboardButton("📊 Статус данных"),
            KeyboardButton("⚙️ Настройки")
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard, 
        resize_keyboard=True, 
        one_time_keyboard=False,
        input_field_placeholder="Введите ваш запрос или выберите команду..."
    )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /start.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} started the bot")
    
    message = START_MESSAGE
    
    # Создаем inline-клавиатуру с быстрыми действиями
    inline_keyboard = [
        [
            InlineKeyboardButton("🌐 Веб-интерфейс", callback_data="action=get_streamlit"),
            InlineKeyboardButton("📖 Справка", callback_data="action=get_help")
        ],
        [
            InlineKeyboardButton("🔄 Обновить данные", callback_data="action=update_snapshot"),
            InlineKeyboardButton("🏷️ Тикеры", callback_data="action=show_tickers")
        ]
    ]
    inline_reply_markup = InlineKeyboardMarkup(inline_keyboard)
    
    # Получаем постоянную клавиатуру
    main_keyboard = get_main_keyboard()
    
    # Отправляем приветственное сообщение с кнопками
    await send_markdown(
        update, 
        context, 
        message, 
        add_disclaimer=False, 
        reply_markup=inline_reply_markup
    )
    
    # Отправляем отдельное сообщение с постоянным меню
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🎯 *Быстрое меню:* Используйте кнопки ниже для быстрого доступа к основным функциям",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard
    )
    
    # Создаем состояние пользователя, если его еще нет
    state = get_user_state(user_id)
    save_user_state(user_id, state)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /help.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested help")
    
    # Создаем клавиатуру с быстрыми действиями
    keyboard = [
        [
            InlineKeyboardButton("🌐 Веб-интерфейс", callback_data="action=get_streamlit"),
            InlineKeyboardButton("🔄 Обновить данные", callback_data="action=update_snapshot")
        ],
        [
            InlineKeyboardButton("🏷️ Показать тикеры", callback_data="action=show_tickers"),
            InlineKeyboardButton("📊 Статус данных", callback_data="action=snapshot_info")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_markdown(update, context, HELP_MESSAGE, add_disclaimer=False, reply_markup=reply_markup)
    
    # Показываем постоянное меню, если его еще нет
    main_keyboard = get_main_keyboard()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="💡 *Подсказка:* Используйте постоянные кнопки ниже для быстрого доступа",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard
    )

async def risk_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /risk.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    args = context.args
    
    if not args or len(args) != 1 or args[0] not in ['conservative', 'moderate', 'aggressive']:
        await send_markdown(
            update, 
            context, 
            "Пожалуйста, укажите риск-профиль: `/risk conservative`, `/risk moderate` или `/risk aggressive`", 
            add_disclaimer=False
        )
        return
    
    risk_profile = args[0].lower()
    logger.info(f"User {user_id} set risk profile to {risk_profile}")
    
    # Обновляем риск-профиль в состоянии пользователя
    update_risk_profile(user_id, risk_profile)
    
    await send_markdown(
        update, 
        context, 
        f"🔄 Ваш риск-профиль установлен на *{risk_profile}*", 
        add_disclaimer=False
    )

async def budget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /budget.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    args = context.args
    
    if not args or len(args) < 1:
        await send_markdown(
            update, 
            context, 
            "Пожалуйста, укажите бюджет в USD, например: `/budget 50000`", 
            add_disclaimer=False
        )
        return
    
    # Проверяем, есть ли подтверждение для больших сумм
    confirm = False
    if len(args) > 1 and args[-1].lower() in ["confirm=yes", "confirm", "yes"]:
        confirm = True
        budget_str = args[0]
    else:
        budget_str = args[0]
    
    try:
        # Очищаем строку от лишних символов
        budget_str = budget_str.replace('$', '').replace(',', '')
        budget = float(budget_str)
        
        # Проверяем на слишком большой бюджет
        if budget > 1000000 and not confirm:
            await send_markdown(
                update, 
                context, 
                f"⚠️ Бюджет превышает 1 000 000 USD. Для подтверждения, пожалуйста, используйте:\n`/budget {budget} confirm=yes`", 
                add_disclaimer=False
            )
            return
        
        logger.info(f"User {user_id} set budget to {budget}")
        
        # Обновляем бюджет в состоянии пользователя
        update_budget(user_id, budget)
        
        await send_markdown(
            update, 
            context, 
            f"💰 Ваш бюджет установлен: *${budget:,.2f}*", 
            add_disclaimer=False
        )
    except ValueError:
        await send_markdown(
            update, 
            context, 
            "❌ Неверный формат бюджета. Пожалуйста, введите число, например: `/budget 50000`", 
            add_disclaimer=False
        )

async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /positions.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Проверяем, есть ли JSON в сообщении
    positions = {}
    json_start = text.find('{')
    
    if json_start != -1:
        # Извлекаем JSON из сообщения
        json_text = text[json_start:]
        try:
            positions = json.loads(json_text)
            logger.info(f"User {user_id} set positions from JSON: {positions}")
        except json.JSONDecodeError:
            await send_markdown(
                update, 
                context, 
                "❌ Не удалось распознать JSON с позициями. Пожалуйста, проверьте формат.", 
                add_disclaimer=False
            )
            return
    else:
        # Если нет JSON, просто отображаем текущие позиции
        state = get_user_state(user_id)
        positions = state.get("positions", {})
        
        if not positions:
            await send_markdown(
                update, 
                context, 
                """
*Ваш портфель пуст*

Чтобы задать текущие позиции, отправьте их в формате JSON:
```
/positions {"AAPL": 10, "MSFT": 5, "BTC": 0.1}
```
Где ключ - тикер актива, значение - количество единиц.
                """,
                add_disclaimer=False
            )
            return
    
    # Если у нас есть позиции (из JSON или из state), обновляем и отображаем
    if positions:
        update_positions(user_id, positions)
        
        positions_text = "*Ваши текущие позиции:*\n\n"
        for ticker, amount in positions.items():
            positions_text += f"• *{ticker}*: {amount}\n"
        
        await send_markdown(
            update, 
            context, 
            positions_text, 
            add_disclaimer=False
        )

async def snapshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /snapshot.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested snapshot info")
    
    # Получаем состояние пользователя
    user_state = get_user_state(user_id)
    
    # Получаем информацию о снапшоте
    await send_typing_action(update, context)
    
    # Сначала проверяем наличие ID снапшота в состоянии пользователя
    user_snapshot_id = user_state.get("last_snapshot_id")
    
    if user_snapshot_id:
        # Если у пользователя есть сохраненный ID снапшота, загружаем его
        registry = SnapshotRegistry()
        user_snapshot = registry.load(user_snapshot_id)
        
        if user_snapshot:
            # Если нашли снапшот по ID из состояния пользователя, используем его
            snapshot_id = user_snapshot_id
            timestamp = user_snapshot.meta.timestamp or user_snapshot.meta.created_at
            tickers = user_snapshot.meta.tickers or user_snapshot.meta.asset_universe
            
            snapshot_info = {
                "snapshot_id": snapshot_id,
                "timestamp": timestamp.isoformat() if timestamp else None,
                "tickers": tickers,
                "error": None
            }
        else:
            # Если не нашли снапшот по ID из состояния пользователя, получаем последний
            snapshot_info = await get_latest_snapshot_info()
            # Обновляем ID снапшота в состоянии пользователя
            if snapshot_info.get("snapshot_id"):
                update_snapshot_id(user_id, snapshot_info["snapshot_id"])
    else:
        # Если у пользователя нет сохраненного ID снапшота, получаем последний
        snapshot_info = await get_latest_snapshot_info()
        # Обновляем ID снапшота в состоянии пользователя
        if snapshot_info.get("snapshot_id"):
            update_snapshot_id(user_id, snapshot_info["snapshot_id"])
    
    if snapshot_info.get("error"):
        await send_markdown(
            update, 
            context, 
            f"❌ {snapshot_info['error']}", 
            add_disclaimer=False
        )
        return
    
    snapshot_id = snapshot_info["snapshot_id"]
    timestamp = snapshot_info["timestamp"]
    tickers = snapshot_info["tickers"]
    
    message = f"""
*Текущий снапшот:* `{snapshot_id}`
*Время создания:* `{timestamp}`
*Количество тикеров:* {len(tickers) if tickers else 0}
    """
    
    # Добавляем несколько тикеров для примера
    if tickers and len(tickers) > 0:
        sample_tickers = tickers[:5]
        message += f"\n*Примеры тикеров:* {', '.join(sample_tickers)}"
        if len(tickers) > 5:
            message += f" и еще {len(tickers) - 5}"
    
    message += "\n\nДля обновления данных используйте команду /update"
    
    await send_markdown(update, context, message, add_disclaimer=False)

async def update_all_users_snapshot_id():
    """
    Обновляет ID последнего снапшота для всех пользователей в базе данных.
    
    Returns:
        Tuple[int, str]: Кортеж с количеством обновленных пользователей и ID установленного снапшота
    """
    try:
        # Получаем последний снапшот
        registry = SnapshotRegistry()
        latest_snapshot = registry.latest()
        
        if not latest_snapshot:
            logger.warning("No snapshots available to update users")
            return (0, "No snapshots available")
        
        snapshot_id = latest_snapshot.meta.id
        logger.info(f"Updating all users to latest snapshot: {snapshot_id}")
        
        # Получаем всех пользователей из Redis
        if not redis_client:
            logger.error("Redis client not available. Can't update users.")
            return (0, f"Redis client not available")
        
        user_keys = redis_client.keys(f"{USER_STATE_PREFIX}*")
        updated_count = 0
        
        for user_key in user_keys:
            try:
                # Получаем ID пользователя из ключа
                user_id_str = user_key.replace(USER_STATE_PREFIX, "")
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

async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /update.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested snapshot update")
    
    # Отправляем сообщение о начале обновления
    await send_markdown(
        update, 
        context, 
        "⏳ Начинаю обновление снапшота...", 
        add_disclaimer=False
    )
    
    # Запускаем обновление снапшота
    await send_typing_action(update, context)
    result = await build_snapshot()
    
    # Проверяем успешность создания снапшота и обновляем ID в состоянии пользователя
    if "Создан новый снапшот:" in result:
        # Извлекаем ID снапшота из результата
        snapshot_id_match = re.search(r"Создан новый снапшот: (\S+)", result)
        if snapshot_id_match:
            new_snapshot_id = snapshot_id_match.group(1)
            # Обновляем ID снапшота в состоянии пользователя
            update_snapshot_id(user_id, new_snapshot_id)
            logger.info(f"Updated snapshot_id for user {user_id} to {new_snapshot_id}")
    
    # Отправляем результат
    await send_markdown(
        update, 
        context, 
        f"✅ {result}", 
        add_disclaimer=False
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /reset.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested state reset")
    
    reset_user_state(user_id)
    
    await send_markdown(
        update, 
        context, 
        "🔄 Ваши настройки и история диалога сброшены.", 
        add_disclaimer=False
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик текстовых сообщений.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Обрабатываем нажатия на кнопки постоянного меню
    if message_text == "🌐 Веб-интерфейс":
        await streamlit_command(update, context)
        return
    elif message_text == "📖 Справка":
        await help_command(update, context)
        return
    elif message_text == "🔄 Обновить данные":
        await update_command(update, context)
        return
    elif message_text == "🏷️ Тикеры":
        await tickers_command(update, context)
        return
    elif message_text == "📊 Статус данных":
        await snapshot_command(update, context)
        return
    elif message_text == "⚙️ Настройки":
        # Отправляем меню настроек
        settings_text = """
⚙️ *НАСТРОЙКИ ПРОФИЛЯ*

Выберите параметр для изменения:

🎲 *Риск-профиль:* `/risk conservative/moderate/aggressive`
💰 *Бюджет:* `/budget 50000`
📊 *Позиции:* `/positions {"AAPL": 100, "MSFT": 50}`
🔄 *Сброс:* `/reset` - сбросить все настройки

*Текущие настройки:*
"""
        state = get_user_state(user_id)
        settings_text += f"• Риск-профиль: *{state.get('risk_profile', 'не установлен')}*\n"
        settings_text += f"• Бюджет: *${state.get('budget', 0):,.2f}*\n"
        positions = state.get('positions', {})
        if positions:
            settings_text += f"• Позиций в портфеле: *{len(positions)}*\n"
        else:
            settings_text += "• Позиций в портфеле: *нет*\n"
        
        await send_markdown(update, context, settings_text, add_disclaimer=False)
        return
    
    # Расширенная проверка на запрос обновления позиций
    update_patterns = [
        r"^(обнови|обновить|измени|изменить)\s+(позиции|список|портфель)$",
        r"(обнови|обновить|измени|изменить)\s+(позиции|список|портфель).*(в\s+соответствии|согласно|по|на\s+основе).*(портфел|создан)",
        r"(применить?|применить|использовать|установить).*(портфель|позиции|веса)"
    ]
    
    update_match = None
    for pattern in update_patterns:
        update_match = re.search(pattern, message_text.lower())
        if update_match:
            break
    
    if update_match:
        logger.info(f"User {user_id} requested portfolio update: '{message_text}'")
        
        # Получаем последний ответ ассистента из истории диалога
        state = get_user_state(user_id)
        dialog_memory = state.get("dialog_memory", [])
        
        portfolio_suggestion = None
        for msg in reversed(dialog_memory):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                # Проверяем, содержит ли ответ информацию о портфеле
                if any(keyword in content.lower() for keyword in ["портфел", "позици", "тикер", "доля", "вес"]):
                    portfolio_suggestion = content
                    break
        
        if not portfolio_suggestion:
            await send_markdown(
                update, 
                context, 
                "❌ Не найдено недавних предложений по портфелю. Пожалуйста, сначала попросите создать портфель.", 
                add_disclaimer=False
            )
            return
        
        # Извлекаем тикеры и веса из таблицы или текста
        # Получаем бюджет пользователя и цены из снапшота
        user_budget = state.get("budget", 10000.0)
        
        # Получаем цены из текущего снапшота
        snapshot_prices = {}
        try:
            from ..market_snapshot.registry import SnapshotRegistry
            registry = SnapshotRegistry()
            
            # Получаем ID снапшота пользователя
            snapshot_id = state.get("last_snapshot_id")
            if snapshot_id:
                snapshot = registry.load(snapshot_id)
                if snapshot and hasattr(snapshot, 'prices') and snapshot.prices:
                    snapshot_prices = snapshot.prices
                    logger.info(f"Loaded {len(snapshot_prices)} prices from snapshot {snapshot_id}")
                else:
                    logger.warning(f"No prices found in snapshot {snapshot_id}")
            else:
                logger.warning("No snapshot ID found for user")
                
        except Exception as e:
            logger.error(f"Error loading snapshot prices: {e}")
        
        portfolio_data = _extract_portfolio_from_text(portfolio_suggestion, user_budget, snapshot_prices)
        
        if not portfolio_data:
            await send_markdown(
                update, 
                context, 
                "❌ Не удалось извлечь информацию о портфеле из последнего ответа. Попробуйте указать тикеры явно.", 
                add_disclaimer=False
            )
            return
        
        # Обновляем позиции в состоянии пользователя
        update_positions(user_id, portfolio_data)
        
        # Формируем сообщение об обновлении
        positions_text = "*✅ Портфель успешно обновлен:*\n\n"
        total_value = 0.0
        
        for ticker, shares_count in portfolio_data.items():
            # Получаем цену акции
            stock_price = snapshot_prices.get(ticker, 100.0) if snapshot_prices else 100.0
            position_value = shares_count * stock_price
            total_value += position_value
            
            # Вычисляем процент от общего бюджета
            percentage = (position_value / user_budget) * 100 if user_budget > 0 else 0
            
            positions_text += f"• *{ticker}*: {shares_count:.4f} акций × ${stock_price:.2f} = ${position_value:.2f} ({percentage:.1f}%)\n"
        
        positions_text += f"\n*💰 Общая стоимость портфеля:* ${total_value:.2f}"
        positions_text += f"\n*🎯 Бюджет пользователя:* ${user_budget:.2f}"
        positions_text += f"\n*📊 Использовано бюджета:* {(total_value / user_budget) * 100 if user_budget > 0 else 0:.1f}%"
        
        await send_markdown(
            update, 
            context, 
            positions_text, 
            add_disclaimer=False
        )
        return
    
    # Проверка на запрос обновления позиций с указанными тикерами
    update_positions_pattern = r"(обнови|обновить|измени|изменить|установи|задай).+(позиции|список|портфель)[^а-яА-Я]*(используя|используя тикеры|из|состоящий из|с тикерами)[^а-яА-Я]*([A-Z]{1,5}(,\s*[A-Z]{1,5})*)"
    explicit_match = re.search(update_positions_pattern, message_text.lower())
    
    if explicit_match:
        logger.info(f"User {user_id} requested portfolio update via text command")
        # Извлекаем список тикеров
        tickers_text = explicit_match.group(4).strip()
        tickers = [ticker.strip() for ticker in re.split(r',\s*', tickers_text)]
        
        # Создаем новые позиции
        new_positions = {ticker: 100 for ticker in tickers}
        
        # Обновляем позиции в состоянии пользователя
        update_positions(user_id, new_positions)
        
        positions_text = "*Ваши обновленные позиции:*\n\n"
        for ticker, amount in new_positions.items():
            positions_text += f"• *{ticker}*: {amount}\n"
        
        await send_markdown(
            update, 
            context, 
            positions_text, 
            add_disclaimer=False
        )
        return
    
    # Добавляем сообщение в историю диалога
    update_dialog_memory(user_id, message_text, role="user")
    
    # Получаем состояние пользователя
    state = get_user_state(user_id)
    
    # Отправляем индикатор набора текста
    await send_typing_action(update, context)
    
    # Запускаем агента-менеджера
    response_text, image_paths = await run_portfolio_manager(message_text, state, user_id)
    
    # Добавляем ответ бота в историю диалога
    update_dialog_memory(user_id, response_text, role="assistant")
    
    # Отправляем ответ пользователю
    await send_portfolio_response(update, context, response_text, image_paths)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик нажатий на inline-кнопки.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    query = update.callback_query
    user_id = query.from_user.id
    callback_data = query.data
    
    # Отправляем индикатор загрузки
    await query.answer(text="Обрабатываю...")
    
    if callback_data == "action=get_streamlit":
        # Отправляем информацию о веб-интерфейсе
        await streamlit_command(update, context)
        
    elif callback_data == "action=get_help":
        # Отправляем справку
        await help_command(update, context)
        
    elif callback_data == "action=update_snapshot":
        # Обновляем снапшот
        await update_command(update, context)
        
    elif callback_data == "action=show_tickers":
        # Показываем доступные тикеры
        await tickers_command(update, context)
    
    elif callback_data == "action=snapshot_info":
        # Показываем информацию о снапшоте
        await snapshot_command(update, context)
    
    elif callback_data == "action=reeval":
        # Пересчитываем ответ с тем же текстом
        state = get_user_state(user_id)
        last_message = None
        
        # Ищем последнее сообщение пользователя в истории диалога
        for msg in reversed(state.get("dialog_memory", [])):
            if msg.get("role") == "user":
                last_message = msg.get("content")
                break
        
        if last_message:
            # Отправляем индикатор набора текста
            try:
                await context.bot.send_chat_action(
                    chat_id=query.message.chat_id,
                    action="typing"
                )
            except Exception as e:
                logger.error(f"Error sending typing action: {str(e)}")
            
            # Запускаем агента-менеджера
            response_text, image_paths = await run_portfolio_manager(last_message, state, user_id)
            
            # Обновляем последний ответ бота в истории диалога
            for i in range(len(state.get("dialog_memory", [])) - 1, -1, -1):
                if state["dialog_memory"][i].get("role") == "assistant":
                    state["dialog_memory"][i]["content"] = response_text
                    save_user_state(user_id, state)
                    break
            
            # Отправляем новый ответ
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Пересчитать", callback_data="action=reeval"),
                    InlineKeyboardButton("📈 Показать графики", callback_data="action=plot")
                ],
                [
                    InlineKeyboardButton("♻️ Ребалансировка", callback_data="action=rebalance")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Сначала отправляем текстовый ответ
            full_text = response_text
            if DISCLAIMER not in response_text:
                full_text = f"{response_text}\n\n{DISCLAIMER}"
                
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=full_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                
                # Затем отправляем все изображения, если они есть
                if image_paths:
                    for i, img_path in enumerate(image_paths):
                        caption = f"График {i+1}/{len(image_paths)}" if len(image_paths) > 1 else None
                        with open(img_path, 'rb') as photo:
                            await context.bot.send_photo(
                                chat_id=query.message.chat_id,
                                photo=photo,
                                caption=caption,
                                parse_mode=ParseMode.MARKDOWN if caption else None
                            )
            except Exception as e:
                logger.error(f"Error sending response: {str(e)}")
                try:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"Произошла ошибка при отправке ответа: {str(e)}"
                    )
                except:
                    pass
        else:
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Не найдено предыдущее сообщение для повторной обработки.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Error sending error message: {str(e)}")
    
    elif callback_data == "action=plot":
        # Генерируем и отправляем графики
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="📈 Генерирую графики...",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error sending plot message: {str(e)}")
        
        # TODO: Интегрировать с реальным генератором графиков
        
    elif callback_data == "action=rebalance":
        # Запускаем ребалансировку портфеля
        try:
            await context.bot.send_chat_action(
                chat_id=query.message.chat_id,
                action="typing"
            )
        except Exception as e:
            logger.error(f"Error sending typing action: {str(e)}")
        
        state = get_user_state(user_id)
        
        # Формируем запрос на ребалансировку
        rebalance_text = "Сделай ребалансировку моего портфеля"
        
        # Запускаем агента-менеджера с запросом на ребалансировку
        response_text, image_paths = await run_portfolio_manager(rebalance_text, state, user_id)
        
        # Отправляем результат ребалансировки
        keyboard = [
            [
                InlineKeyboardButton("🔄 Пересчитать", callback_data="action=reeval"),
                InlineKeyboardButton("📈 Показать графики", callback_data="action=plot")
            ],
            [
                InlineKeyboardButton("♻️ Ребалансировка", callback_data="action=rebalance")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Сначала отправляем текстовый ответ
        full_text = response_text
        if DISCLAIMER not in response_text:
            full_text = f"{response_text}\n\n{DISCLAIMER}"
            
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=full_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            # Затем отправляем все изображения, если они есть
            if image_paths:
                for i, img_path in enumerate(image_paths):
                    caption = f"График {i+1}/{len(image_paths)}" if len(image_paths) > 1 else None
                    with open(img_path, 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id,
                            photo=photo,
                            caption=caption,
                            parse_mode=ParseMode.MARKDOWN if caption else None
                        )
        except Exception as e:
            logger.error(f"Error sending rebalance response: {str(e)}")
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"Произошла ошибка при отправке результатов ребалансировки: {str(e)}"
                )
            except:
                pass
        
    else:
        # Неизвестный callback_data
        await query.answer(text="Неизвестная команда")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик ошибок.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    logger.error(f"Update {update} caused error {context.error}")
    
    try:
        if update and update.effective_chat:
            await send_markdown(
                update, 
                context, 
                f"❌ Произошла ошибка при обработке запроса:\n`{str(context.error)}`", 
                add_disclaimer=False
            )
    except Exception as e:
        logger.error(f"Error in error handler: {str(e)}")

async def tickers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /tickers - показывает список всех доступных тикеров.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested available tickers list")
    
    # Отправляем индикатор набора текста
    await send_typing_action(update, context)
    
    # Получаем список доступных тикеров
    available_tickers = get_available_tickers(use_cache=False)  # Принудительно обновляем список
    
    if not available_tickers:
        await send_markdown(
            update, 
            context, 
            "❌ Не удалось найти доступные тикеры. Проверьте наличие моделей в директории models/.", 
            add_disclaimer=False
        )
        return
    
    # Группируем тикеры для лучшей читаемости (по 5 в строке)
    tickers_chunks = []
    for i in range(0, len(available_tickers), 5):
        chunk = available_tickers[i:i+5]
        tickers_chunks.append(", ".join(f"`{ticker}`" for ticker in chunk))
    
    message = f"""
*Доступные тикеры ({len(available_tickers)}):*

{"\n".join(tickers_chunks)}

Вы можете использовать эти тикеры для анализа, прогнозирования и оптимизации портфеля.
"""
    
    await send_markdown(update, context, message, add_disclaimer=False)

async def update_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /updateall для обновления ID снапшота всех пользователей.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested update of all users' snapshots")
    
    # Отправляем сообщение о начале обновления
    await send_markdown(
        update, 
        context, 
        "⏳ Обновляю снапшот для всех пользователей...", 
        add_disclaimer=False
    )
    
    # Запускаем обновление снапшотов для всех пользователей
    await send_typing_action(update, context)
    updated_count, snapshot_id = await update_all_users_snapshot_id()
    
    if updated_count > 0:
        result = f"✅ Обновлено {updated_count} пользователей на снапшот: `{snapshot_id}`"
    else:
        result = f"❌ Не удалось обновить снапшоты: {snapshot_id}"
    
    # Отправляем результат
    await send_markdown(
        update, 
        context, 
        result, 
        add_disclaimer=False
    )

async def accept_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /accept для фиксации текущего портфеля.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested to accept current portfolio")
    
    # Получаем текущие позиции
    state = get_user_state(user_id)
    positions = state.get("positions", {})
    
    if not positions:
        await send_markdown(
            update, 
            context, 
            "❌ Ваш портфель пуст. Нечего фиксировать.", 
            add_disclaimer=False
        )
        return
        
    # Опциональное имя для снимка портфеля
    snapshot_name = None
    if context.args and len(context.args) > 0:
        snapshot_name = " ".join(context.args)
        
    # Сохраняем снимок портфеля
    result = save_portfolio_snapshot(user_id, snapshot_name)
    
    if result:
        await send_markdown(
            update, 
            context, 
            f"✅ Текущий портфель успешно зафиксирован{' как «' + snapshot_name + '»' if snapshot_name else ''}.\n\n"
            "Теперь вы можете отслеживать его производительность с течением времени и запрашивать аналитику командой /performance.",
            add_disclaimer=False
        )
    else:
        await send_markdown(
            update, 
            context, 
            "❌ Не удалось зафиксировать портфель. Пожалуйста, попробуйте позже.",
            add_disclaimer=False
        )

async def performance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /performance для отображения производительности портфеля.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested portfolio performance")
    
    portfolio_history = get_portfolio_history(user_id)
    
    if not portfolio_history:
        await send_markdown(
            update, 
            context, 
            "❌ История портфеля пуста. Используйте команду /accept, чтобы зафиксировать текущий портфель.", 
            add_disclaimer=False
        )
        return
        
    # Для простоты берем первый и последний снимок
    first_snapshot = portfolio_history[0]
    last_snapshot = portfolio_history[-1]
    
    # Формируем текст с результатами
    first_date = datetime.fromisoformat(first_snapshot['timestamp']).strftime('%d.%m.%Y')
    last_date = datetime.fromisoformat(last_snapshot['timestamp']).strftime('%d.%m.%Y')
    
    # Рассчитываем изменения
    change_pct = ((last_snapshot['portfolio_value'] / first_snapshot['portfolio_value']) - 1) * 100
    
    performance_text = f"""
*Сравнение производительности портфеля*

📊 Начальный портфель ({first_snapshot['name']}):
Дата: {first_date}
Стоимость: ${first_snapshot['portfolio_value']:,.2f}

📈 Текущий портфель ({last_snapshot['name']}):
Дата: {last_date}
Стоимость: ${last_snapshot['portfolio_value']:,.2f}

💰 Изменение: {change_pct:.2f}% {'+' if change_pct > 0 else ''}

*Позиции в начальном портфеле:*
"""
    
    for ticker, amount in first_snapshot['positions'].items():
        performance_text += f"• *{ticker}*: {amount}\n"
        
    performance_text += "\n*Позиции в текущем портфеле:*\n"
    
    for ticker, amount in last_snapshot['positions'].items():
        performance_text += f"• *{ticker}*: {amount}\n"
        
    await send_markdown(
        update, 
        context, 
        performance_text, 
        add_disclaimer=True
    )
    
    # TODO: Добавить генерацию графика производительности
    # и отправку его пользователю 

async def force_update_all_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /forceupdate для принудительного обновления всех пользователей на последний снапшот.
    Эта команда полезна после сброса настроек или проблем с синхронизацией.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested forced update of all users to latest snapshot")
    
    # Отправляем сообщение о начале обновления
    await send_markdown(
        update, 
        context, 
        "⏳ Принудительно обновляю всех пользователей на последний снапшот...", 
        add_disclaimer=False
    )
    
    # Запускаем принудительное обновление всех пользователей
    await send_typing_action(update, context)
    
    try:
        # Получаем последний снапшот
        registry = SnapshotRegistry()
        latest_snapshot = registry.latest()
        
        if not latest_snapshot:
            result = "❌ Нет доступных снапшотов для обновления"
        else:
            # Обновляем всех пользователей на последний снапшот
            updated_count, snapshot_id = await update_all_users_snapshot_id()
            
            if updated_count > 0:
                result = f"✅ Принудительно обновлено {updated_count} пользователей на снапшот: `{snapshot_id}`"
                result += f"\n\nТеперь все пользователи используют последний снапшот."
            else:
                result = f"❌ Не удалось обновить пользователей: {snapshot_id}"
    except Exception as e:
        logger.error(f"Error in forced update: {str(e)}")
        result = f"❌ Ошибка при принудительном обновлении: {str(e)}"
    
    # Отправляем результат
    await send_markdown(
        update, 
        context, 
        result, 
        add_disclaimer=False
    )

async def streamlit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /streamlit.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested Streamlit interface link")
    
    message = f"""
🌐 *ВЕБА-ИНТЕРФЕЙС PORTFOLIO ASSISTANT*

═══════════════════════════

🚀 **Прямая ссылка:** {STREAMLIT_URL}

═══════════════════════════

✨ *ВОЗМОЖНОСТИ ВЕБ-ИНТЕРФЕЙСА*

📊 **Интерактивная аналитика:**
• Динамические графики и диаграммы
• Детальные таблицы с данными
• Drag-and-drop интерфейс

⚡ **Расширенная оптимизация:**
• Алгоритмы HRP, Mean-Variance, Risk Parity
• Настройка параметров риска
• Сценарное моделирование

📈 **Углубленный анализ:**
• Историческая производительность
• Корреляционные матрицы
• Эффективная граница портфеля

🔮 **Прогнозирование:**
• 3-месячные прогнозы доходности
• Анализ чувствительности
• Стресс-тестирование портфеля

📱 **Telegram интеграция:**
• Отправка отчетов прямо в чат
• Экспорт в различные форматы
• Синхронизация данных

═══════════════════════════

🛠️ *БЫСТРЫЙ ЗАПУСК*

**Автоматический запуск:**
```
./start.sh          # MacOS/Linux
start.bat           # Windows
python launcher.py  # Универсальный
```

**Ручной запуск:**
```
streamlit run streamlit_app.py --server.port=8501
```

═══════════════════════════

💡 *СОВЕТ:* Если веб-интерфейс не запущен, используйте команды выше. Приложение автоматически откроется в браузере!

🌟 Наслаждайтесь полнофункциональной аналитикой!
"""

    # Создаем клавиатуру с полезными ссылками
    keyboard = [
        [
            InlineKeyboardButton("📖 Справка", callback_data="action=get_help"),
            InlineKeyboardButton("🔄 Обновить данные", callback_data="action=update_snapshot")
        ],
        [
            InlineKeyboardButton("🏷️ Доступные тикеры", callback_data="action=show_tickers")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_markdown(update, context, message, add_disclaimer=False, reply_markup=reply_markup) 