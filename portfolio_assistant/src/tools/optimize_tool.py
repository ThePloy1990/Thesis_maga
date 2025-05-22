import logging
from typing import Dict, Optional

import pandas as pd
import numpy as np
from pypfopt import EfficientFrontier, BlackLittermanModel, expected_returns, risk_models

from src.market_snapshot.registry import SnapshotRegistry

logger = logging.getLogger(__name__)


def optimize_tool(
    snapshot_id: str,
    risk_aversion: float = 2.5,  # Used as delta for market-implied prior in BL
    method: str = "black_litterman",  # or "markowitz"
    max_weight: float = 0.4,
    risk_free_rate: float = 0.005  # Снижено с 0.02 до 0.005 для соответствия текущим низким доходностям
) -> Dict:
    """
    Optimizes a portfolio based on a given market snapshot.

    Args:
        snapshot_id: The ID of the market snapshot to use.
        risk_aversion: Risk aversion coefficient. Used for market-implied prior in Black-Litterman.
        method: Optimization method, either "black_litterman" or "markowitz".
        max_weight: Maximum weight for any single asset in the portfolio (0 to 1).
        risk_free_rate: The risk-free rate for Sharpe ratio calculation.

    Returns:
        A dictionary containing the optimized weights, expected portfolio return,
        portfolio risk (volatility), Sharpe ratio, and the snapshot_id used.
        Returns a dictionary with an 'error' key if optimization fails.
    """
    registry = SnapshotRegistry()
    snapshot = registry.load(snapshot_id)

    if not snapshot:
        logger.error(f"Snapshot with id '{snapshot_id}' not found.")
        return {"error": f"Snapshot '{snapshot_id}' not found", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}

    logger.info(f"Optimizing portfolio with method '{method}' using snapshot '{snapshot_id}'.")

    # Extract data from snapshot
    mu_dict = snapshot.mu
    sigma_dict = snapshot.sigma
    
    # Consistent asset order
    # Ensure all assets in mu are in sigma and vice-versa, or handle missing ones.
    # For simplicity, assume snapshot is well-formed and mu keys cover main assets in sigma.
    assets = list(mu_dict.keys())
    if not assets:
        logger.error(f"No assets found in mu for snapshot '{snapshot_id}'.")
        return {"error": "No assets in snapshot mu", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}

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
    S_final = S_df  # Use snapshot's covariance matrix for EF for both methods for now

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
    else:
        logger.error(f"Invalid optimization method: {method}. Choose 'black_litterman' or 'markowitz'.")
        return {"error": f"Invalid method: {method}", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}

    # Portfolio Optimization using EfficientFrontier
    if not (0 <= max_weight <= 1):
        logger.error(f"Invalid max_weight: {max_weight}. Must be between 0 and 1.")
        return {"error": f"Invalid max_weight: {max_weight}", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}
    
    weight_bounds = (0, max_weight)

    try:
        ef = EfficientFrontier(mu_final, S_final, weight_bounds=weight_bounds)
        ef.max_sharpe(risk_free_rate=risk_free_rate) # Optimize for max Sharpe ratio
        cleaned_weights = ef.clean_weights()
        
        # Portfolio performance
        # Returns: expected return, volatility, sharpe ratio
        perf_exp_ret, perf_risk, perf_sharpe = ef.portfolio_performance(verbose=False, risk_free_rate=risk_free_rate)

    except Exception as e:
        logger.error(f"EfficientFrontier optimization failed: {e}")
        return {"error": f"Optimization error: {e}", "weights": None, "exp_ret": None, "risk": None, "sharpe": None, "snapshot_id": snapshot_id}

    logger.info(f"Optimization successful. Weights: {cleaned_weights}")
    return {
        "weights": cleaned_weights,
        "exp_ret": perf_exp_ret,
        "risk": perf_risk,  # This is volatility (standard deviation)
        "sharpe": perf_sharpe,
        "snapshot_id": snapshot_id
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