import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple

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
    update_snapshot_id
)
from .reply import (
    send_markdown,
    send_typing_action,
    send_portfolio_response
)
from .agent_integration import (
    run_portfolio_manager,
    build_snapshot,
    get_latest_snapshot_info
)

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

*Примеры запросов:*
• "Собери портфель из AAPL, MSFT и BTC"
• "Расскажи о перспективах Tesla"
• "Сделай сценарий с ростом AAPL на 10%"
• "Какой коэффициент Шарпа у моего портфеля?"
• "Покажи эффективную границу для моих активов"
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
    
    # Получаем информацию о снапшоте
    await send_typing_action(update, context)
    snapshot_info = await get_latest_snapshot_info()
    
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
    
    # Обновляем последний использованный снапшот в состоянии пользователя
    update_snapshot_id(user_id, snapshot_id)
    
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