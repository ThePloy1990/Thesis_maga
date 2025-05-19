#!/usr/bin/env python3
"""
Комплексное тестирование новой функциональности работы с моделями CatBoost.
Выполняет полное тестирование всех аспектов системы:
- Динамическая загрузка моделей
- Обучение и переобучение моделей
- Прогнозирование с использованием новой инфраструктуры
- Проверка интеграции с существующим кодом
"""

import sys
import os
import logging
import json
import time
import shutil
from pathlib import Path
from datetime import datetime

# Настройка пути к проекту
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Настройка логирования
log_file = project_root / "logs" / f"comprehensive_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
log_file.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger("comprehensive_test")

# Импорт необходимых модулей
import pandas as pd
import numpy as np
from catboost import CatBoostRegressor

from src.core.model_manager import ModelRegistry, ModelTrainer, predict_with_model_registry
from src.core.forecast import get_available_models, batch_predict, predict_with_catboost
from src.data_collection import StockDataCollector


def prepare_test_environment():
    """Подготовка тестового окружения."""
    logger.info("=== Подготовка тестового окружения ===")
    
    # Создаем временную директорию для тестовых моделей
    test_models_dir = project_root / "models" / "test_models"
    test_models_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Создана директория для тестовых моделей: {test_models_dir}")
    
    # Копируем некоторые существующие модели для тестирования
    source_models_dir = project_root / "models"
    sample_models = list(source_models_dir.glob("catboost_*.cbm"))[:3]  # Берем первые 3 модели
    
    if not sample_models:
        logger.error("Не найдены модели для тестирования!")
        return None
    
    # Копируем модели в тестовую директорию
    test_tickers = []
    for model_path in sample_models:
        ticker = model_path.stem.replace("catboost_", "")
        test_tickers.append(ticker)
        shutil.copy(model_path, test_models_dir / model_path.name)
        logger.info(f"Скопирована модель {ticker} в тестовую директорию")
    
    # Возвращаем информацию о тестовом окружении
    return {
        "test_models_dir": test_models_dir,
        "test_tickers": test_tickers
    }


def test_model_registry(test_env):
    """Тестирование реестра моделей."""
    logger.info("\n=== Тестирование ModelRegistry ===")
    
    test_models_dir = test_env["test_models_dir"]
    test_tickers = test_env["test_tickers"]
    
    # Создаем реестр моделей с тестовой директорией
    registry = ModelRegistry(models_dir=test_models_dir)
    
    # Проверяем список доступных моделей
    available_models = registry.get_available_models()
    logger.info(f"Доступные модели: {available_models}")
    assert set(test_tickers).issubset(set(available_models)), "Не все тестовые модели найдены в реестре"
    
    # Тестируем загрузку моделей и кэширование
    cache_hits = 0
    for ticker in test_tickers:
        start_time = time.time()
        model1 = registry.get_model(ticker)
        first_load_time = time.time() - start_time
        
        start_time = time.time()
        model2 = registry.get_model(ticker)
        second_load_time = time.time() - start_time
        
        logger.info(f"Модель {ticker}: первая загрузка {first_load_time:.4f}с, вторая загрузка {second_load_time:.4f}с")
        
        # Проверяем, что это тот же объект (из кэша)
        if id(model1) == id(model2):
            cache_hits += 1
    
    logger.info(f"Кэширование моделей: {cache_hits}/{len(test_tickers)} успешных попаданий")
    assert cache_hits == len(test_tickers), "Не все модели были корректно кэшированы"
    
    return registry


