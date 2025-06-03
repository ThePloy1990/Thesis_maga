import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import shutil
import logging
from datetime import datetime, timezone

from src.tools.optimize_tool import optimize_tool
from src.market_snapshot.registry import SnapshotRegistry
from src.market_snapshot.model import MarketSnapshot, SnapshotMeta

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Define a consistent path for test S3 stubs for this test file
TEST_OPTIMIZE_S3_STUB_PATH = "local_test/snapshots_optimize_tool"

@pytest.fixture(scope="function")
def test_snapshot_registry() -> SnapshotRegistry:
    """Provides a clean SnapshotRegistry instance for each test function."""
    if Path(TEST_OPTIMIZE_S3_STUB_PATH).exists():
        shutil.rmtree(TEST_OPTIMIZE_S3_STUB_PATH)
    Path(TEST_OPTIMIZE_S3_STUB_PATH).mkdir(parents=True, exist_ok=True)

    registry = SnapshotRegistry(s3_stub_path=TEST_OPTIMIZE_S3_STUB_PATH)
    # Clear Redis keys that this registry might use (based on its default prefix)
    # This is a simplified cleanup for testing; assumes no critical data on test Redis DB 0.
    test_snapshot_prefix = registry._snapshot_key_prefix # e.g., "snapshot:"
    keys_to_delete = registry.redis_client.keys(f"{test_snapshot_prefix}optimize_test_snap_*")
    if keys_to_delete:
        registry.redis_client.delete(*keys_to_delete)

    yield registry

    # Teardown: clean S3 stub and Redis keys again if needed, though isolated by function scope
    if Path(TEST_OPTIMIZE_S3_STUB_PATH).exists():
        shutil.rmtree(TEST_OPTIMIZE_S3_STUB_PATH)
    keys_to_delete = registry.redis_client.keys(f"{test_snapshot_prefix}optimize_test_snap_*")
    if keys_to_delete:
        registry.redis_client.delete(*keys_to_delete)

@pytest.fixture(scope="function")
def dummy_snapshot_id(test_snapshot_registry: SnapshotRegistry) -> str:
    """Creates a dummy snapshot with 3 assets and returns its ID."""
    registry = test_snapshot_registry
    
    # Используем реальные тикеры, для которых есть модели в папке models
    assets = ["T", "JNJ", "PG"]

    # More realistic means and covariance for testing
    mu_data = {
        "T": 0.12,
        "JNJ": 0.18,
        "PG": 0.09
    }

    # Ensure positive definite covariance matrix
    sigma_data_array = np.array([
        [0.050, 0.015, 0.008],  # Var(T), Cov(T,JNJ), Cov(T,PG)
        [0.015, 0.065, 0.012],  # Cov(JNJ,T), Var(JNJ), Cov(JNJ,PG)
        [0.008, 0.012, 0.040]   # Cov(PG,T), Cov(PG,JNJ), Var(PG)
    ])
    # Check positive definiteness (all eigenvalues positive)
    eigenvalues = np.linalg.eigvals(sigma_data_array)
    if not np.all(eigenvalues > 0):
        # Basic fix: add small value to diagonal if not positive definite
        # PyPortfolioOpt's fix_nonpositive_semidefinite is more robust but applied inside the tool.
        # For test data, simple adjustment might be enough or ensure data is well-formed.
        logger.warning("Test covariance matrix not positive definite. Adding small epsilon to diagonal.")
        sigma_data_array += np.eye(len(assets)) * 1e-6

    sigma_data = pd.DataFrame(sigma_data_array, index=assets, columns=assets).to_dict()

    meta = SnapshotMeta(
        id="optimize_test_snap_001", # Fixed ID for predictability in tests
        created_at=datetime.now(timezone.utc),
        horizon_days=21, # Approx 1 month
        asset_universe=assets
    )
    snapshot = MarketSnapshot(
        meta=meta,
        mu=mu_data,
        sigma=sigma_data,
        sentiment={asset: 0.1 for asset in assets}, # Dummy sentiment
        raw_features_path="/dev/null"
    )
    saved_id = registry.save(snapshot)
    logger.info(f"Saved dummy snapshot for optimize_tool test: {saved_id}")
    return saved_id


