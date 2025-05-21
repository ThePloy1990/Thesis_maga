import os
import uuid
import logging
from typing import List, Optional, Dict, Any, Union
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import CallbackContext

from .config import DISCLAIMER, PLOTS_TMP

logger = logging.getLogger(__name__)

async def send_markdown(update: Update, context: CallbackContext, text: str, 
                      add_disclaimer: bool = True, 
                      reply_markup: Optional[InlineKeyboardMarkup] = None) -> int:
    """
    Отправляет markdown-форматированное сообщение пользователю.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
        text: Текст сообщения с markdown-разметкой
        add_disclaimer: Добавлять ли дисклеймер в конец сообщения
        reply_markup: Опциональная клавиатура с кнопками
        
    Returns:
        ID отправленного сообщения
    """
    try:
        # Добавляем дисклеймер, если нужно
        full_text = text
        if add_disclaimer and DISCLAIMER not in text:
            full_text = f"{text}\n\n{DISCLAIMER}"
        
        # Отправляем сообщение
        message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=full_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return message.message_id
    except Exception as e:
        logger.error(f"Error sending markdown message: {str(e)}")
        try:
            # Пробуем отправить сообщение без markdown в случае ошибки
            message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Произошла ошибка при форматировании сообщения. Текст без форматирования:\n\n{text}"
            )
            return message.message_id
        except Exception as e2:
            logger.error(f"Error sending fallback message: {str(e2)}")
            return 0

async def send_photo(update: Update, context: CallbackContext, 
                   photo_path: str, 
                   caption: Optional[str] = None, 
                   reply_markup: Optional[InlineKeyboardMarkup] = None) -> int:
    """
    Отправляет изображение пользователю.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
        photo_path: Путь к файлу с изображением
        caption: Опциональный заголовок изображения
        reply_markup: Опциональная клавиатура с кнопками
        
    Returns:
        ID отправленного сообщения
    """
    try:
        with open(photo_path, 'rb') as photo:
            message = await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN if caption else None,
                reply_markup=reply_markup
            )
            return message.message_id
    except Exception as e:
        logger.error(f"Error sending photo {photo_path}: {str(e)}")
        await send_markdown(
            update,
            context,
            f"Не удалось отправить изображение. Ошибка: {str(e)}",
            add_disclaimer=False
        )
        return 0

async def send_typing_action(update: Update, context: CallbackContext) -> None:
    """
    Отправляет индикатор набора текста.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
    """
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
    except Exception as e:
        logger.error(f"Error sending typing action: {str(e)}")

async def send_portfolio_response(update: Update, context: CallbackContext, 
                                markdown_text: str, 
                                image_paths: List[str] = None) -> None:
    """
    Отправляет полный ответ портфельного менеджера, включая текст и изображения.
    
    Args:
        update: Объект Update от Telegram
        context: Контекст обработчика
        markdown_text: Markdown-форматированный текст ответа
        image_paths: Список путей к изображениям
    """
    # Создаем клавиатуру с кнопками
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
    await send_markdown(update, context, markdown_text, add_disclaimer=True, reply_markup=reply_markup)
    
    # Затем отправляем все изображения, если они есть
    if image_paths:
        for i, img_path in enumerate(image_paths):
            caption = f"График {i+1}/{len(image_paths)}" if len(image_paths) > 1 else None
            await send_photo(update, context, img_path, caption=caption)

def generate_tmp_file_path(extension: str = 'png') -> str:
    """
    Генерирует уникальный путь к временному файлу для сохранения графика.
    
    Args:
        extension: Расширение файла
        
    Returns:
        Путь к файлу
    """
    file_name = f"{uuid.uuid4()}.{extension}"
    return os.path.join(PLOTS_TMP, file_name) 