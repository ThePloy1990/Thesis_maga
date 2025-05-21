import pytest
import uuid
import copy
import os
import shutil
import json
from datetime import datetime, timezone
from typing import Dict, List, Any

# Импортируем внутреннюю логику для прямого тестирования
from src.tools.scenario_tool import _internal_scenario_adjust_tool_logic as scenario_adjust_tool_impl
from src.market_snapshot.snapshot_registry import SnapshotRegistry
from src.market_snapshot.model import MarketSnapshot, SnapshotMeta

# Константа для пути к тестовому S3 стабу для этого модуля тестов
TEST_S3_STUB_PATH_SCENARIO = "local_test/snapshots_scenario_tool"
# Конфигурация Redis
REDIS_HOST = "localhost"
REDIS_PORT = 6379

@pytest.fixture(scope="function")
def registry_and_cleanup_scenario():
    if not os.path.exists(TEST_S3_STUB_PATH_SCENARIO):
        os.makedirs(TEST_S3_STUB_PATH_SCENARIO)
    
    registry = SnapshotRegistry(
        redis_host=REDIS_HOST, 
        redis_port=REDIS_PORT, 
        s3_stub_path=TEST_S3_STUB_PATH_SCENARIO
    )
    if registry.redis_client:
        keys_to_delete = registry.redis_client.keys("snapshot:*")
        if keys_to_delete:
            registry.redis_client.delete(*keys_to_delete)

    yield registry

    if registry.redis_client:
        keys_to_delete = registry.redis_client.keys("snapshot:*") 
        if keys_to_delete:
            registry.redis_client.delete(*keys_to_delete)
            
    if os.path.exists(TEST_S3_STUB_PATH_SCENARIO):
        shutil.rmtree(TEST_S3_STUB_PATH_SCENARIO)

@pytest.fixture(scope="function")
def base_snapshot_data_dict() -> Dict:
    """Данные для создания базового MarketSnapshot в виде словаря."""
    return {
        "meta": {
            "id": f"test_base_snap_for_scenario_{uuid.uuid4().hex[:8]}", # Уникальный ID для каждого запуска
            "created_at": datetime.now(timezone.utc).isoformat(),
            "asset_universe": ["AAPL", "MSFT", "GOOG"],
            "horizon_days": 30,
            "description": "Base snapshot for scenario tests",
            "source": "test_fixture"
        },
        "mu": {"AAPL": 0.01, "MSFT": 0.015, "GOOG": 0.02},
        "sigma": {
            "AAPL": {"AAPL": 0.0025, "MSFT": 0.0001, "GOOG": 0.0002},
            "MSFT": {"AAPL": 0.0001, "MSFT": 0.0036, "GOOG": 0.0003},
            "GOOG": {"AAPL": 0.0002, "MSFT": 0.0003, "GOOG": 0.0049},
        },
        "market_caps": {"AAPL": 2.5e12, "MSFT": 2.0e12, "GOOG": 1.8e12},
        "prices": {"AAPL": 150.0, "MSFT": 300.0, "GOOG": 2500.0},
        "sentiment": {"AAPL": 0.5, "MSFT": 0.6, "GOOG": 0.7}, 
        "raw_features_path": f"/path/to/dummy_features_{uuid.uuid4().hex[:4]}.csv"
    }

@pytest.fixture(scope="function")
def saved_base_snapshot(registry_and_cleanup_scenario: SnapshotRegistry, base_snapshot_data_dict: Dict) -> MarketSnapshot:
    registry = registry_and_cleanup_scenario
    current_meta_data_dict = copy.deepcopy(base_snapshot_data_dict["meta"])
    current_data_dict = copy.deepcopy(base_snapshot_data_dict)

    if isinstance(current_meta_data_dict["created_at"], str):
        current_meta_data_dict["created_at"] = datetime.fromisoformat(current_meta_data_dict["created_at"])
    
    base_meta = SnapshotMeta(**current_meta_data_dict)
    
    base_snap = MarketSnapshot(
        meta=base_meta,
        mu=current_data_dict["mu"],
        sigma=current_data_dict["sigma"],
        market_caps=current_data_dict.get("market_caps"),
        prices=current_data_dict.get("prices"),
        sentiment=current_data_dict["sentiment"], 
        raw_features_path=current_data_dict["raw_features_path"] 
    )
    registry.save(base_snap)
    return base_snap

