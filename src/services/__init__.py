"""
Пакет с сервисами:
- Celery для фоновых задач
- API
- Интеграции с внешними сервисами
- Модели данных
"""

from src.services.models import User, SessionLocal, Base

__all__ = [
    'User',
    'SessionLocal',
    'Base'
] 