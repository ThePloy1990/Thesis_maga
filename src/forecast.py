"""Вспомогательные функции для прогнозирования доходности акций."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from catboost import CatBoostRegressor


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

    model_path = Path("models") / f"catboost_{ticker}.cbm"
    if not model_path.exists():
        raise FileNotFoundError(f"Модель для {ticker} не найдена: {model_path}")

    model = CatBoostRegressor()
    model.load_model(model_path)

    features = _load_features(ticker, data_file or DATA_FILE)
    prediction = model.predict(features)
    return float(prediction[0])

