@echo off
echo ===================================
echo Тестирование компонентов сбора данных
echo ===================================

rem Переход в корневую директорию проекта
cd %~dp0\..

rem Установка необходимых библиотек
pip install -q yfinance ccxt requests transformers torch

rem Запуск тестирования
echo Запуск тестирования...
python scripts/test_data_collectors.py

echo ===================================
echo Тестирование завершено
echo ===================================

pause 