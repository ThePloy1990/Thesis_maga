"""
Модуль для управления моделями CatBoost.
Обеспечивает динамическую загрузку, кэширование и обновление моделей.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from datetime import datetime

import pandas as pd
import numpy as np
from catboost import CatBoostRegressor

logger = logging.getLogger(__name__)

# Константы
DEFAULT_MODELS_DIR = Path("models")
DEFAULT_DATA_DIR = Path("data")
FEATURES_FILE = Path("data/stocks_with_indicators_20.csv")
TRAIN_DATA_FILE = Path("data/sp500_ml_ready_20250412_174743.csv")


class ModelRegistry:
    """
    Реестр моделей CatBoost для прогнозирования доходности акций.
    Обеспечивает кэширование загруженных моделей для быстрого доступа.
    """

    def __init__(self, models_dir: Path = DEFAULT_MODELS_DIR):
        self.models_dir = models_dir
        self.models_cache: Dict[str, Tuple[CatBoostRegressor, datetime]] = {}
        
        # Убедимся, что директория с моделями существует
        if not models_dir.exists():
            models_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Создана директория моделей: {models_dir}")
    
    def get_model(self, ticker: str) -> CatBoostRegressor:
        """
        Получает модель для указанного тикера.
        Если модель уже загружена и не устарела, возвращает её из кэша.
        """
        # Проверяем, есть ли модель в кэше и не устарела ли она
        if ticker in self.models_cache:
            model, load_time = self.models_cache[ticker]
            model_path = self._get_model_path(ticker)
            
            # Проверяем, не была ли модель изменена с момента загрузки
            if model_path.exists():
                mod_time = datetime.fromtimestamp(model_path.stat().st_mtime)
                if mod_time <= load_time:
                    logger.debug(f"Модель {ticker} загружена из кэша")
                    return model
        
        # Если модели нет в кэше или она устарела, загружаем заново
        model_path = self._get_model_path(ticker)
        if not model_path.exists():
            raise FileNotFoundError(f"Модель для {ticker} не найдена: {model_path}")
        
        logger.info(f"Загрузка модели {ticker} из {model_path}")
        model = CatBoostRegressor()
        model.load_model(model_path)
        
        # Сохраняем в кэш с временем загрузки
        self.models_cache[ticker] = (model, datetime.now())
        return model
    
    def get_available_models(self) -> List[str]:
        """Возвращает список доступных моделей (тикеров)."""
        models = []
        for file in self.models_dir.glob("catboost_*.cbm"):
            ticker = file.stem.replace("catboost_", "")
            models.append(ticker)
        return sorted(models)
    
    def _get_model_path(self, ticker: str) -> Path:
        """Возвращает путь к файлу модели для указанного тикера."""
        return self.models_dir / f"catboost_{ticker}.cbm"


class ModelTrainer:
    """
    Класс для обучения и обновления моделей CatBoost.
    Позволяет обучать модели для отдельных тикеров и всего набора данных.
    """

    def __init__(
        self, 
        models_dir: Path = DEFAULT_MODELS_DIR,
        data_dir: Path = DEFAULT_DATA_DIR,
        features_file: Path = FEATURES_FILE,
        train_data_file: Path = TRAIN_DATA_FILE,
    ):
        self.models_dir = models_dir
        self.data_dir = data_dir
        self.features_file = features_file
        self.train_data_file = train_data_file
        
        # Создаем директории, если они не существуют
        if not models_dir.exists():
            models_dir.mkdir(parents=True, exist_ok=True)
        if not data_dir.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
    
    def train_model(
        self, 
        ticker: str, 
        iterations: int = 500,
        learning_rate: float = 0.03,
        depth: int = 6,
        custom_data: Optional[pd.DataFrame] = None,
    ) -> Tuple[CatBoostRegressor, float]:
        """
        Обучает модель CatBoost для указанного тикера.
        Возвращает обученную модель и метрику качества (RMSE).
        """
        logger.info(f"Начинаем обучение модели для {ticker}")
        
        # Загружаем данные для обучения
        if custom_data is not None:
            data = custom_data
        else:
            data = self._load_training_data()
        
        # Фильтруем данные по тикеру
        ticker_data = data[data["symbol"] == ticker].copy()
        if ticker_data.empty:
            raise ValueError(f"Нет данных для обучения модели {ticker}")
        
        # Подготавливаем признаки и целевую переменную
        features, target = self._prepare_data(ticker_data)
        
        # Разделяем данные на обучающую и тестовую выборки
        train_size = int(len(features) * 0.8)
        X_train, X_test = features[:train_size], features[train_size:]
        y_train, y_test = target[:train_size], target[train_size:]
        
        # Создаем и обучаем модель
        model = CatBoostRegressor(
            iterations=iterations,
            learning_rate=learning_rate,
            depth=depth,
            loss_function='RMSE',
            verbose=False
        )
        
        model.fit(X_train, y_train, eval_set=(X_test, y_test))
        
        # Оцениваем качество модели
        predictions = model.predict(X_test)
        rmse = np.sqrt(np.mean((predictions - y_test) ** 2))
        logger.info(f"Модель для {ticker} обучена, RMSE: {rmse:.4f}")
        
        # Сохраняем модель
        model_path = self._get_model_path(ticker)
        model.save_model(model_path)
        logger.info(f"Модель сохранена в {model_path}")
        
        return model, rmse
    
    def train_all_models(self, tickers: Optional[List[str]] = None) -> Dict[str, float]:
        """
        Обучает модели для всех тикеров в наборе данных или для указанного списка.
        Возвращает словарь с метриками качества для каждой модели.
        """
        # Загружаем данные для обучения
        data = self._load_training_data()
        
        # Определяем список тикеров для обучения
        if tickers is None:
            tickers = data["symbol"].unique().tolist()
        
        results = {}
        for ticker in tickers:
            try:
                _, rmse = self.train_model(ticker, custom_data=data)
                results[ticker] = rmse
            except Exception as e:
                logger.error(f"Ошибка при обучении модели {ticker}: {e}")
                results[ticker] = float('nan')
        
        return results
    
    def update_model(self, ticker: str, new_data: Optional[pd.DataFrame] = None) -> float:
        """
        Обновляет существующую модель новыми данными.
        Если модель не существует, создает новую.
        Возвращает метрику качества (RMSE) обновленной модели.
        """
        model_path = self._get_model_path(ticker)
        
        # Загружаем данные для обновления
        if new_data is None:
            data = self._load_training_data()
            ticker_data = data[data["symbol"] == ticker].copy()
        else:
            ticker_data = new_data[new_data["symbol"] == ticker].copy()
        
        if ticker_data.empty:
            raise ValueError(f"Нет данных для обновления модели {ticker}")
        
        # Подготавливаем признаки и целевую переменную
        features, target = self._prepare_data(ticker_data)
        
        # Если модель существует, обновляем её, иначе создаем новую
        if model_path.exists():
            model = CatBoostRegressor()
            model.load_model(model_path)
            
            # Обновляем модель
            model.fit(features, target, verbose=False)
        else:
            # Создаем новую модель
            _, rmse = self.train_model(ticker, custom_data=ticker_data)
            return rmse
        
        # Оцениваем качество модели
        predictions = model.predict(features)
        rmse = np.sqrt(np.mean((predictions - target) ** 2))
        
        # Сохраняем обновленную модель
        model.save_model(model_path)
        logger.info(f"Модель {ticker} обновлена, RMSE: {rmse:.4f}")
        
        return rmse
    
    def _load_training_data(self) -> pd.DataFrame:
        """Загружает данные для обучения моделей."""
        if not self.train_data_file.exists():
            raise FileNotFoundError(f"Файл с данными для обучения не найден: {self.train_data_file}")
        
        return pd.read_csv(self.train_data_file)
    
    def _prepare_data(self, data: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Подготавливает данные для обучения:
        - Удаляет ненужные колонки
        - Обрабатывает пропущенные значения
        - Формирует набор признаков и целевую переменную
        """
        # Удаляем ненужные колонки
        features = data.drop(
            columns=["Date", "symbol", "future_price", "annual_return"], 
            errors="ignore"
        )
        
        # Обрабатываем пропущенные значения
        features = features.fillna(features.median())
        
        # Выделяем целевую переменную (прогнозируемую доходность)
        if "annual_return" in data.columns:
            target = data["annual_return"]
        else:
            target = data["future_price"]
        
        return features, target
    
    def _get_model_path(self, ticker: str) -> Path:
        """Возвращает путь к файлу модели для указанного тикера."""
        return self.models_dir / f"catboost_{ticker}.cbm"


# Функция-обертка для совместимости с существующим кодом
def predict_with_model_registry(ticker: str, features: Optional[pd.DataFrame] = None) -> float:
    """
    Использует ModelRegistry для прогнозирования доходности.
    Обеспечивает совместимость с существующим кодом.
    """
    registry = ModelRegistry()
    model = registry.get_model(ticker)
    
    if features is None:
        # Загружаем признаки по умолчанию
        if not FEATURES_FILE.exists():
            raise FileNotFoundError(f"Файл с признаками не найден: {FEATURES_FILE}")
        
        df = pd.read_csv(FEATURES_FILE)
        df_ticker = df[df["symbol"] == ticker]
        if df_ticker.empty:
            raise ValueError(f"Нет данных для тикера {ticker}")
        
        features = df_ticker.drop(
            columns=["Date", "symbol", "future_price", "annual_return"], errors="ignore"
        ).tail(1)
    
    prediction = model.predict(features)
    return float(prediction[0]) 