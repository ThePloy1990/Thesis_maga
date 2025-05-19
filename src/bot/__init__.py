"""
Пакет с компонентами ботов:
- Telegram бот
- Streamlit панель управления
"""

from bot.telegram_bot import setup_bot
from bot.streamlit_report import create_report_page

__all__ = [
    'setup_bot',
    'create_report_page'
] 