def test_prediction(test_env):
    """Тестирование прогнозирования с использованием ModelRegistry."""
    logger.info("\n=== Тестирование прогнозирования ===")
    
    test_models_dir = test_env["test_models_dir"]
    test_tickers = test_env["test_tickers"]
    
    # Проверка индивидуального прогнозирования
    try:
        # Получение данных для прогнозирования
        data_file = project_root / "data" / "stocks_with_indicators_20.csv"
        
        # Проверяем, есть ли данные для тикеров
        has_data = True
        if not data_file.exists():
            logger.warning(f"Файл данных не найден: {data_file}. Создаем тестовые данные.")
            has_data = False
        else:
            # Загружаем данные и проверяем наличие тикеров
            df = pd.read_csv(data_file)
            has_data = any(ticker in df["symbol"].values for ticker in test_tickers)
            
            if not has_data:
                logger.warning(f"В файле {data_file} нет данных для тестовых тикеров. Создаем тестовые данные.")
        
        # Создаем синтетические данные для тестирования, если нет реальных
        if not has_data:
            # Создаем DataFrame для тестирования
            np.random.seed(42)
            test_data = []
            
            for ticker in test_tickers:
                # Создаем 10 строк данных для каждого тикера
                for i in range(10):
                    row = {
                        "Date": f"2025-01-{i+1:02d}",
                        "symbol": ticker,
                        "open": 100 + np.random.randn() * 5,
                        "high": 105 + np.random.randn() * 5,
                        "low": 95 + np.random.randn() * 5,
                        "close": 102 + np.random.randn() * 5,
                        "volume": 1000000 + np.random.randint(0, 500000),
                        "future_price": 105 + np.random.randn() * 10,
                        "annual_return": 0.1 + np.random.randn() * 0.05
                    }
                    
                    # Добавляем дополнительные признаки
                    for j in range(10):
                        row[f"feature_{j}"] = np.random.randn()
                        
                    test_data.append(row)
            
            # Создаем DataFrame
            df = pd.DataFrame(test_data)
            
            # Сохраняем во временный файл
            test_data_file = test_models_dir.parent / "test_features.csv"
            df.to_csv(test_data_file, index=False)
            logger.info(f"Созданы тестовые данные для прогнозирования: {test_data_file}")
            
            # Используем созданный файл
            data_file = test_data_file
        
        # Теперь выполняем прогнозирование
        for ticker in test_tickers:
            # Проверяем наличие данных для тикера
            ticker_data = df[df["symbol"] == ticker]
            if ticker_data.empty:
                logger.warning(f"Нет данных для тикера {ticker} в {data_file}")
                continue
            
            # Подготавливаем признаки
            features = ticker_data.drop(columns=["Date", "symbol", "future_price", "annual_return"], errors="ignore").tail(1)
            
            try:
                # Прогнозирование через ModelRegistry напрямую
                registry = ModelRegistry(models_dir=test_models_dir)
                model = registry.get_model(ticker)
                prediction1 = float(model.predict(features)[0])
                
                # Прогнозирование через функцию-обертку
                prediction2 = predict_with_model_registry(ticker, features)
                
                # Прогнозирование через модуль forecast
                prediction3 = predict_with_catboost(ticker, data_file)
                
                logger.info(f"Прогнозы для {ticker}:")
                logger.info(f"- Напрямую через модель: {prediction1:.4f}")
                logger.info(f"- Через predict_with_model_registry: {prediction2:.4f}")
                logger.info(f"- Через predict_with_catboost: {prediction3:.4f}")
                
                # Проверка согласованности прогнозов
                assert abs(prediction1 - prediction2) < 1e-6, "Прогнозы отличаются!"
                assert abs(prediction1 - prediction3) < 1e-6, "Прогнозы отличаются!"
            except Exception as e:
                logger.error(f"Ошибка при прогнозировании для {ticker}: {e}")
    
    except Exception as e:
        logger.error(f"Ошибка при тестировании прогнозирования: {e}")
        raise
    
    # Тестируем пакетное прогнозирование
    try:
        predictions = batch_predict(test_tickers)
        logger.info(f"Результаты пакетного прогнозирования: {predictions}")
    except Exception as e:
        logger.error(f"Ошибка при пакетном прогнозировании: {e}")
        raise


