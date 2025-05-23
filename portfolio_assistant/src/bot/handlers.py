import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, ContextTypes

from .config import DISCLAIMER
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
*Привет! Я ваш AI-портфельный ассистент* 🚀

Я помогу вам с:
• Построением оптимального инвестиционного портфеля
• Анализом финансовых активов
• Сценарным моделированием

*Основные команды:*
/help - Подробная справка
/risk - Установить ваш риск-профиль
/budget - Установить бюджет
/positions - Задать текущие позиции
/snapshot - Информация о текущих данных
/update - Обновить рыночные данные

*Примеры запросов:*
"Собери портфель из AAPL, MSFT и BTC на 1 месяц"
"Что думаешь про Tesla?"
"Поменяй прогноз по BTC на +5%"
"""

HELP_MESSAGE = """
*Список команд:*

📋 *Основные команды:*
/start - Начало работы
/help - Эта справка
/reset - Сбросить настройки и контекст

⚙️ *Настройки:*
/risk `conservative/moderate/aggressive` - Установить риск-профиль
/budget `10000` - Установить бюджет в USD (до 1 млн)
/positions - Задать текущие позиции (можно с JSON)

📊 *Снапшоты:*
/snapshot - Информация о текущем снапшоте
/update - Обновить данные о рынке
/tickers - Показать список всех доступных тикеров

📈 *Портфель:*
/accept [имя] - Зафиксировать текущий портфель для отслеживания
/performance - Показать изменение портфеля со времени первой фиксации

*Примеры запросов:*
• "Собери портфель из AAPL, MSFT и BTC"
• "Расскажи о перспективах Tesla"
• "Сделай сценарий с ростом AAPL на 10%"
• "Какой коэффициент Шарпа у моего портфеля?"
• "Покажи эффективную границу для моих активов"
• "Обнови позиции" - применяет последнее предложение по портфелю
"""

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /start.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    user_id = update.effective_user.id
    logger.info(f"User {user_id} started the bot")
    
    # Получаем информацию о снапшоте
    snapshot_info = await get_latest_snapshot_info()
    
    message = START_MESSAGE
    if snapshot_info.get("snapshot_id"):
        message += f"\n\n*Текущий снапшот:* `{snapshot_info['snapshot_id']}`"
        message += f"\n*Дата:* `{snapshot_info['timestamp']}`"
    
    # Отправляем приветственное сообщение
    await send_markdown(update, context, message, add_disclaimer=False)
    
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
    
    await send_markdown(update, context, HELP_MESSAGE, add_disclaimer=False)

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
    
    # Проверка на запрос обновления позиций без указания тикеров
    simple_update_pattern = r"^(обнови|обновить|измени|изменить)\s+(позиции|список|портфель)$"
    simple_match = re.search(simple_update_pattern, message_text.lower())
    
    if simple_match:
        logger.info(f"User {user_id} requested portfolio update without specifying tickers")
        
        # Получаем последний запрос на изменение позиций из истории диалога
        state = get_user_state(user_id)
        dialog_memory = state.get("dialog_memory", [])
        
        # Ищем последний ответ ассистента, где он предложил позиции
        portfolio_suggestion = None
        for msg in reversed(dialog_memory):
            if msg.get("role") == "assistant" and re.search(r"ваш(его|ему)?.*(портфел|позици)", msg.get("content", "").lower()):
                portfolio_suggestion = msg.get("content")
                break
        
        if not portfolio_suggestion:
            await send_markdown(
                update, 
                context, 
                "❌ Не найдено недавних предложений по обновлению портфеля. Пожалуйста, укажите тикеры явно.", 
                add_disclaimer=False
            )
            return
        
        # Извлекаем тикеры из предложения
        tickers = []
        portfolio_text = portfolio_suggestion.lower()
        ticker_matches = re.finditer(r"[^a-z]([A-Z]{1,5})[^a-z]", portfolio_suggestion)
        
        for match in ticker_matches:
            tickers.append(match.group(1))
        
        if not tickers:
            await send_markdown(
                update, 
                context, 
                "❌ Не удалось извлечь тикеры из последнего предложения. Пожалуйста, укажите тикеры явно.", 
                add_disclaimer=False
            )
            return
        
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
    
    # Проверка на запрос обновления позиций с указанными тикерами
    update_positions_pattern = r"(обнови|обновить|измени|изменить|установи|задай).+(позиции|список|портфель)[^а-яА-Я]*(используя|используя тикеры|из|состоящий из|с тикерами)[^а-яА-Я]*([A-Z]{1,5}(,\s*[A-Z]{1,5})*)"
    match = re.search(update_positions_pattern, message_text.lower())
    
    if match:
        logger.info(f"User {user_id} requested portfolio update via text command")
        # Извлекаем список тикеров
        tickers_text = match.group(4).strip()
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
    response_text, image_paths = await run_portfolio_manager(message_text, state)
    
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
    
    if callback_data == "action=reeval":
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
            response_text, image_paths = await run_portfolio_manager(last_message, state)
            
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
        response_text, image_paths = await run_portfolio_manager(rebalance_text, state)
        
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