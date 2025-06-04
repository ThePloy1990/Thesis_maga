import logging
from typing import Dict, Optional, List
from pathlib import Path

import pandas as pd
import numpy as np
from pypfopt import EfficientFrontier, BlackLittermanModel, expected_returns, risk_models
from pypfopt.hierarchical_portfolio import HRPOpt

# Исправляем импорт для работы со Streamlit
try:
    from ..market_snapshot.registry import SnapshotRegistry
except ImportError:
    # Альтернативный импорт для Streamlit
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'market_snapshot'))
    from registry import SnapshotRegistry

logger = logging.getLogger(__name__)


def optimize_tool(
    tickers: Optional[List[str]] = None,  # Список тикеров для оптимизации
    snapshot_id: str = None,  # ID снэпшота (опционально)
    risk_aversion: float = 1.0,  # Для совместимости, но не используется в HRP
    method: str = "hrp",  # "hrp", "black_litterman", "markowitz", или "target_return"
    max_weight: float = 0.4,  # Для non-HRP методов
    risk_free_rate: float = 0.001,  # Для расчета Sharpe
    min_weight: float = 0.01,  # Минимальный вес для HRP (фильтрация)
    target_return: float = None  # Целевая годовая доходность (например, 0.15 для 15%)
) -> Dict:
    """
    Optimizes a portfolio based on a given market snapshot.

    Args:
        tickers: List of tickers to optimize with. If provided, only these tickers will be used.
        snapshot_id: The ID of the market snapshot to use. If None, the latest snapshot is used.
        risk_aversion: Risk aversion coefficient. Used for market-implied prior in Black-Litterman (не используется в HRP).
        method: Optimization method: "hrp" (default), "black_litterman", "markowitz", or "target_return".
        max_weight: Maximum weight for any single asset in the portfolio (0 to 1) - только для non-HRP методов.
        risk_free_rate: The risk-free rate for Sharpe ratio calculation.
        min_weight: Minimum weight threshold for HRP - активы с меньшим весом исключаются.
        target_return: Target annual return for "target_return" method (e.g., 0.15 for 15%).

    Returns:
        A dictionary containing the optimized weights, expected portfolio return,
        portfolio risk (volatility), Sharpe ratio, and the snapshot_id used.
        Returns a dictionary with an 'error' key if optimization fails.
    """
    registry = SnapshotRegistry()
    
    # Если snapshot_id не указан, используем последний снэпшот
    if not snapshot_id:
        snapshot = registry.latest()
        if snapshot:
            snapshot_id = snapshot.meta.id
        else:
            logger.error("No snapshots found in registry.")
            return {"error": "No snapshots found", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": None}
    else:
        snapshot = registry.load(snapshot_id)

    if not snapshot:
        logger.error(f"Snapshot with id '{snapshot_id}' not found.")
        return {"error": f"Snapshot '{snapshot_id}' not found", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}

    logger.info(f"Optimizing portfolio with method '{method}' using snapshot '{snapshot_id}'.")

    # Проверяем доступность тикеров
    models_path = Path(__file__).absolute().parent.parent.parent.parent / "models"
    
    # Получаем список доступных тикеров из директории с моделями
    available_tickers = []
    for model_file in models_path.glob("catboost_*.cbm"):
        ticker = model_file.stem.replace("catboost_", "")
        if ticker:
            available_tickers.append(ticker)
    
    logger.info(f"Доступно {len(available_tickers)} тикеров для оптимизации")
    
    # Если предоставлен список тикеров, проверяем их наличие
    if tickers:
        valid_tickers = [t for t in tickers if t in available_tickers]
        invalid_tickers = [t for t in tickers if t not in available_tickers]
        
        if invalid_tickers:
            logger.warning(f"Следующие тикеры недоступны: {invalid_tickers}")
            if not valid_tickers:
                return {
                    "error": f"Ни один из указанных тикеров не доступен для оптимизации. Используйте доступные тикеры.",
                    "weights": None,
                    "exp_ret": None,
                    "risk": None,
                    "sharpe": None,
                    "snapshot_id": snapshot_id
                }
    
    # Extract data from snapshot
    mu_dict = snapshot.mu
    sigma_dict = snapshot.sigma
    
    # Фильтруем только доступные тикеры
    available_mu_tickers = [t for t in mu_dict.keys() if t in available_tickers]
    logger.info(f"В снэпшоте найдено {len(available_mu_tickers)} доступных тикеров")
    
    if tickers:
        # Если указаны конкретные тикеры, используем их пересечение с доступными
        assets = [t for t in tickers if t in available_mu_tickers]
        logger.info(f"Из {len(tickers)} указанных тикеров доступно {len(assets)} в снэпшоте и моделях")
    else:
        # Иначе используем все доступные тикеры из снэпшота
        assets = available_mu_tickers
    
    if not assets or len(assets) < 3:
        logger.error(f"Недостаточно доступных тикеров для оптимизации: {len(assets) if assets else 0}")
        return {
            "error": f"Требуется минимум 3 доступных тикера для оптимизации, найдено {len(assets) if assets else 0}",
            "weights": None,
            "exp_ret": None,
            "risk": None,
            "sharpe": None,
            "snapshot_id": snapshot_id
        }

    # Для HRP используем реальные исторические данные
    if method.lower() == "hrp":
        try:
            import yfinance as yf
            from datetime import datetime, timedelta, timezone
            
            logger.info(f"Using HRP optimization with {len(assets)} assets")
            
            # Загружаем реальные исторические данные для HRP (как в agent_integration.py)
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=365)  # Год исторических данных
            
            logger.info(f"Загружаем исторические данные с {start_date.strftime('%Y-%m-%d')} по {end_date.strftime('%Y-%m-%d')}")
            
            # Собираем исторические доходности для всех активов
            all_returns = {}
            
            for ticker in assets:
                try:
                    # Загружаем данные для отдельного тикера (как в agent_integration.py)
                    ticker_data = yf.download(
                        ticker, 
                        start=start_date.strftime("%Y-%m-%d"), 
                        end=end_date.strftime("%Y-%m-%d"),
                        progress=False,
                        auto_adjust=True
                    )
                    
                    # Пропускаем пустые данные
                    if ticker_data.empty:
                        logger.warning(f"No historical data for {ticker}, skipping")
                        continue
                    
                    # Получаем цены закрытия
                    close_column = 'Close'
                    if isinstance(ticker_data.columns, pd.MultiIndex):
                        # Обрабатываем MultiIndex формат
                        try:
                            close_prices = ticker_data.xs('Close', level=0, axis=1)
                            # Если получили DataFrame с одной колонкой, преобразуем в Series
                            if isinstance(close_prices, pd.DataFrame):
                                if close_prices.shape[1] == 1:
                                    close_prices = close_prices.iloc[:, 0]
                                else:
                                    # Если несколько колонок, берем первую (основной тикер)
                                    close_prices = close_prices.iloc[:, 0]
                        except Exception as e:
                            logger.error(f"Error accessing MultiIndex data for {ticker}: {e}")
                            continue
                    else:
                        # Обрабатываем обычный DataFrame
                        if close_column not in ticker_data.columns:
                            alternative_close = 'Adj Close' if 'Adj Close' in ticker_data.columns else None
                            if alternative_close:
                                close_column = alternative_close
                            else:
                                logger.warning(f"No price column found for {ticker}, skipping")
                                continue
                        close_prices = ticker_data[close_column]
                    
                    # Убеждаемся что close_prices это Series
                    if isinstance(close_prices, pd.DataFrame):
                        if close_prices.shape[1] == 1:
                            close_prices = close_prices.iloc[:, 0]
                        else:
                            logger.warning(f"Multiple price columns for {ticker}, taking first")
                            close_prices = close_prices.iloc[:, 0]
                    
                    # Получаем ежедневные логарифмические доходности
                    log_returns = np.log(close_prices / close_prices.shift(1)).dropna()
                    
                    # Убеждаемся что log_returns это Series
                    if isinstance(log_returns, pd.DataFrame):
                        if log_returns.shape[1] == 1:
                            log_returns = log_returns.iloc[:, 0]
                        else:
                            logger.warning(f"Multiple return columns for {ticker}, taking first")
                            log_returns = log_returns.iloc[:, 0]
                    
                    if len(log_returns) < 50:  # Минимум данных для HRP
                        logger.warning(f"Insufficient data for {ticker}: {len(log_returns)} days")
                        continue
                    
                    # Сохраняем для HRP
                    all_returns[ticker] = log_returns
                    logger.debug(f"Loaded {len(log_returns)} returns for {ticker}")
                    
                except Exception as e:
                    logger.warning(f"Error loading data for {ticker}: {e}")
                    continue
            
            # Проверяем что у нас достаточно данных
            if len(all_returns) < 3:
                return {
                    "error": f"Недостаточно исторических данных для HRP: получены данные только для {len(all_returns)} активов",
                    "weights": None,
                    "exp_ret": None,
                    "risk": None,
                    "sharpe": None,
                    "snapshot_id": snapshot_id
                }
            
            # Создаем общий индекс для всех рядов (как в agent_integration.py)
            common_index = pd.DatetimeIndex([])
            for ticker, returns in all_returns.items():
                common_index = common_index.union(returns.index)
            
            # Создаем DataFrame с общим индексом и заполняем его доходностями
            returns_df = pd.DataFrame(index=common_index)
            for ticker, returns in all_returns.items():
                returns_df[ticker] = returns
            
            # Убираем строки где все значения NaN
            returns_df = returns_df.dropna(how='all')
            
            # Проверяем качество данных
            if returns_df.empty:
                return {
                    "error": "Исторические данные пусты после обработки",
                    "weights": None,
                    "exp_ret": None,
                    "risk": None,
                    "sharpe": None,
                    "snapshot_id": snapshot_id
                }
            
            logger.info(f"Подготовлен dataset с {len(returns_df)} наблюдениями для {len(returns_df.columns)} активов")
            
            # Обновляем список активов только теми, для которых есть данные
            assets = [ticker for ticker in assets if ticker in returns_df.columns]
            returns_df = returns_df[assets]
            
            # Создаем HRP оптимизатор с реальными историческими данными
            hrp = HRPOpt(returns_df)
            
            # Оптимизация
            weights = hrp.optimize()
            
            # Фильтруем веса менее min_weight
            weights = {ticker: weight for ticker, weight in weights.items() 
                      if weight >= min_weight}
            
            # Перенормализуем веса после фильтрации
            total_weight = sum(weights.values())
            if total_weight > 0:
                weights = {ticker: weight/total_weight for ticker, weight in weights.items()}
            else:
                logger.error("All weights filtered out - reducing min_weight threshold")
                # Берем топ-N активов если все веса слишком малы
                original_weights = hrp.optimize()
                sorted_weights = sorted(original_weights.items(), key=lambda x: x[1], reverse=True)
                top_n = min(10, len(sorted_weights))  # Берем топ-10 или все доступные
                weights = dict(sorted_weights[:top_n])
                total_weight = sum(weights.values())
                weights = {ticker: weight/total_weight for ticker, weight in weights.items()}
            
            logger.info(f"HRP optimization successful. Active assets: {len(weights)}")
            
            # Рассчитываем ожидаемые метрики портфеля используя mu и sigma из snapshot
            portfolio_mu = sum(mu_dict[ticker] * weight for ticker, weight in weights.items())
            
            # Получаем ковариационную матрицу из snapshot для расчета риска
            cov_matrix = pd.DataFrame(sigma_dict).loc[assets, assets]
            
            # Рассчитываем волатильность портфеля через ковариационную матрицу
            weight_vector = pd.Series(index=assets, data=0.0)
            for ticker, weight in weights.items():
                weight_vector[ticker] = weight
            
            # Используем ковариационную матрицу из snapshot для расчета риска
            portfolio_variance = weight_vector.T @ cov_matrix @ weight_vector
            portfolio_risk = np.sqrt(portfolio_variance)
            
            # Sharpe ratio
            sharpe_ratio = (portfolio_mu - risk_free_rate) / portfolio_risk if portfolio_risk > 0 else 0
            
            return {
                "weights": weights,
                "exp_ret": float(portfolio_mu),
                "risk": float(portfolio_risk),
                "sharpe": float(sharpe_ratio),
                "snapshot_id": snapshot_id,
                "method": "HRP"
            }
            
        except Exception as e:
            logger.error(f"HRP optimization failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"error": f"HRP optimization error: {e}", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}

    # Для остальных методов (Markowitz, Black-Litterman) используем старую логику
    try:
        # Convert mu to Series and sigma to DataFrame
        mu_series = pd.Series(mu_dict).loc[assets] # Ensure order
        S_df = pd.DataFrame(sigma_dict).loc[assets, assets] # Ensure order and square matrix
        
        # Validate inputs for PyPortfolioOpt
        if not isinstance(mu_series, pd.Series):
            raise ValueError("Expected returns (mu) must be a pandas Series.")
        if not isinstance(S_df, pd.DataFrame):
            raise ValueError("Covariance matrix (S) must be a pandas DataFrame.")
        if S_df.shape != (len(assets), len(assets)):
            raise ValueError("Covariance matrix shape mismatch with number of assets.")
        if S_df.index.tolist() != assets or S_df.columns.tolist() != assets:
            raise ValueError("Covariance matrix index/columns do not match asset list.")

        # Check for positive definiteness, fix if necessary
        S_df = risk_models.fix_nonpositive_semidefinite(S_df, fix_method='spectral')

    except Exception as e:
        logger.error(f"Error processing mu/sigma from snapshot '{snapshot_id}': {e}")
        return {"error": f"Data processing error: {e}", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}

    # Determine mu_final and S_final based on method
    S_final = S_df

    if method.lower() == "black_litterman":
        tau = 0.05  # As specified
        logger.info(f"Using Black-Litterman: tau={tau}, risk_aversion (for prior delta)={risk_aversion}")
        
        # For demo, use equal market caps.
        mcaps = pd.Series({asset: 1.0 for asset in assets}) 
        
        # Views (Q) are from snapshot.mu
        Q = mu_series

        # P matrix (identity if views are for each asset directly)
        P = np.eye(len(assets))

        # Omega: uncertainty of views. Diagonal matrix, proportional to tau * variances from S_df.
        omega_diag = tau * np.diag(S_df) 
        omega = np.diag(omega_diag) 

        try:
            # Pass market_caps and risk_aversion (as delta) directly to the model
            bl = BlackLittermanModel(
                cov_matrix=S_df, 
                # pi=pi, # Let the model calculate pi if not provided or provide market_caps and delta
                Q=Q, 
                P=P, 
                omega=omega, 
                tau=tau,
                market_caps=mcaps, # Provide market caps
                delta=risk_aversion # Provide risk aversion as delta
            )
            mu_final = bl.bl_returns() # Posterior expected returns
            # S_final = bl.bl_cov() # Optionally use posterior covariance matrix
        except Exception as e:
            logger.error(f"Black-Litterman model calculation failed: {e}")
            return {"error": f"BL model error: {e}", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}

    elif method.lower() == "markowitz":
        logger.info("Using Markowitz optimization with snapshot mu.")
        mu_final = mu_series
    elif method.lower() == "target_return":
        logger.info("Using Target Return optimization with snapshot mu.")
        mu_final = mu_series
    else:
        logger.error(f"Invalid optimization method: {method}. Choose 'hrp', 'black_litterman', 'markowitz', or 'target_return'.")
        return {"error": f"Invalid method: {method}", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}

    # Portfolio Optimization using EfficientFrontier
    if not (0 <= max_weight <= 1):
        logger.error(f"Invalid max_weight: {max_weight}. Must be between 0 and 1.")
        return {"error": f"Invalid max_weight: {max_weight}", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}
    
    weight_bounds = (0, max_weight)

    try:
        ef = EfficientFrontier(mu_final, S_final, weight_bounds=weight_bounds)
        
        # Выбираем метод оптимизации
        if method.lower() == "target_return":
            if target_return is None:
                logger.error("target_return must be specified for target_return method")
                return {"error": "target_return parameter required for target_return method", 
                       "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}
            
            logger.info(f"Optimizing for target return: {target_return:.2%}")
            
            # Проверяем, достижима ли целевая доходность
            min_ret = mu_final.min()
            max_ret = mu_final.max()
            if target_return < min_ret or target_return > max_ret:
                logger.warning(f"Target return {target_return:.2%} is outside feasible range [{min_ret:.2%}, {max_ret:.2%}]")
                # Клампируем к допустимому диапазону
                target_return = max(min_ret, min(max_ret, target_return))
                logger.info(f"Adjusted target return to: {target_return:.2%}")
            
            try:
                ef.efficient_return(target_return=target_return)
            except Exception as e:
                logger.error(f"Failed to optimize for target return {target_return:.2%}: {e}")
                # Fallback to max Sharpe if target return optimization fails
                logger.info("Falling back to max Sharpe optimization")
                ef.max_sharpe(risk_free_rate=risk_free_rate)
        else:
            # Стандартная оптимизация по максимальному Sharpe ratio
            ef.max_sharpe(risk_free_rate=risk_free_rate)
        
        cleaned_weights = ef.clean_weights()
        
        # Portfolio performance
        # Returns: expected return, volatility, sharpe ratio
        perf_exp_ret, perf_risk, perf_sharpe = ef.portfolio_performance(verbose=False, risk_free_rate=risk_free_rate)

    except Exception as e:
        logger.error(f"EfficientFrontier optimization failed: {e}")
        return {"error": f"Optimization error: {e}", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}

    logger.info(f"Optimization successful. Weights: {cleaned_weights}")
    method_name = method.upper() if method.lower() != "target_return" else f"Target Return ({target_return:.1%})"
    return {
        "weights": cleaned_weights,
        "exp_ret": perf_exp_ret,
        "risk": perf_risk,  # This is volatility (standard deviation)
        "sharpe": perf_sharpe,
        "snapshot_id": snapshot_id,
        "method": method_name
    }

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # This is a basic test. For proper testing, use pytest and fixtures.
    # Ensure you have a SnapshotRegistry setup and a valid snapshot_id.

    # Create a dummy snapshot for testing (manual version of what test fixture would do)
    registry = SnapshotRegistry() # Assumes default Redis and S3 stub path
    # Clean up previous test data if any
    # registry.delete_all_snapshots_dangerously() 

    from datetime import datetime, timezone
    from src.market_snapshot.model import SnapshotMeta, MarketSnapshot

    assets_test = ["TICKA", "TICKB", "TICKC"]
    mu_test = {asset: np.random.uniform(0.01, 0.2) for asset in assets_test}
    # Create a somewhat realistic covariance matrix
    S_test_array = np.array([[0.01, 0.002, 0.001],
                             [0.002, 0.02, 0.003],
                             [0.001, 0.003, 0.005]])
    S_test = pd.DataFrame(S_test_array, index=assets_test, columns=assets_test).to_dict()

    test_snap_meta = SnapshotMeta(
        id="optimize_tool_test_snap_001",
        created_at=datetime.now(timezone.utc),
        horizon_days=30,
        asset_universe=assets_test
    )
    test_snap_data = MarketSnapshot(
        meta=test_snap_meta,
        mu=mu_test,
        sigma=S_test,
        sentiment={asset: np.random.uniform(-0.5, 0.5) for asset in assets_test},
        raw_features_path="/path/to/dummy_features_for_opt_test.csv"
    )
    
    try:
        # Ensure registry paths are writable and Redis is running
        saved_id = registry.save(test_snap_data)
        logger.info(f"Saved dummy snapshot for optimize_tool test: {saved_id}")

        # Test Markowitz
        logger.info("\nTesting Markowitz optimization...")
        result_markowitz = optimize_tool(snapshot_id=saved_id, method="markowitz", max_weight=0.5)
        if result_markowitz.get("error"):
            logger.error(f"Markowitz Error: {result_markowitz['error']}")
        else:
            logger.info(f"Markowitz Result: {result_markowitz}")
            assert sum(result_markowitz['weights'].values()) == pytest.approx(1.0, abs=1e-5)
            assert max(result_markowitz['weights'].values()) <= 0.5

        # Test Black-Litterman
        logger.info("\nTesting Black-Litterman optimization...")
        result_bl = optimize_tool(snapshot_id=saved_id, method="black_litterman", max_weight=0.35, risk_aversion=3.0)
        if result_bl.get("error"):
            logger.error(f"Black-Litterman Error: {result_bl['error']}")
        else:
            logger.info(f"Black-Litterman Result: {result_bl}")
            assert sum(result_bl['weights'].values()) == pytest.approx(1.0, abs=1e-5)
            assert max(result_bl['weights'].values()) <= 0.35
            
    except ConnectionRefusedError:
        logger.error("Redis connection refused. Ensure Redis is running for the __main__ test.")
    except Exception as e:
        logger.error(f"Error in __main__ example: {e}", exc_info=True)
    finally:
        # Clean up the test snapshot
        # if 'saved_id' in locals() and saved_id:
        #    pass # In a real test, you would delete or use a test-specific registry
        logger.info("__main__ test finished. Consider using pytest for thorough testing.") 