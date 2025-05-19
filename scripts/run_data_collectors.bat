@echo off
echo ===================================
echo Запуск обработчика сбора данных
echo ===================================

rem Переход в корневую директорию проекта
cd %~dp0\..

rem Проверка и создание директории для данных
if not exist data mkdir data

rem Запуск Celery с поддержкой Beat для периодических задач
echo Запуск Celery с Beat scheduler...
celery -A src.services.celery_app worker --loglevel=INFO --pool=solo -B

echo ===================================
echo Обработчик остановлен
echo ===================================

pause 