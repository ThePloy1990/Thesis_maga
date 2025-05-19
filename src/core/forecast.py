"""Вспомогательные функции для прогнозирования доходности акций."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Dict, Union

import pandas as pd
from catboost import CatBoostRegressor

from .model_manager import ModelRegistry, predict_with_model_registry

DATA_FILE = Path("data/stocks_with_indicators_20.csv")


def _load_features(ticker: str, data_file: Path = DATA_FILE) -> pd.DataFrame:
    """Возвращает последнюю строку признаков для указанного тикера."""

    df = pd.read_csv(data_file)
    df_ticker = df[df["symbol"] == ticker]
    if df_ticker.empty:
        raise ValueError(f"Нет данных для тикера {ticker}")

    features = df_ticker.drop(
        columns=["Date", "symbol", "future_price", "annual_return"], errors="ignore"
    )
    return features.tail(1)


def predict_with_catboost(ticker: str, data_file: Path | None = None) -> float:
    """Загружает модель CatBoost и возвращает прогноз доходности."""
    
    # Используем новый способ прогнозирования через ModelRegistry
    if data_file is not None:
        features = _load_features(ticker, data_file)
        return predict_with_model_registry(ticker, features)
    else:
        return predict_with_model_registry(ticker)


def get_available_models() -> List[str]:
    """Возвращает список доступных моделей (тикеров)."""
    registry = ModelRegistry()
    return registry.get_available_models()


def batch_predict(tickers: List[str], data_file: Path | None = None) -> Dict[str, float]:
    """Выполняет прогнозирование для нескольких тикеров."""
    results = {}
    for ticker in tickers:
        try:
            prediction = predict_with_catboost(ticker, data_file)
            results[ticker] = prediction
        except Exception as e:
            results[ticker] = float('nan')
    return results

