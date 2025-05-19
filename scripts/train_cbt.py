#!/usr/bin/env python3
"""
Утилита для обучения и обновления моделей CatBoost.

Использование:
    train_cbt.py --all              # Обучение всех моделей
    train_cbt.py --tickers AAPL,MSFT,GOOG  # Обучение указанных тикеров
    train_cbt.py --update AAPL      # Обновление модели для тикера
    train_cbt.py --file data/new_data.csv  # Использование нового набора данных
"""

import os
import sys
import argparse
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Настройка базового пути проекта
project_path = Path(__file__).resolve().parent.parent
sys.path.append(str(project_path))

import pandas as pd
from src.core.model_manager import ModelTrainer, ModelRegistry

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(project_path / "logs" / f"train_cbt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger("train_cbt")

# Создаем директорию для логов, если она не существует
(project_path / "logs").mkdir(exist_ok=True)


def parse_args():
    """Разбор аргументов командной строки."""
    parser = argparse.ArgumentParser(description="Утилита для обучения и обновления моделей CatBoost")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Обучить модели для всех доступных тикеров")
    group.add_argument("--tickers", type=str, help="Обучить модели для указанных тикеров (через запятую)")
    group.add_argument("--update", type=str, help="Обновить модель для указанного тикера")
    group.add_argument("--list", action="store_true", help="Вывести список доступных моделей")
    
    parser.add_argument("--file", type=str, help="Путь к файлу с данными для обучения/обновления")
    parser.add_argument("--iterations", type=int, default=500, help="Количество итераций для обучения")
    parser.add_argument("--learning-rate", type=float, default=0.03, help="Скорость обучения")
    parser.add_argument("--depth", type=int, default=6, help="Глубина деревьев")
    parser.add_argument("--output", type=str, help="Путь для сохранения результатов в JSON")
    
    return parser.parse_args()


def train_models(tickers: List[str], data_file: Optional[str] = None, 
                iterations: int = 500, learning_rate: float = 0.03, 
                depth: int = 6) -> Dict[str, float]:
    """Обучает модели для указанных тикеров и возвращает метрики."""
    trainer = ModelTrainer()
    
    # Загружаем данные, если указан файл
    custom_data = None
    if data_file and Path(data_file).exists():
        logger.info(f"Загрузка данных из файла: {data_file}")
        custom_data = pd.read_csv(data_file)
    
    results = {}
    for ticker in tickers:
        try:
            logger.info(f"Обучение модели для {ticker}")
            _, rmse = trainer.train_model(
                ticker, 
                iterations=iterations,
                learning_rate=learning_rate,
                depth=depth,
                custom_data=custom_data
            )
            results[ticker] = rmse
            logger.info(f"Модель для {ticker} обучена, RMSE: {rmse:.4f}")
        except Exception as e:
            logger.error(f"Ошибка при обучении модели {ticker}: {e}")
            results[ticker] = float('nan')
    
    return results


def update_model(ticker: str, data_file: Optional[str] = None) -> float:
    """Обновляет модель для указанного тикера."""
    trainer = ModelTrainer()
    
    # Загружаем данные, если указан файл
    new_data = None
    if data_file and Path(data_file).exists():
        logger.info(f"Загрузка данных из файла: {data_file}")
        new_data = pd.read_csv(data_file)
    
    try:
        logger.info(f"Обновление модели для {ticker}")
        rmse = trainer.update_model(ticker, new_data)
        logger.info(f"Модель для {ticker} обновлена, RMSE: {rmse:.4f}")
        return rmse
    except Exception as e:
        logger.error(f"Ошибка при обновлении модели {ticker}: {e}")
        return float('nan')


def list_models() -> List[str]:
    """Возвращает список доступных моделей."""
    registry = ModelRegistry()
    models = registry.get_available_models()
    return models


def save_results(results: Dict[str, float], output_path: Optional[str] = None):
    """Сохраняет результаты в JSON-файл."""
    if output_path:
        output_file = Path(output_path)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = project_path / "data" / f"model_training_results_{timestamp}.json"
    
    # Преобразуем NaN в None для корректной сериализации в JSON
    clean_results = {k: None if pd.isna(v) else v for k, v in results.items()}
    
    # Считаем среднее RMSE, если есть валидные значения
    valid_values = [v for v in results.values() if not pd.isna(v)]
    average_rmse = sum(valid_values) / len(valid_values) if valid_values else None
    
    # Добавляем метаданные
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "model_type": "CatBoost",
        "results": clean_results,
        "average_rmse": average_rmse
    }
    
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    logger.info(f"Результаты сохранены в {output_file}")


def main():
    """Основная функция утилиты."""
    args = parse_args()
    
    # Вывод списка моделей
    if args.list:
        models = list_models()
        print(f"Доступно {len(models)} моделей:")
        for model in models:
            print(f"- {model}")
        return
    
    # Обучение всех моделей
    if args.all:
        logger.info("Начало обучения всех моделей")
        trainer = ModelTrainer()
        results = trainer.train_all_models()
    
    # Обучение указанных тикеров
    elif args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
        logger.info(f"Начало обучения моделей для {len(tickers)} тикеров: {tickers}")
        results = train_models(
            tickers, 
            args.file, 
            args.iterations, 
            args.learning_rate, 
            args.depth
        )
    
    # Обновление модели
    elif args.update:
        ticker = args.update.strip()
        logger.info(f"Обновление модели для {ticker}")
        rmse = update_model(ticker, args.file)
        results = {ticker: rmse}
    
    # Сохранение результатов
    save_results(results, args.output)
    
    # Вывод результатов в консоль
    print("\nРезультаты обучения:")
    for ticker, rmse in results.items():
        if pd.isna(rmse):
            print(f"{ticker}: ошибка")
        else:
            print(f"{ticker}: RMSE = {rmse:.4f}")


if __name__ == "__main__":
    main() 