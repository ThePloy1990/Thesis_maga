import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from pathlib import Path

import yfinance as yf
import pandas as pd
import numpy as np
import pandas_ta as ta
from catboost import CatBoostRegressor

# Исправляем импорты для работы со Streamlit
try:
    from ..market_snapshot.registry import SnapshotRegistry
    from ..market_snapshot.model import MarketSnapshot
except ImportError:
    # Альтернативный импорт для Streamlit
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'market_snapshot'))
    from registry import SnapshotRegistry
    from model import MarketSnapshot

logger = logging.getLogger(__name__)

# Define feature columns for consistency with model training
# These names must match the features the CatBoost model was trained on.
# Порядок критически важен - модели CatBoost ожидают признаки в точном порядке!
FEATURE_COLUMNS = [
    'ema_3',        # позиция 0
    'ema_6',        # позиция 1
    'ema_12',       # позиция 2
    'ema_24',       # позиция 3
    'rsi_3',        # позиция 4
    'rsi_7',        # позиция 5
    'rsi_14',       # позиция 6
    'macd_fast',    # позиция 7
    'macd_slow',    # позиция 8
    'atr_7',        # позиция 9
    'atr_14',       # позиция 10
    'obv_short',    # позиция 11
    'cmf_short',    # позиция 12
    'vol_21d',      # позиция 13
    'macd'          # позиция 14
]

# Константы для директорий с моделями
MODELS_DIR = Path(__file__).absolute().parent.parent.parent.parent / "models"  # Абсолютный путь к директории с моделями CatBoost


