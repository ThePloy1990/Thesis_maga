@echo off
chcp 65001 >nul
title Portfolio Assistant - Автоматический запуск

echo ============================================================
echo 🚀 PORTFOLIO ASSISTANT - АВТОМАТИЧЕСКИЙ ЗАПУСК
echo ============================================================

:: Проверка Python
echo.
echo 📋 Проверка Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python не найден! Установите Python 3.8+
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%i in ('python --version') do echo ✅ %%i
)

:: Проверка виртуального окружения
echo.
echo 📋 Проверка виртуального окружения...
if defined VIRTUAL_ENV (
    echo ✅ Виртуальное окружение активировано: %VIRTUAL_ENV%
) else if exist "venv\Scripts\activate.bat" (
    echo ⚠️  Виртуальное окружение найдено, но не активировано
    echo 💡 Активируем автоматически...
    call venv\Scripts\activate.bat
    if defined VIRTUAL_ENV (
        echo ✅ Виртуальное окружение активировано
    ) else (
        echo ❌ Не удалось активировать виртуальное окружение
        pause
        exit /b 1
    )
) else (
    echo ⚠️  Виртуальное окружение не найдено
    echo 💡 Создаем виртуальное окружение...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo ✅ Виртуальное окружение создано и активировано
)

:: Проверка requirements.txt
echo.
echo 📋 Проверка зависимостей...
if exist "requirements.txt" (
    echo ✅ Файл requirements.txt найден
    echo 💡 Устанавливаем зависимости...
    pip install -r requirements.txt --quiet --disable-pip-version-check
    if %errorlevel% equ 0 (
        echo ✅ Зависимости установлены
    ) else (
        echo ❌ Ошибка установки зависимостей
        pause
        exit /b 1
    )
) else (
    echo ⚠️  Файл requirements.txt не найден
)

:: Проверка .env файла
echo.
echo 📋 Проверка конфигурации...
if exist ".env" (
    echo ✅ Файл .env найден
) else (
    echo ⚠️  Файл .env не найден
    echo 💡 Создайте файл .env с TELEGRAM_TOKEN
)

:: Проверка снапшотов
echo.
echo 📋 Проверка данных...
if exist "local\snapshots" (
    for /f %%i in ('dir /b "local\snapshots\*.json" 2^>nul ^| find /c /v ""') do set snapshot_count=%%i
    if !snapshot_count! gtr 0 (
        echo ✅ Найдено !snapshot_count! снапшотов
    ) else (
        echo ⚠️  Снапшоты не найдены в local\snapshots\
    )
) else (
    echo ⚠️  Папка local\snapshots не найдена
)

:: Запуск приложения
echo.
echo 🚀 Запускаем Portfolio Assistant...
echo    Подождите, приложение загружается...
echo    Приложение откроется в браузере через несколько секунд...

:: Запускаем через Python launcher
python launcher.py

:: Альтернативный запуск, если launcher не работает
if %errorlevel% neq 0 (
    echo.
    echo 💡 Пробуем альтернативный запуск...
    
    :: Открываем браузер в фоне через 3 секунды
    timeout /t 3 >nul
    start http://localhost:8501
    
    :: Запускаем Streamlit
    streamlit run streamlit_app.py --server.port=8501 --server.headless=false --browser.gatherUsageStats=false
)

pause 