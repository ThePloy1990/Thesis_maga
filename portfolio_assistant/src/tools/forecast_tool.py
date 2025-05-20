import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from pathlib import Path

import yfinance as yf
import pandas as pd
import numpy as np
import pandas_ta as ta
from catboost import CatBoostRegressor

from src.market_snapshot.registry import SnapshotRegistry
from src.market_snapshot.model import MarketSnapshot # Assuming this might be needed if we enhance snapshot interaction

logger = logging.getLogger(__name__)

# Define feature columns for consistency with model training
# These names must match the features the CatBoost model was trained on.
FEATURE_COLUMNS = [
    'ret_1d', 'ret_5d', 'ret_21d',
    'SMA_5', 'SMA_10', 'SMA_20',
    'EMA_5', 'EMA_10', 'EMA_20',
    'VOL_21D', 'RSI_14'
]

MODELS_DIR = Path("models") # Assuming models directory is at the project root


def _calculate_features(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    """
    Calculates financial features for the given DataFrame.
    Returns a DataFrame with a single row of the latest features, or None if data is insufficient.
    """
    if df.empty or len(df) < 60: # Need enough data for lookbacks and indicators
        logger.warning(f"Insufficient data for {ticker} to calculate all features (need at least 60 days, got {len(df)}).")
        return None

    # Use Adj Close for calculations
    adj_close = df['Adj Close']

    # Log returns
    log_returns = np.log(adj_close / adj_close.shift(1))
    df['log_ret'] = log_returns

    features = pd.DataFrame(index=[df.index[-1]]) # Single row for the last day

    features['ret_1d'] = log_returns.iloc[-1]
    features['ret_5d'] = log_returns.rolling(window=5).sum().iloc[-1]
    features['ret_21d'] = log_returns.rolling(window=21).sum().iloc[-1]

    # SMA, EMA, RSI using pandas_ta
    # pandas_ta might add columns directly to df or return a new df, handle accordingly.
    # For safety, we calculate and then assign the last value.
    df.ta.sma(length=5, append=True, col_names=("SMA_5",))
    df.ta.sma(length=10, append=True, col_names=("SMA_10",))
    df.ta.sma(length=20, append=True, col_names=("SMA_20",))

    df.ta.ema(length=5, append=True, col_names=("EMA_5",))
    df.ta.ema(length=10, append=True, col_names=("EMA_10",))
    df.ta.ema(length=20, append=True, col_names=("EMA_20",))

    df.ta.rsi(length=14, append=True, col_names=("RSI_14",))
    
    # Volatility (21-day standard deviation of daily log returns)
    df['VOL_21D'] = log_returns.rolling(window=21).std()

    # Assign the latest values to the features DataFrame
    for col in ['SMA_5', 'SMA_10', 'SMA_20', 'EMA_5', 'EMA_10', 'EMA_20', 'RSI_14', 'VOL_21D']:
        if col in df.columns:
            features[col] = df[col].iloc[-1]
        else:
            logger.error(f"Feature column {col} not found after pandas_ta calculation for {ticker}.")
            return None # Or fill with NaN, depending on model robustness
            
    # Ensure all expected columns are present
    for col in FEATURE_COLUMNS:
        if col not in features.columns:
            logger.error(f"Expected feature column {col} is missing for {ticker}.")
            return None

    return features[FEATURE_COLUMNS] # Return in defined order


def forecast_tool(
    ticker: str,
    snapshot_id: Optional[str] = None,
    lookback_days: int = 180 # For feature calculation if on-demand
) -> Dict:
    """
    Provides a 1-month log-return forecast (mu) and its variance (sigma)
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
        Example: {"mu": 0.032, "sigma": 0.0049, "snapshot_id": "2023-01-01T12-00-00Z"}
    """
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
    logger.info(f"Generating on-demand forecast for {ticker} (lookback: {lookback_days} days)")
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
        mu_hat = model.predict(prediction_features_df)[0]
    except Exception as e:
        logger.error(f"Error during model prediction for {ticker}: {e}")
        return {"mu": None, "sigma": None, "snapshot_id": None, "error": f"Model prediction error for {ticker}"}

    # Estimate risk (sigma_hat = monthly variance)
    # Download 3 years of daily data for risk estimation
    risk_end_date = datetime.now(timezone.utc)
    risk_start_date = risk_end_date - timedelta(days=3*365)
    try:
        risk_data_ohlcv = yf.download(ticker, start=risk_start_date.strftime("%Y-%m-%d"), end=risk_end_date.strftime("%Y-%m-%d"), progress=False)
        if risk_data_ohlcv.empty:
            logger.error(f"No risk data for {ticker} from yfinance.")
            return {"mu": mu_hat, "sigma": None, "snapshot_id": None, "error": f"No yfinance risk data for {ticker}"}
        
        daily_log_returns_risk = np.log(risk_data_ohlcv['Adj Close'] / risk_data_ohlcv['Adj Close'].shift(1)).dropna()
        if len(daily_log_returns_risk) < 21:
             logger.warning(f"Not enough risk data points for {ticker} after processing ({len(daily_log_returns_risk)} found)")
             sigma_hat = np.nan # Or some default high variance
        else:
            # Resample to 21-trading-day (approx. monthly) sum of log returns
            # 'B' stands for business day, so 21B is approx 1 month of trading
            monthly_log_returns = daily_log_returns_risk.resample('21B').sum()
            if len(monthly_log_returns) < 2: # Need at least 2 periods for std dev
                logger.warning(f"Not enough monthly periods to calculate std dev for {ticker} ({len(monthly_log_returns)} found)")
                sigma_hat = np.nan
            else:
                vol_month = monthly_log_returns.std()
                sigma_hat = vol_month**2

    except Exception as e:
        logger.error(f"Error during risk estimation for {ticker}: {e}")
        sigma_hat = np.nan # Or a default value indicating error

    return {
        "mu": float(mu_hat),
        "sigma": float(sigma_hat) if not np.isnan(sigma_hat) else None,
        "snapshot_id": None
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