#!/usr/bin/env python3
"""
Основной файл для запуска Telegram-бота "AI-портфельный ассистент".
"""

import logging
import os
import sys
from pathlib import Path

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

# Добавляем корневую директорию проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.bot.config import TELEGRAM_TOKEN
from src.bot.handlers import (
    start_command,
    help_command,
    risk_command,
    budget_command,
    positions_command,
    snapshot_command,
    update_command,
    update_all_command,
    reset_command,
    message_handler,
    callback_handler,
    error_handler,
    tickers_command,
    accept_command,
    performance_command,
    streamlit_command
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Запускает бота."""
    # Проверяем наличие токена
    if not TELEGRAM_TOKEN:
        logger.error("No TELEGRAM_TOKEN found in environment. Please set it in .env file.")
        sys.exit(1)
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("risk", risk_command))
    application.add_handler(CommandHandler("budget", budget_command))
    application.add_handler(CommandHandler("positions", positions_command))
    application.add_handler(CommandHandler("snapshot", snapshot_command))
    application.add_handler(CommandHandler("update", update_command))
    application.add_handler(CommandHandler("updateall", update_all_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("tickers", tickers_command))
    application.add_handler(CommandHandler("accept", accept_command))
    application.add_handler(CommandHandler("performance", performance_command))
    application.add_handler(CommandHandler("streamlit", streamlit_command))
    
    # Регистрируем обработчик для callback-запросов (inline-кнопки)
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Обработчик текстовых сообщений (должен быть последним)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Starting Portfolio Assistant Bot")
    application.run_polling()

if __name__ == '__main__':
    main()