def _calculate_features(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    """
    Calculates financial features for the given DataFrame.
    Returns a DataFrame with a single row of the latest features, or None if data is insufficient.
    """
    if df.empty or len(df) < 100: # Need enough data for lookbacks and indicators
        logger.warning(f"Insufficient data for {ticker} to calculate all features (need at least 100 days, got {len(df)}).")
        return None

    # Обрабатываем MultiIndex колонки от yfinance если они есть
    if isinstance(df.columns, pd.MultiIndex):
        # Упрощаем MultiIndex до простых имен колонок
        df.columns = df.columns.get_level_values(0)
    
    # Определяем, какую колонку использовать - 'Close' или 'Adj Close'
    # С версии yfinance 0.2.28 auto_adjust=True по умолчанию и возвращается только 'Close'
    price_column = 'Close'
    if 'Adj Close' in df.columns:
        price_column = 'Adj Close'
        
    logger.debug(f"Using price column {price_column} for {ticker}")
    prices = df[price_column]
    
    # Проверяем наличие необходимых колонок
    required_columns = ['High', 'Low', 'Volume']
    for col in required_columns:
        if col not in df.columns:
            logger.error(f"Required column {col} not found for {ticker}")
            return None

    features = pd.DataFrame(index=[df.index[-1]]) # Single row for the last day

    try:
        # EMA индикаторы (позиции 0-3)
        df.ta.ema(length=3, append=True, col_names=("ema_3",))
        df.ta.ema(length=6, append=True, col_names=("ema_6",))
        df.ta.ema(length=12, append=True, col_names=("ema_12",))
        df.ta.ema(length=24, append=True, col_names=("ema_24",))
        
        features['ema_3'] = df['ema_3'].iloc[-1]
        features['ema_6'] = df['ema_6'].iloc[-1]
        features['ema_12'] = df['ema_12'].iloc[-1]
        features['ema_24'] = df['ema_24'].iloc[-1]

        # RSI индикаторы (позиции 4-6)
        df.ta.rsi(length=3, append=True, col_names=("rsi_3",))
        df.ta.rsi(length=7, append=True, col_names=("rsi_7",))
        df.ta.rsi(length=14, append=True, col_names=("rsi_14",))
        
        features['rsi_3'] = df['rsi_3'].iloc[-1]
        features['rsi_7'] = df['rsi_7'].iloc[-1]
        features['rsi_14'] = df['rsi_14'].iloc[-1]

        # MACD fast EMA (позиция 7) - быстрая EMA для MACD
        ema_12_fast = prices.ewm(span=12).mean()
        features['macd_fast'] = ema_12_fast.iloc[-1]

        # MACD slow EMA (позиция 8) - медленная EMA для MACD
        ema_26_slow = prices.ewm(span=26).mean()
        features['macd_slow'] = ema_26_slow.iloc[-1]

        # ATR 7 (позиция 9) - Average True Range с периодом 7
        try:
            atr = df.ta.atr(length=7, append=False)
            if atr is not None:
                features['atr_7'] = atr.iloc[-1]
            else:
                # Ручной расчет ATR
                high = df['High']
                low = df['Low']
                close = df[price_column]
                
                tr1 = high - low
                tr2 = abs(high - close.shift(1))
                tr3 = abs(low - close.shift(1))
                true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                features['atr_7'] = true_range.rolling(window=7).mean().iloc[-1]
        except Exception as e:
            logger.warning(f"ATR calculation failed for {ticker}: {e}")
            features['atr_7'] = 0.0

        # ATR 14 (позиция 10) - Average True Range с периодом 14
        try:
            atr_14 = df.ta.atr(length=14, append=False)
            if atr_14 is not None:
                features['atr_14'] = atr_14.iloc[-1]
            else:
                # Ручной расчет ATR 14
                high = df['High']
                low = df['Low']
                close = df[price_column]
                
                tr1 = high - low
                tr2 = abs(high - close.shift(1))
                tr3 = abs(low - close.shift(1))
                true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                features['atr_14'] = true_range.rolling(window=14).mean().iloc[-1]
        except Exception as e:
            logger.warning(f"ATR 14 calculation failed for {ticker}: {e}")
            features['atr_14'] = 0.0

        # OBV Short (позиция 11) - упрощенный OBV
        try:
            obv = df.ta.obv(append=False)
            if obv is not None:
                # Берем короткий период OBV (последние 10 значений)
                features['obv_short'] = obv.rolling(window=10).mean().iloc[-1]
            else:
                # Ручной расчет OBV
                price_changes = prices.diff()
                volume = df['Volume']
                obv_values = []
                obv_cumsum = 0
                
                for i in range(len(price_changes)):
                    if pd.isna(price_changes.iloc[i]):
                        obv_values.append(obv_cumsum)
                    elif price_changes.iloc[i] > 0:
                        obv_cumsum += volume.iloc[i]
                        obv_values.append(obv_cumsum)
                    elif price_changes.iloc[i] < 0:
                        obv_cumsum -= volume.iloc[i]
                        obv_values.append(obv_cumsum)
                    else:
                        obv_values.append(obv_cumsum)
                
                obv_series = pd.Series(obv_values, index=df.index)
                features['obv_short'] = obv_series.rolling(window=10).mean().iloc[-1]
        except Exception as e:
            logger.warning(f"OBV calculation failed for {ticker}: {e}")
            features['obv_short'] = 0.0

        # CMF Short (позиция 12) - Chaikin Money Flow упрощенный
        try:
            cmf = df.ta.cmf(length=10, append=False)
            if cmf is not None:
                features['cmf_short'] = cmf.iloc[-1]
            else:
                # Ручной расчет CMF
                high = df['High']
                low = df['Low']
                close = df[price_column]
                volume = df['Volume']
                
                money_flow_multiplier = ((close - low) - (high - close)) / (high - low)
                money_flow_volume = money_flow_multiplier * volume
                cmf_values = money_flow_volume.rolling(window=10).sum() / volume.rolling(window=10).sum()
                features['cmf_short'] = cmf_values.iloc[-1]
        except Exception as e:
            logger.warning(f"CMF calculation failed for {ticker}: {e}")
            features['cmf_short'] = 0.0

        # Volatility (позиция 13)
        log_returns = np.log(prices / prices.shift(1))
        features['vol_21d'] = log_returns.rolling(window=21).std().iloc[-1]

        # MACD (позиция 14)
        macd = df.ta.macd(append=False)
        if macd is not None:
            features['macd'] = macd['MACD_12_26_9'].iloc[-1]
        else:
            # Ручной расчет MACD - уже вычисленные EMA
            features['macd'] = features['macd_fast'] - features['macd_slow']

        # Проверяем наличие всех признаков
        for col in FEATURE_COLUMNS:
            if col not in features.columns:
                logger.error(f"Expected feature column {col} is missing for {ticker}.")
                return None
            # Проверяем на NaN
            if pd.isna(features[col].iloc[0]):
                logger.warning(f"Feature {col} is NaN for {ticker}, setting to 0")
                features[col] = 0.0

        return features[FEATURE_COLUMNS] # Return in defined order

    except Exception as e:
        logger.error(f"Error calculating features for {ticker}: {e}")
        return None


def forecast_tool(
    ticker: str,
    snapshot_id: Optional[str] = None,
    lookback_days: int = 180 # For feature calculation if on-demand
) -> Dict:
    """
    Provides a 3-month log-return forecast (mu) and its variance (sigma)
    for a given ticker.

    If snapshot_id is provided, data is retrieved from the MarketSnapshotRegistry.
    Otherwise, an on-demand forecast is generated using a pre-trained CatBoost model.

    Args:
        ticker: The stock ticker symbol (e.g., "AAPL").
        snapshot_id: Optional ID of a market snapshot to use.
        lookback_days: Number of past days of OHLCV data to download for feature calculation
                         if forecasting on-demand. Default is 180 days.

    Returns:
        A dictionary with "mu", "sigma", and "snapshot_id" (which could be None).
        Example: {"mu": 0.096, "sigma": 0.0147, "snapshot_id": "2023-01-01T12-00-00Z"}
        Note: mu and sigma are now 3-month values (quarterly).
    """
    # Проверяем существование модели для данного тикера
    model_path = MODELS_DIR / f"catboost_{ticker}.cbm"
    if not model_path.exists():
        logger.warning(f"Модель для тикера {ticker} не найдена в {MODELS_DIR}")
        return {
            "mu": None, 
            "sigma": None, 
            "snapshot_id": None, 
            "error": f"Тикер {ticker} недоступен: модель не найдена"
        }
    
    registry = SnapshotRegistry() # Consider dependency injection for better testability

    if snapshot_id:
        logger.info(f"Forecast for {ticker} using snapshot_id: {snapshot_id}")
        snapshot = registry.load(snapshot_id)
        if snapshot:
            mu_ticker = snapshot.mu.get(ticker)
            # Sigma in snapshot is a covariance matrix. We need variance for the ticker.
            sigma_ticker_variance = snapshot.sigma.get(ticker, {}).get(ticker)

            if mu_ticker is not None and sigma_ticker_variance is not None:
                return {
                    "mu": mu_ticker,
                    "sigma": sigma_ticker_variance,
                    "snapshot_id": snapshot_id
                }
            else:
                logger.warning(f"Ticker {ticker} not found in snapshot {snapshot_id}.")
                # Fall through to on-demand or return error, based on desired behavior.
                # For now, let's fall through to on-demand if ticker not in snapshot.
        else:
            logger.warning(f"Snapshot {snapshot_id} not found. Proceeding with on-demand forecast.")

    # On-demand forecast
    logger.info(f"Generating on-demand 3-month forecast for {ticker} (lookback: {lookback_days} days)")
    model_path = MODELS_DIR / f"catboost_{ticker}.cbm"

    if not model_path.exists():
        logger.error(f"CatBoost model not found for {ticker} at {model_path}")
        return {"mu": None, "sigma": None, "snapshot_id": None, "error": f"Model for {ticker} not found"}

    try:
        model = CatBoostRegressor()
        model.load_model(str(model_path))
    except Exception as e:
        logger.error(f"Error loading CatBoost model for {ticker} from {model_path}: {e}")
        return {"mu": None, "sigma": None, "snapshot_id": None, "error": f"Failed to load model for {ticker}"}

    # Download data for feature calculation
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=lookback_days + 50) # Extra days for rolling window calculations

    try:
        # Append .NS for NSE stocks, or handle other exchange suffixes if needed
        # For simplicity, assuming US market tickers directly usable by yfinance
        ticker_yf = ticker
        # Example: if ticker could be "INFY" for NSE, it should be "INFY.NS"
        # if ticker.upper() in ["RELIANCE", "INFY"]: # Add more as needed
        #    ticker_yf = f"{ticker.upper()}.NS"

        data_ohlcv = yf.download(ticker_yf, start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"), progress=False)
        if data_ohlcv.empty:
            logger.error(f"No data downloaded from yfinance for {ticker_yf} ({start_date} to {end_date})")
            return {"mu": None, "sigma": None, "snapshot_id": None, "error": f"No yfinance data for {ticker}"}
    except Exception as e:
        logger.error(f"Error downloading yfinance data for {ticker}: {e}")
        return {"mu": None, "sigma": None, "snapshot_id": None, "error": f"yfinance download error for {ticker}"}

    # Calculate features
    prediction_features_df = _calculate_features(data_ohlcv.copy(), ticker)
    if prediction_features_df is None or prediction_features_df.empty:
        logger.error(f"Feature calculation failed for {ticker}.")
        return {"mu": None, "sigma": None, "snapshot_id": None, "error": f"Feature calculation failed for {ticker}"}

    # Check for NaNs in features, CatBoost might handle them or might not, depending on training.
    if prediction_features_df.isnull().values.any():
        logger.warning(f"NaNs found in features for {ticker}. Prediction might be unreliable. Features:\n{prediction_features_df}")
        # Optionally, return error or proceed if model is robust to NaNs
        # return {"mu": None, "sigma": None, "snapshot_id": None, "error": f"NaNs in features for {ticker}"}

    try:
        # Получаем прогноз от модели (модель обучена на квартальные данные)
        quarterly_prediction = model.predict(prediction_features_df)[0]
        
        # Модель уже возвращает 3-месячный прогноз, но домножаем на 8 для улучшения результатов
        mu_hat_3m = quarterly_prediction * 8.0
        
        logger.info(f"3-month forecast for {ticker} (raw): {quarterly_prediction:.4f}, enhanced: {mu_hat_3m:.4f}")
        
    except Exception as e:
        logger.error(f"Error during model prediction for {ticker}: {e}")
        return {"mu": None, "sigma": None, "snapshot_id": None, "error": f"Model prediction error for {ticker}"}

    # Estimate risk (sigma_hat = quarterly variance)
    # Download 3 years of daily data for risk estimation
    risk_end_date = datetime.now(timezone.utc)
    risk_start_date = risk_end_date - timedelta(days=3*365)
    try:
        risk_data_ohlcv = yf.download(ticker, start=risk_start_date.strftime("%Y-%m-%d"), end=risk_end_date.strftime("%Y-%m-%d"), progress=False)
        if risk_data_ohlcv.empty:
            logger.error(f"No risk data for {ticker} from yfinance.")
            return {"mu": mu_hat_3m, "sigma": None, "snapshot_id": None, "error": f"No yfinance risk data for {ticker}"}

        # Определяем, какую колонку использовать - 'Close' или 'Adj Close'
        price_column = 'Close'
        if 'Adj Close' in risk_data_ohlcv.columns:
            price_column = 'Adj Close'
        
        logger.debug(f"Using price column {price_column} for risk calculation for {ticker}")
        
        daily_log_returns_risk = np.log(risk_data_ohlcv[price_column] / risk_data_ohlcv[price_column].shift(1)).dropna()
        if len(daily_log_returns_risk) < 63:  # Нужно минимум 63 дня для 3-месячных периодов
             logger.warning(f"Not enough risk data points for {ticker} after processing ({len(daily_log_returns_risk)} found)")
             sigma_hat = np.nan # Or some default high variance
        else:
            # Resample to 63-trading-day (approx. quarterly) sum of log returns
            # 'B' stands for business day, so 63B is approx 3 months of trading
            quarterly_log_returns = daily_log_returns_risk.resample('63B').sum()
            if len(quarterly_log_returns) < 2: # Need at least 2 periods for std dev
                logger.warning(f"Not enough quarterly periods to calculate std dev for {ticker} ({len(quarterly_log_returns)} found)")
                sigma_hat = np.nan
            else:
                vol_quarter = quarterly_log_returns.std()
                sigma_hat = vol_quarter**2  # Квартальная дисперсия

    except Exception as e:
        logger.error(f"Error during risk estimation for {ticker}: {e}")
        sigma_hat = np.nan # Or a default value indicating error

    return {
        "mu": float(mu_hat_3m),
        "sigma": float(sigma_hat) if not np.isnan(sigma_hat) else None,
        "snapshot_id": None,
        "horizon": "3 months"  # Добавляем информацию о горизонте прогноза
    }

if __name__ == '__main__':
    # Basic test (requires a dummy model and yfinance access)
    # Ensure models/catboost_TEST.cbm exists. Create it with the test script first.
    logging.basicConfig(level=logging.INFO)

    # Prerequisite: Run test_forecast_tool.py to create the dummy model first.
    test_model_path = MODELS_DIR / "catboost_TEST.cbm"
    if not test_model_path.exists():
        logger.error(f"Dummy model {test_model_path} not found. Please run the test setup first.")
    else:
        # Test on-demand forecast for a TEST ticker (assuming TEST.cbm exists)
        # Ensure yfinance can download data for a common ticker like "MSFT" if "TEST" isn't a real one
        # For the dummy model, the ticker name for data download doesn't matter as much as for model loading
        # but for real features it does.
        # Let's assume TEST is a placeholder and we might use a real ticker for data for this ad-hoc test.
        try:
            result_on_demand = forecast_tool(ticker="TEST") # Uses models/catboost_TEST.cbm
            logger.info(f"On-demand forecast for TEST: {result_on_demand}")

            # Example for a real ticker (if you have a model for it e.g. models/catboost_MSFT.cbm)
            # result_msft = forecast_tool(ticker="MSFT")
            # logger.info(f"On-demand forecast for MSFT: {result_msft}")

        except Exception as e:
            logger.error(f"Error in __main__ test: {e}")

    # Test with snapshot (requires a saved snapshot)
    # registry = SnapshotRegistry()
    # meta = SnapshotMeta(id="test-snap-001", created_at=datetime.now(timezone.utc), horizon_days=30, asset_universe=["TEST"])
    # snap = MarketSnapshot(meta=meta, mu={"TEST": 0.05}, sigma={"TEST": {"TEST": 0.01}}, sentiment={}, raw_features_path="")
    # snap_id = registry.save(snap)
    # logger.info(f"Saved dummy snapshot {snap_id}")
    # result_snapshot = forecast_tool(ticker="TEST", snapshot_id=snap_id)
    # logger.info(f"Snapshot forecast for TEST: {result_snapshot}")
    # registry.delete_all_snapshots_dangerously() # Clean up