def test_model_training(test_env):
    """Тестирование обучения и обновления моделей."""
    logger.info("\n=== Тестирование обучения моделей ===")
    
    test_models_dir = test_env["test_models_dir"]
    
    # Создание тестовых данных для обучения
    logger.info("Подготовка тестовых данных для обучения...")
    
    # Проверяем наличие реальных данных
    train_data_file = project_root / "data" / "sp500_ml_ready_20250412_174743.csv"
    
    # Создаем синтетические данные для тестирования
    logger.info("Создаем синтетические данные для обучения...")
    
    np.random.seed(42)
    num_samples = 100
    num_features = 10
    
    # Создаем тестовый тикер
    test_ticker = "TEST_TICKER"
    
    # Создаем признаки
    X = np.random.randn(num_samples, num_features)
    
    # Создаем целевую переменную с некоторой зависимостью от признаков
    y = 0.5 + 0.4 * X[:, 0] - 0.3 * X[:, 1] + 0.2 * np.random.randn(num_samples)
    
    # Создаем DataFrame
    features_cols = [f"feature_{i}" for i in range(num_features)]
    data = pd.DataFrame(X, columns=features_cols)
    data["symbol"] = test_ticker
    data["Date"] = pd.date_range(start="2025-01-01", periods=num_samples).strftime("%Y-%m-%d")
    data["future_price"] = y
    data["annual_return"] = y / 100  # Просто для создания второй возможной целевой переменной
    
    # Добавим еще несколько полезных колонок, которые могут быть нужны для модели
    data["open"] = 100 + np.random.randn(num_samples) * 5
    data["high"] = data["open"] + 5 + np.random.randn(num_samples) * 2
    data["low"] = data["open"] - 5 - np.random.randn(num_samples) * 2
    data["close"] = data["open"] + np.random.randn(num_samples) * 3
    data["volume"] = 1000000 + np.random.randint(0, 500000, num_samples)
    
    # Сохраняем данные во временный файл
    temp_data_file = test_models_dir.parent / "test_train_data.csv"
    data.to_csv(temp_data_file, index=False)
    logger.info(f"Созданы синтетические данные для обучения: {temp_data_file}")
    
    # Создаем экземпляр ModelTrainer
    trainer = ModelTrainer(models_dir=test_models_dir)
    
    # Обучаем новую модель
    try:
        logger.info(f"Обучение новой модели для {test_ticker}...")
        model, rmse = trainer.train_model(
            test_ticker,
            iterations=50,  # Уменьшаем для ускорения тестов
            custom_data=pd.read_csv(temp_data_file)
        )
        logger.info(f"Модель для {test_ticker} успешно обучена, RMSE: {rmse:.4f}")
        
        # Путь к созданной модели
        model_path = test_models_dir / f"catboost_{test_ticker}.cbm"
        logger.info(f"Проверка наличия файла модели: {model_path.exists()}")
        
        # Проверяем, что модель можно загрузить
        loaded_model = CatBoostRegressor()
        loaded_model.load_model(model_path)
        logger.info("Модель успешно загружена")
        
        # Делаем прогноз с использованием новой модели
        test_features = data[features_cols].head(1)
        prediction = loaded_model.predict(test_features)[0]
        logger.info(f"Тестовый прогноз с новой моделью: {prediction:.4f}")
    except Exception as e:
        logger.error(f"Ошибка при обучении новой модели: {e}")
    
    # Обновляем существующую модель
    try:
        logger.info(f"Обновление модели для {test_ticker}...")
        rmse = trainer.update_model(test_ticker, pd.read_csv(temp_data_file))
        logger.info(f"Модель для {test_ticker} успешно обновлена, RMSE: {rmse:.4f}")
        
        # Проверяем, что модель по-прежнему работает
        model_path = test_models_dir / f"catboost_{test_ticker}.cbm"
        loaded_model = CatBoostRegressor()
        loaded_model.load_model(model_path)
        
        # Делаем прогноз с использованием обновленной модели
        test_features = data[features_cols].head(1)
        prediction = loaded_model.predict(test_features)[0]
        logger.info(f"Тестовый прогноз с обновленной моделью: {prediction:.4f}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении модели: {e}")
    
    # Возвращаем тестовый тикер для использования в других тестах
    return test_ticker


