#!/usr/bin/env python3
"""
🚀 Portfolio Assistant Launcher
Автоматический запуск портфельного ассистента
"""

import os
import sys
import subprocess
import webbrowser
import time
from pathlib import Path

def check_python_version():
    """Проверка версии Python"""
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или выше")
        print(f"   Текущая версия: {sys.version}")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True

def check_virtual_env():
    """Проверка виртуального окружения"""
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("✅ Виртуальное окружение активировано")
        return True
    else:
        print("⚠️  Виртуальное окружение не активировано")
        venv_path = Path("venv")
        if venv_path.exists():
            print("💡 Найдено виртуальное окружение в папке 'venv'")
            if sys.platform == "win32":
                activate_cmd = "venv\\Scripts\\activate.bat"
            else:
                activate_cmd = "source venv/bin/activate"
            print(f"   Запустите: {activate_cmd}")
        return False

def check_requirements():
    """Проверка установленных зависимостей"""
    print("🔍 Проверяем зависимости...")
    
    # Основные пакеты для проверки
    required_packages = [
        ('streamlit', 'streamlit'),
        ('plotly', 'plotly'), 
        ('pandas', 'pandas'),
        ('numpy', 'numpy'),
        ('yfinance', 'yfinance'),
        ('python-telegram-bot', 'telegram'),
        ('kaleido', 'kaleido'),
        ('scikit-learn', 'sklearn'),
        ('fastapi', 'fastapi'),
        ('sqlalchemy', 'sqlalchemy')
    ]
    
    missing_packages = []
    
    for package_name, import_name in required_packages:
        try:
            __import__(import_name)
            print(f"   ✅ {package_name}")
        except ImportError:
            print(f"   ❌ {package_name}")
            missing_packages.append(package_name)
    
    if missing_packages:
        print(f"\n❌ Отсутствуют пакеты: {', '.join(missing_packages)}")
        print("💡 Установите их командой:")
        print(f"   pip install {' '.join(missing_packages)}")
        return False
    
    return True

def check_env_file():
    """Проверка файла .env"""
    env_path = Path(".env")
    if not env_path.exists():
        print("⚠️  Файл .env не найден")
        print("💡 Создайте файл .env с токеном Telegram бота:")
        print("   TELEGRAM_TOKEN=ваш_токен_здесь")
        return False
    
    print("✅ Файл .env найден")
    return True

def check_snapshots():
    """Проверка наличия снапшотов"""
    snapshots_dir = Path("local/snapshots")
    if not snapshots_dir.exists():
        print("⚠️  Папка снапшотов не найдена")
        return False
    
    snapshots = list(snapshots_dir.glob("*.json"))
    if not snapshots:
        print("⚠️  Снапшоты не найдены в local/snapshots/")
        return False
    
    print(f"✅ Найдено {len(snapshots)} снапшотов")
    return True

def launch_streamlit():
    """Запуск Streamlit приложения"""
    print("\n🚀 Запускаем Portfolio Assistant...")
    print("   Подождите, приложение загружается...")
    
    # Запускаем Streamlit
    try:
        # Открываем браузер через 3 секунды
        def open_browser():
            time.sleep(3)
            webbrowser.open("http://localhost:8501")
        
        import threading
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.start()
        
        # Запускаем Streamlit
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
            "--server.port=8501",
            "--server.headless=false",
            "--browser.gatherUsageStats=false"
        ])
        
    except KeyboardInterrupt:
        print("\n\n👋 Portfolio Assistant остановлен")
    except Exception as e:
        print(f"\n❌ Ошибка запуска: {e}")

def main():
    """Главная функция"""
    print("=" * 60)
    print("🚀 PORTFOLIO ASSISTANT LAUNCHER")
    print("=" * 60)
    
    # Проверки системы
    checks = [
        ("Python версия", check_python_version),
        ("Виртуальное окружение", check_virtual_env),
        ("Зависимости", check_requirements),
        ("Конфигурация", check_env_file),
        ("Данные снапшотов", check_snapshots)
    ]
    
    passed_checks = 0
    total_checks = len(checks)
    
    for name, check_func in checks:
        print(f"\n📋 {name}:")
        if check_func():
            passed_checks += 1
    
    print(f"\n📊 Результат проверок: {passed_checks}/{total_checks}")
    
    if passed_checks == total_checks:
        print("🎉 Все проверки пройдены успешно!")
        launch_streamlit()
    else:
        print("\n⚠️  Есть проблемы, которые нужно исправить")
        print("💡 Исправьте указанные проблемы и запустите снова")
        
        # Спрашиваем, хотят ли запустить принудительно
        try:
            response = input("\nХотите запустить принудительно? (y/n): ")
            if response.lower() in ['y', 'yes', 'да', 'д']:
                print("🚀 Принудительный запуск...")
                launch_streamlit()
        except KeyboardInterrupt:
            print("\n👋 Отменено")

if __name__ == "__main__":
    main() 