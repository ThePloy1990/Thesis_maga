#!/usr/bin/env python3
"""
Скрипт для запуска Streamlit приложения Portfolio Assistant
"""

import subprocess
import sys
import os

def main():
    print("🚀 Запуск Portfolio Assistant...")
    print("📊 Интерфейс будет доступен по адресу: http://localhost:8501")
    print("⚠️  Для остановки нажмите Ctrl+C")
    print("-" * 50)
    
    try:
        # Убеждаемся что мы в правильной директории
        if not os.path.exists("streamlit_app.py"):
            print("❌ Ошибка: файл streamlit_app.py не найден!")
            print("Убедитесь что вы запускаете скрипт из корневой директории проекта")
            return
        
        # Запускаем Streamlit
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
            "--server.port", "8501",
            "--server.address", "localhost",
            "--browser.gatherUsageStats", "false"
        ])
        
    except KeyboardInterrupt:
        print("\n👋 Приложение остановлено пользователем")
    except Exception as e:
        print(f"❌ Ошибка при запуске: {e}")

if __name__ == "__main__":
    main() 