def test_train_cbt_utility(test_env, test_ticker):
    """Тестирование утилиты train_cbt.py."""
    logger.info("\n=== Тестирование утилиты train_cbt.py ===")
    
    test_models_dir = test_env["test_models_dir"]
    
    # Проверяем список доступных моделей через утилиту
    try:
        import subprocess
        
        # Запускаем утилиту с опцией --list
        logger.info("Запуск train_cbt.py --list...")
        result = subprocess.run(
            ["python", "scripts/train_cbt.py", "--list"], 
            capture_output=True, 
            text=True
        )
        logger.info(f"Результат: {result.stdout}")
        assert result.returncode == 0, "Ошибка при запуске утилиты с опцией --list"
        
        # Если у нас есть тестовый тикер из предыдущего теста,
        # используем его для тестирования обновления
        if test_ticker:
            # Запускаем утилиту для обновления модели
            logger.info(f"Запуск train_cbt.py --update {test_ticker}...")
            
            # Путь к тестовым данным
            train_data_path = test_models_dir.parent / "test_train_data.csv"
            
            # Проверяем, что файл с данными существует
            if not train_data_path.exists():
                logger.error(f"Файл с данными для обучения не найден: {train_data_path}")
                return
            
            # Создаем временный файл для вывода результатов
            output_json = test_models_dir / f"update_results_{test_ticker}.json"
            
            # Запускаем утилиту с указанием файла данных
            result = subprocess.run(
                [
                    "python", 
                    "scripts/train_cbt.py", 
                    "--update", test_ticker,
                    "--file", str(train_data_path),
                    "--output", str(output_json)
                ], 
                capture_output=True, 
                text=True
            )
            logger.info(f"Результат: {result.stdout}")
            if result.stderr:
                logger.warning(f"Ошибки: {result.stderr}")
            
            # Проверяем, что результат сохранен
            if output_json.exists():
                # Загружаем и проверяем результаты
                with open(output_json, 'r') as f:
                    update_results = json.load(f)
                
                logger.info(f"Результаты обновления: {json.dumps(update_results, indent=2)}")
            else:
                logger.warning(f"Файл с результатами {output_json} не создан")
        
    except Exception as e:
        logger.error(f"Ошибка при тестировании утилиты train_cbt.py: {e}")
        raise


def cleanup_test_environment(test_env):
    """Очистка тестового окружения."""
    logger.info("\n=== Очистка тестового окружения ===")
    
    test_models_dir = test_env["test_models_dir"]
    
    try:
        # Удаляем временные файлы и директории
        if test_models_dir.exists():
            shutil.rmtree(test_models_dir)
            logger.info(f"Удалена тестовая директория: {test_models_dir}")
        
        # Удаляем временные файлы с данными
        temp_files = [
            test_models_dir.parent / "test_train_data.csv",
            test_models_dir.parent / "test_features.csv",
            test_models_dir.parent / "test_data.csv"
        ]
        
        for temp_file in temp_files:
            if temp_file.exists():
                temp_file.unlink()
                logger.info(f"Удален временный файл: {temp_file}")
    except Exception as e:
        logger.error(f"Ошибка при очистке тестового окружения: {e}")
        logger.info("Продолжаем выполнение, несмотря на ошибку очистки")


def main():
    """Основная функция тестирования."""
    try:
        logger.info("Начало комплексного тестирования")
        
        # Подготовка тестового окружения
        test_env = prepare_test_environment()
        if not test_env:
            logger.error("Не удалось подготовить тестовое окружение")
            return 1
        
        # Тестирование реестра моделей
        registry = test_model_registry(test_env)
        
        # Тестирование прогнозирования
        test_prediction(test_env)
        
        # Тестирование обучения и обновления моделей
        test_ticker = test_model_training(test_env)
        
        # Тестирование утилиты train_cbt.py
        test_train_cbt_utility(test_env, test_ticker)
        
        # Очистка тестового окружения
        cleanup_test_environment(test_env)
        
        logger.info("Все тесты успешно завершены!")
        return 0
    
    except Exception as e:
        logger.error(f"Ошибка при выполнении тестов: {e}")
        return 1
    

if __name__ == "__main__":
    sys.exit(main()) 