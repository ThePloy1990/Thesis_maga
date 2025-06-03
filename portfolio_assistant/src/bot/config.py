import os
from dotenv import load_dotenv
from pathlib import Path

# Загрузка настроек из .env файла
load_dotenv()

# Telegram токен
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# API ключи
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Подключение к Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://")

# Пути к директориям
MODEL_DIR = os.getenv("MODEL_DIR", "models/")
PLOTS_TMP = os.getenv("PLOTS_TMP", "tmp/plots")

# Создаем директорию для сохранения графиков, если она не существует
Path(PLOTS_TMP).mkdir(parents=True, exist_ok=True)

# Дисклеймер, который добавляется к каждому сообщению
DISCLAIMER = (
    "⚠️ *Данный контент носит информационный характер и "
    "не является индивидуальной инвестиционной рекомендацией. "
    "Инвестиции сопряжены с риском.*"
)

# URL для Streamlit приложения
STREAMLIT_URL = os.getenv("STREAMLIT_URL", "http://localhost:8501") 