def test_successful_adjustment_and_save(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    registry = registry_and_cleanup_scenario
    original_id = saved_base_snapshot.meta.id
    
    adjustments_data = [
        {"ticker": "AAPL", "delta": 0.005},
        {"ticker": "MSFT", "delta": -0.002}
    ]
    deltas_json_str = json.dumps(adjustments_data)
    expected_deltas_dict = {"AAPL": 0.005, "MSFT": -0.002}

    new_snapshot_id = scenario_adjust_tool_impl(snapshot_id=original_id, deltas_json_string=deltas_json_str)

    base_id_for_new = original_id.split('-scn-')[0] 
    expected_prefix = base_id_for_new + "-scn-"
    assert new_snapshot_id.startswith(expected_prefix)
    hash_part = new_snapshot_id[len(expected_prefix):]
    assert len(hash_part) == 8

    scenario_snap: MarketSnapshot = registry.load(new_snapshot_id)
    assert scenario_snap is not None
    assert scenario_snap.meta.id == new_snapshot_id

    assert scenario_snap.mu["AAPL"] == pytest.approx(saved_base_snapshot.mu["AAPL"] + expected_deltas_dict["AAPL"])
    assert scenario_snap.mu["MSFT"] == pytest.approx(saved_base_snapshot.mu["MSFT"] + expected_deltas_dict["MSFT"])
    assert scenario_snap.mu["GOOG"] == pytest.approx(saved_base_snapshot.mu["GOOG"])

    assert scenario_snap.sigma == saved_base_snapshot.sigma
    assert scenario_snap.meta.asset_universe == saved_base_snapshot.meta.asset_universe
    assert scenario_snap.meta.horizon_days == saved_base_snapshot.meta.horizon_days
    assert scenario_snap.meta.created_at > saved_base_snapshot.meta.created_at
    assert scenario_snap.meta.source == "scenario_adjustment_tool"
    assert scenario_snap.meta.description.startswith(f"Scenario based on {original_id}")
    
    # Проверка properties, если они есть в модели SnapshotMeta и были добавлены scenario_tool
    if hasattr(scenario_snap.meta, 'properties') and scenario_snap.meta.properties: 
        assert scenario_snap.meta.properties.get("base_snapshot_id") == original_id
        assert scenario_snap.meta.properties.get("applied_deltas") == expected_deltas_dict

    original_reloaded: MarketSnapshot = registry.load(original_id)
    assert original_reloaded.mu == saved_base_snapshot.mu 

def test_adjust_ticker_not_in_snapshot(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot, capsys):
    registry = registry_and_cleanup_scenario
    original_id = saved_base_snapshot.meta.id
    adjustments_data = [
        {"ticker": "NEWCO", "delta": 0.05},
        {"ticker": "AAPL", "delta": 0.001}
    ]
    deltas_json_str = json.dumps(adjustments_data)
    expected_AAPL_delta = 0.001

    new_snapshot_id = scenario_adjust_tool_impl(snapshot_id=original_id, deltas_json_string=deltas_json_str)
    
    captured = capsys.readouterr()
    assert "Warning: Ticker 'NEWCO' in deltas not found in original snapshot's mu. Adjustment for this ticker will be skipped." in captured.out

    scenario_snap: MarketSnapshot = registry.load(new_snapshot_id)
    assert scenario_snap is not None
    assert "NEWCO" not in scenario_snap.mu 
    assert scenario_snap.mu["AAPL"] == pytest.approx(saved_base_snapshot.mu["AAPL"] + expected_AAPL_delta)

def test_base_snapshot_not_found(registry_and_cleanup_scenario: SnapshotRegistry):
    non_existent_id = "id_that_does_not_exist"
    deltas_json_str = json.dumps([{"ticker": "AAPL", "delta": 0.01}])
    with pytest.raises(ValueError, match=f"Snapshot with ID '{non_existent_id}' not found."):
        scenario_adjust_tool_impl(snapshot_id=non_existent_id, deltas_json_string=deltas_json_str)

def test_empty_deltas_list_in_json_string(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    registry = registry_and_cleanup_scenario
    original_id = saved_base_snapshot.meta.id
    deltas_json_str = json.dumps([]) 

    new_snapshot_id = scenario_adjust_tool_impl(snapshot_id=original_id, deltas_json_string=deltas_json_str)
    base_id_for_new = original_id.split('-scn-')[0]
    expected_prefix = base_id_for_new + "-scn-"
    assert new_snapshot_id.startswith(expected_prefix)

    scenario_snap: MarketSnapshot = registry.load(new_snapshot_id)
    assert scenario_snap is not None
    assert scenario_snap.mu == saved_base_snapshot.mu

def test_id_generation_and_suffix_format(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.id
    deltas_json_str = json.dumps([{"ticker": "AAPL", "delta": 0.001}])
    new_snapshot_id = scenario_adjust_tool_impl(snapshot_id=original_id, deltas_json_string=deltas_json_str)
    
    parts = new_snapshot_id.split("-scn-")
    assert len(parts) == 2
    base_id_for_new = original_id.split('-scn-')[0]
    assert parts[0] == base_id_for_new
    
    hash_suffix = parts[1]
    assert len(hash_suffix) == 8 
    assert all(c in "0123456789abcdef" for c in hash_suffix.lower())

def test_original_snapshot_unchanged_in_registry(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    registry = registry_and_cleanup_scenario
    original_id = saved_base_snapshot.meta.id
    mu_before_tool_call = copy.deepcopy(saved_base_snapshot.mu)
    sigma_before_tool_call = copy.deepcopy(saved_base_snapshot.sigma)
    deltas_json_str = json.dumps([
        {"ticker": "AAPL", "delta": 0.123},
        {"ticker": "GOOG", "delta": -0.05}
    ]) 
    scenario_adjust_tool_impl(snapshot_id=original_id, deltas_json_string=deltas_json_str)
    original_snapshot_reloaded: MarketSnapshot = registry.load(original_id)
    
    assert original_snapshot_reloaded is not None
    assert original_snapshot_reloaded.mu == mu_before_tool_call
    assert original_snapshot_reloaded.sigma == sigma_before_tool_call
    assert original_snapshot_reloaded.mu["AAPL"] == saved_base_snapshot.mu["AAPL"]

# Тесты на невалидные входы
def test_invalid_json_string(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.id
    invalid_json_str = "not a valid json string {{{{ "
    with pytest.raises(ValueError, match="Invalid JSON format for deltas_json_string"):
        scenario_adjust_tool_impl(snapshot_id=original_id, deltas_json_string=invalid_json_str)

def test_json_string_not_a_list(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.id
    json_str_not_list = json.dumps({"ticker": "AAPL", "delta": 0.1}) 
    with pytest.raises(TypeError, match="Parsed deltas_json_string must be a list"):
        scenario_adjust_tool_impl(snapshot_id=original_id, deltas_json_string=json_str_not_list)

def test_json_list_item_not_a_dict(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.id
    json_str_item_not_dict = json.dumps([{"ticker": "AAPL", "delta": 0.1}, "not_a_dict"])
    with pytest.raises(TypeError, match="Each item in the parsed list must be a dictionary, item at index 1 is <class 'str'>"):
        scenario_adjust_tool_impl(snapshot_id=original_id, deltas_json_string=json_str_item_not_dict)

def test_invalid_adjustment_item_in_json_missing_ticker(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.id
    json_str_missing_ticker = json.dumps([{"delta": 0.1}])
    with pytest.raises(ValueError, match=r"Invalid data for TickerAdjustment at index 0: .*Input required for field ticker"):
        scenario_adjust_tool_impl(snapshot_id=original_id, deltas_json_string=json_str_missing_ticker)

def test_invalid_adjustment_item_in_json_wrong_delta_type(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.id
    json_str_wrong_delta = json.dumps([{"ticker": "AAPL", "delta": "not-a-float"}])
    with pytest.raises(ValueError, match=r"Invalid data for TickerAdjustment at index 0: .*Input should be a valid number"):
        scenario_adjust_tool_impl(snapshot_id=original_id, deltas_json_string=json_str_wrong_delta)

# Тест test_direct_call_with_ticker_adjustment_objects был удален, т.к. он не соответствует текущей сигнатуре функции. 