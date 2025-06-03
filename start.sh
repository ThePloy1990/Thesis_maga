#!/bin/bash

# 🚀 Portfolio Assistant - Скрипт запуска для MacOS/Linux
# Автоматический запуск портфельного ассистента

echo "============================================================"
echo "🚀 PORTFOLIO ASSISTANT - АВТОМАТИЧЕСКИЙ ЗАПУСК"
echo "============================================================"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода с цветом
print_status() {
    echo -e "${2}${1}${NC}"
}

# Проверка Python
echo ""
print_status "📋 Проверка Python..." $BLUE
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version 2>&1)
    print_status "✅ $python_version" $GREEN
else
    print_status "❌ Python3 не найден! Установите Python 3.8+" $RED
    exit 1
fi

# Проверка виртуального окружения
echo ""
print_status "📋 Проверка виртуального окружения..." $BLUE
if [[ "$VIRTUAL_ENV" != "" ]]; then
    print_status "✅ Виртуальное окружение активировано: $VIRTUAL_ENV" $GREEN
elif [[ -d "venv" ]]; then
    print_status "⚠️  Виртуальное окружение найдено, но не активировано" $YELLOW
    print_status "💡 Активируем автоматически..." $BLUE
    source venv/bin/activate
    if [[ "$VIRTUAL_ENV" != "" ]]; then
        print_status "✅ Виртуальное окружение активировано" $GREEN
    else
        print_status "❌ Не удалось активировать виртуальное окружение" $RED
        exit 1
    fi
else
    print_status "⚠️  Виртуальное окружение не найдено" $YELLOW
    print_status "💡 Создаем виртуальное окружение..." $BLUE
    python3 -m venv venv
    source venv/bin/activate
    print_status "✅ Виртуальное окружение создано и активировано" $GREEN
fi

# Проверка requirements.txt
echo ""
print_status "📋 Проверка зависимостей..." $BLUE
if [[ -f "requirements.txt" ]]; then
    print_status "✅ Файл requirements.txt найден" $GREEN
    print_status "💡 Устанавливаем зависимости..." $BLUE
    pip install -r requirements.txt --quiet --disable-pip-version-check
    if [[ $? -eq 0 ]]; then
        print_status "✅ Зависимости установлены" $GREEN
    else
        print_status "❌ Ошибка установки зависимостей" $RED
        exit 1
    fi
else
    print_status "⚠️  Файл requirements.txt не найден" $YELLOW
fi

# Проверка .env файла
echo ""
print_status "📋 Проверка конфигурации..." $BLUE
if [[ -f ".env" ]]; then
    print_status "✅ Файл .env найден" $GREEN
else
    print_status "⚠️  Файл .env не найден" $YELLOW
    print_status "💡 Создайте файл .env с TELEGRAM_TOKEN" $BLUE
fi

# Проверка снапшотов
echo ""
print_status "📋 Проверка данных..." $BLUE
if [[ -d "local/snapshots" ]]; then
    snapshot_count=$(find local/snapshots -name "*.json" | wc -l)
    if [[ $snapshot_count -gt 0 ]]; then
        print_status "✅ Найдено $snapshot_count снапшотов" $GREEN
    else
        print_status "⚠️  Снапшоты не найдены в local/snapshots/" $YELLOW
    fi
else
    print_status "⚠️  Папка local/snapshots не найдена" $YELLOW
fi

# Запуск приложения
echo ""
print_status "🚀 Запускаем Portfolio Assistant..." $GREEN
print_status "   Подождите, приложение загружается..." $BLUE
print_status "   Приложение откроется в браузере через несколько секунд..." $BLUE

# Запускаем через Python launcher
python3 launcher.py

# Альтернативный запуск, если launcher не работает
if [[ $? -ne 0 ]]; then
    echo ""
    print_status "💡 Пробуем альтернативный запуск..." $YELLOW
    
    # Открываем браузер в фоне через 3 секунды
    (sleep 3 && open http://localhost:8501) &
    
    # Запускаем Streamlit
    streamlit run streamlit_app.py --server.port=8501 --server.headless=false --browser.gatherUsageStats=false
fi 