def test_optimize_tool_markowitz(dummy_snapshot_id: str):
    """Test Markowitz optimization."""
    snapshot_id = dummy_snapshot_id
    max_w = 0.6 # Test with a different max_weight
    result = optimize_tool(snapshot_id=snapshot_id, method="markowitz", max_weight=max_w)
    logger.info(f"Markowitz test result: {result}")

    assert "error" not in result or result["error"] is None, f"Optimization failed: {result.get('error')}"
    assert result["weights"] is not None
    assert result["snapshot_id"] == snapshot_id
    weights_sum = sum(result["weights"].values())
    assert weights_sum == pytest.approx(1.0, abs=1.1e-5), f"Sum of weights {weights_sum} is not approximately 1."
    assert max(result["weights"].values()) <= max_w + 1e-5 # Add tolerance for float precision
    assert result["exp_ret"] is not None
    assert result["risk"] is not None
    assert result["sharpe"] is not None


def test_optimize_tool_black_litterman(dummy_snapshot_id: str):
    """Test Black-Litterman optimization."""
    snapshot_id = dummy_snapshot_id
    max_w = 0.45 # Test with a different max_weight
    risk_aversion_test = 3.0

    result = optimize_tool(
        snapshot_id=snapshot_id,
        method="black_litterman",
        risk_aversion=risk_aversion_test,
        max_weight=max_w
    )
    logger.info(f"Black-Litterman test result: {result}")

    assert "error" not in result or result["error"] is None, f"Optimization failed: {result.get('error')}"
    assert result["weights"] is not None
    assert result["snapshot_id"] == snapshot_id
    weights_sum = sum(result["weights"].values())
    assert weights_sum == pytest.approx(1.0, abs=1.1e-5), f"Sum of weights {weights_sum} is not approximately 1."
    assert max(result["weights"].values()) <= max_w + 1e-5
    assert result["exp_ret"] is not None
    assert result["risk"] is not None
    assert result["sharpe"] is not None


def test_optimize_tool_hrp(dummy_snapshot_id: str):
    """Test HRP (Hierarchical Risk Parity) optimization."""
    snapshot_id = dummy_snapshot_id
    min_w = 0.05  # Minimum weight threshold for HRP

    result = optimize_tool(
        snapshot_id=snapshot_id,
        method="hrp",
        min_weight=min_w
    )
    logger.info(f"HRP test result: {result}")

    assert "error" not in result or result["error"] is None, f"HRP optimization failed: {result.get('error')}"
    assert result["weights"] is not None
    assert result["snapshot_id"] == snapshot_id
    weights_sum = sum(result["weights"].values())
    assert weights_sum == pytest.approx(1.0, abs=1.1e-5), f"Sum of weights {weights_sum} is not approximately 1."
    # HRP doesn't use max_weight constraint, so we just check all weights are positive
    assert all(w > 0 for w in result["weights"].values()), "All HRP weights should be positive"
    assert result["exp_ret"] is not None
    assert result["risk"] is not None
    assert result["sharpe"] is not None
    assert result["method"] == "HRP"


def test_optimize_tool_invalid_method(dummy_snapshot_id: str):
    """Test with an invalid optimization method."""
    snapshot_id = dummy_snapshot_id
    result = optimize_tool(snapshot_id=snapshot_id, method="invalid_method_name")
    logger.info(f"Invalid method test result: {result}")
    assert result["error"] is not None
    assert "Invalid method" in result["error"]
    assert result["weights"] is None


def test_optimize_tool_snapshot_not_found():
    """Test with a non-existent snapshot ID."""
    non_existent_id = "this_id_does_not_exist_12345"
    result = optimize_tool(snapshot_id=non_existent_id)
    logger.info(f"Snapshot not found test result: {result}")
    assert result["error"] is not None
    assert f"Snapshot '{non_existent_id}' not found" in result["error"]
    assert result["weights"] is None


def test_optimize_tool_invalid_max_weight(dummy_snapshot_id: str):
    """Test with an invalid max_weight parameter."""
    snapshot_id = dummy_snapshot_id
    result = optimize_tool(snapshot_id=snapshot_id, method="markowitz", max_weight=1.5) # max_weight > 1
    logger.info(f"Invalid max_weight (too high) test result: {result}")
    assert result["error"] is not None
    assert "Invalid max_weight" in result["error"]

    result_low = optimize_tool(snapshot_id=snapshot_id, method="markowitz", max_weight=-0.1) # max_weight < 0
    logger.info(f"Invalid max_weight (too low) test result: {result_low}")
    assert result_low["error"] is not None
    assert "Invalid max_weight" in result_low["error"]

# Note: For Black-Litterman, the quality of results heavily depends on the views (Q),
# prior (pi), and uncertainties (Omega). The dummy data might produce simplistic or
# sometimes non-intuitive BL results. Real-world scenarios require careful calibration.
