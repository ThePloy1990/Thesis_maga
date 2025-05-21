import pytest
import uuid
import copy
import os
import shutil
import json
from datetime import datetime, timezone
from typing import Dict, List, Any

from src.tools.scenario_tool import scenario_adjust_tool, TickerAdjustment
from src.market_snapshot.snapshot_registry import SnapshotRegistry
from src.market_snapshot.snapshot import MarketSnapshot, SnapshotMeta

# Константа для пути к тестовому S3 стабу для этого модуля тестов
TEST_S3_STUB_PATH_SCENARIO = "local_test/snapshots_scenario_tool"
# Конфигурация Redis (предполагаем, что Redis запущен локально для тестов)
REDIS_HOST = "localhost"
REDIS_PORT = 6379

@pytest.fixture(scope="function")
def registry_and_cleanup_scenario():
    """
    Фикстура для создания и очистки SnapshotRegistry и S3 стаба для тестов scenario_tool.
    Также очищает Redis от ключей, созданных в этих тестах.
    """
    # Создаем директорию для S3 стаба, если ее нет
    if not os.path.exists(TEST_S3_STUB_PATH_SCENARIO):
        os.makedirs(TEST_S3_STUB_PATH_SCENARIO)
    
    registry = SnapshotRegistry(
        redis_host=REDIS_HOST, 
        redis_port=REDIS_PORT, 
        s3_stub_path=TEST_S3_STUB_PATH_SCENARIO
    )
    # Очистка Redis перед тестом (только ключи, которые могут быть созданы этим тестом)
    # Это более безопасно, чем flushall, если Redis используется другими тестами/приложениями
    # В данном случае, SnapshotRegistry использует префикс "snapshot:"
    # Сценарии будут иметь ID типа "base_id-scn-xxxx"
    if registry.redis_client:
        keys_to_delete = registry.redis_client.keys("snapshot:*") # Захватываем все снэпшоты
        if keys_to_delete:
            registry.redis_client.delete(*keys_to_delete)

    yield registry

    # Очистка после теста
    if registry.redis_client:
        keys_to_delete = registry.redis_client.keys("snapshot:*") 
        if keys_to_delete:
            registry.redis_client.delete(*keys_to_delete)
            
    # Удаляем директорию S3 стаба
    if os.path.exists(TEST_S3_STUB_PATH_SCENARIO):
        shutil.rmtree(TEST_S3_STUB_PATH_SCENARIO)

@pytest.fixture(scope="function")
def base_snapshot_data() -> Dict:
    """Данные для создания базового MarketSnapshot."""
    return {
        "meta": {
            "id": "test_base_snap_for_scenario",
            "created_at": datetime.now(timezone.utc),
            "asset_universe": ["AAPL", "MSFT", "GOOG"],
            "horizon_days": 30,
            "description": "Base snapshot for scenario tests",
            "source": "test_fixture",
            "properties": {"test_prop": "value1", "horizon_days": 30}
        },
        "mu": {"AAPL": 0.01, "MSFT": 0.015, "GOOG": 0.02},
        "sigma": {
            "AAPL": {"AAPL": 0.0025, "MSFT": 0.0001, "GOOG": 0.0002},
            "MSFT": {"AAPL": 0.0001, "MSFT": 0.0036, "GOOG": 0.0003},
            "GOOG": {"AAPL": 0.0002, "MSFT": 0.0003, "GOOG": 0.0049},
        },
        "market_caps": {"AAPL": 2.5e12, "MSFT": 2.0e12, "GOOG": 1.8e12},
        "prices": {"AAPL": 150.0, "MSFT": 300.0, "GOOG": 2500.0}
    }

@pytest.fixture(scope="function")
def saved_base_snapshot(registry_and_cleanup_scenario: SnapshotRegistry, base_snapshot_data: Dict) -> MarketSnapshot:
    """Создает, сохраняет и возвращает базовый MarketSnapshot."""
    registry = registry_and_cleanup_scenario
    meta_data = base_snapshot_data["meta"]
    
    # Ensure timestamp is a datetime object if it's not already (e.g. if data is from pure dict)
    if isinstance(meta_data["created_at"], str):
        meta_data["created_at"] = datetime.fromisoformat(meta_data["created_at"])
    elif not isinstance(meta_data["created_at"], datetime):
        meta_data["created_at"] = datetime.now(timezone.utc) # Fallback, should be datetime

    base_meta = SnapshotMeta(**meta_data)
    
    base_snap = MarketSnapshot(
        meta=base_meta,
        mu=base_snapshot_data["mu"],
        sigma=base_snapshot_data["sigma"],
        market_caps=base_snapshot_data.get("market_caps"),
        prices=base_snapshot_data.get("prices")
    )
    registry.save(base_snap)
    return base_snap

def test_successful_adjustment_and_save(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    registry = registry_and_cleanup_scenario
    original_id = saved_base_snapshot.meta.snapshot_id
    
    adjustments_data = [
        {"ticker": "AAPL", "delta": 0.005},
        {"ticker": "MSFT", "delta": -0.002}
    ]
    deltas_json_str = json.dumps(adjustments_data)
    expected_deltas_dict = {"AAPL": 0.005, "MSFT": -0.002}

    new_snapshot_id = scenario_adjust_tool(snapshot_id=original_id, deltas_json_string=deltas_json_str)

    expected_prefix = original_id + "-scn-"
    assert new_snapshot_id.startswith(expected_prefix)
    hash_part = new_snapshot_id[len(expected_prefix):]
    assert len(hash_part) == 8

    scenario_snap: MarketSnapshot = registry.load(new_snapshot_id)
    assert scenario_snap is not None
    assert scenario_snap.meta.snapshot_id == new_snapshot_id

    assert scenario_snap.mu["AAPL"] == pytest.approx(saved_base_snapshot.mu["AAPL"] + expected_deltas_dict["AAPL"])
    assert scenario_snap.mu["MSFT"] == pytest.approx(saved_base_snapshot.mu["MSFT"] + expected_deltas_dict["MSFT"])
    assert scenario_snap.mu["GOOG"] == pytest.approx(saved_base_snapshot.mu["GOOG"])

    assert scenario_snap.sigma == saved_base_snapshot.sigma
    assert scenario_snap.meta.tickers == saved_base_snapshot.meta.tickers
    assert scenario_snap.meta.properties.get("horizon_days") == saved_base_snapshot.meta.properties.get("horizon_days")
    assert scenario_snap.meta.timestamp > saved_base_snapshot.meta.timestamp
    assert scenario_snap.meta.source == "scenario_adjustment_tool"
    assert scenario_snap.meta.description.startswith(f"Scenario based on {original_id}")
    assert scenario_snap.meta.properties["base_snapshot_id"] == original_id
    assert scenario_snap.meta.properties["applied_deltas"] == expected_deltas_dict 

    original_reloaded: MarketSnapshot = registry.load(original_id)
    assert original_reloaded.mu == saved_base_snapshot.mu 

def test_adjust_ticker_not_in_snapshot(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot, capsys):
    registry = registry_and_cleanup_scenario
    original_id = saved_base_snapshot.meta.snapshot_id
    adjustments_data = [
        {"ticker": "NEWCO", "delta": 0.05},
        {"ticker": "AAPL", "delta": 0.001}
    ]
    deltas_json_str = json.dumps(adjustments_data)
    expected_AAPL_delta = 0.001

    new_snapshot_id = scenario_adjust_tool(snapshot_id=original_id, deltas_json_string=deltas_json_str)
    
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
        scenario_adjust_tool(snapshot_id=non_existent_id, deltas_json_string=deltas_json_str)

def test_empty_deltas_list_in_json_string(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    registry = registry_and_cleanup_scenario
    original_id = saved_base_snapshot.meta.snapshot_id
    deltas_json_str = json.dumps([]) # Пустой список как JSON-строка

    new_snapshot_id = scenario_adjust_tool(snapshot_id=original_id, deltas_json_string=deltas_json_str)
    expected_prefix = original_id + "-scn-"
    assert new_snapshot_id.startswith(expected_prefix)

    scenario_snap: MarketSnapshot = registry.load(new_snapshot_id)
    assert scenario_snap is not None
    assert scenario_snap.mu == saved_base_snapshot.mu

def test_id_generation_and_suffix_format(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.snapshot_id
    deltas_json_str = json.dumps([{"ticker": "AAPL", "delta": 0.001}])
    new_snapshot_id = scenario_adjust_tool(snapshot_id=original_id, deltas_json_string=deltas_json_str)
    
    parts = new_snapshot_id.split("-scn-")
    assert len(parts) == 2
    base_id_for_new = original_id.split('-scn-')[0]
    assert parts[0] == base_id_for_new
    
    hash_suffix = parts[1]
    assert len(hash_suffix) == 8 
    assert all(c in "0123456789abcdef" for c in hash_suffix.lower())

def test_original_snapshot_unchanged_in_registry(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    registry = registry_and_cleanup_scenario
    original_id = saved_base_snapshot.meta.snapshot_id
    mu_before_tool_call = copy.deepcopy(saved_base_snapshot.mu)
    deltas_json_str = json.dumps([
        {"ticker": "AAPL", "delta": 0.123},
        {"ticker": "GOOG", "delta": -0.05}
    ]) 
    scenario_adjust_tool(snapshot_id=original_id, deltas_json_string=deltas_json_str)
    original_snapshot_reloaded: MarketSnapshot = registry.load(original_id)
    
    assert original_snapshot_reloaded is not None
    assert original_snapshot_reloaded.mu == mu_before_tool_call
    assert original_snapshot_reloaded.mu["AAPL"] == saved_base_snapshot.mu["AAPL"]

# Тесты на невалидные входы
def test_invalid_json_string(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.snapshot_id
    invalid_json_str = "not a valid json string {{{{ "
    with pytest.raises(ValueError, match="Invalid JSON format for deltas_json_string"):
        scenario_adjust_tool(snapshot_id=original_id, deltas_json_string=invalid_json_str)

def test_json_string_not_a_list(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.snapshot_id
    json_str_not_list = json.dumps({"ticker": "AAPL", "delta": 0.1}) # JSON-объект, а не массив
    with pytest.raises(TypeError, match="Parsed deltas_json_string must be a list"):
        scenario_adjust_tool(snapshot_id=original_id, deltas_json_string=json_str_not_list)

def test_json_list_item_not_a_dict(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.snapshot_id
    json_str_item_not_dict = json.dumps([{"ticker": "AAPL", "delta": 0.1}, "not_a_dict"])
    with pytest.raises(TypeError, match="Each item in the parsed list must be a dictionary, item at index 1 is <class 'str'>"):
        scenario_adjust_tool(snapshot_id=original_id, deltas_json_string=json_str_item_not_dict)

def test_invalid_adjustment_item_in_json_missing_ticker(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.snapshot_id
    json_str_missing_ticker = json.dumps([{"delta": 0.1}])
    with pytest.raises(ValueError) as exc_info:
        scenario_adjust_tool(snapshot_id=original_id, deltas_json_string=json_str_missing_ticker)
    assert "Field required [type=missing" in str(exc_info.value)
    assert "ticker" in str(exc_info.value)

def test_invalid_adjustment_item_in_json_wrong_delta_type(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    original_id = saved_base_snapshot.meta.snapshot_id
    json_str_wrong_delta = json.dumps([{"ticker": "AAPL", "delta": "not-a-float"}])
    with pytest.raises(ValueError) as exc_info:
        scenario_adjust_tool(snapshot_id=original_id, deltas_json_string=json_str_wrong_delta)
    assert "Input should be a valid number" in str(exc_info.value)
    assert "unable to parse string as a number" in str(exc_info.value)

# Тест на случай передачи уже созданных объектов TickerAdjustment (этот тест теперь нерелевантен, т.к. функция ожидает List[Dict])
# Мы его удалим, так как adjustments_list_raw теперь всегда list of dicts с точки зрения сигнатуры функции для SDK.
# Вместо него, проверим, что функция все еще может работать с предварительно созданными объектами, если ее вызвать напрямую (хотя SDK так не сделает)

def test_direct_call_with_ticker_adjustment_objects(registry_and_cleanup_scenario: SnapshotRegistry, saved_base_snapshot: MarketSnapshot):
    """Тестирует прямой вызов функции с уже созданными объектами TickerAdjustment.
    Это не то, как SDK будет вызывать, но полезно для проверки внутренней логики.
    Однако, сигнатура теперь List[Dict[str, Any]], поэтому такой вызов вызовет TypeError
    на этапе проверки isinstance(item_raw, dict). Оставляем этот тест для демонстрации,
    но ожидаем TypeError или изменим функцию, чтобы она принимала List[Union[Dict, TickerAdjustment]].
    Для текущей реализации функции, этот тест должен падать или быть адаптирован.
    Пока что закомментируем его, так как он не соответствует текущей сигнатуре для SDK.
    """
    # registry = registry_and_cleanup_scenario
    # original_id = saved_base_snapshot.meta.snapshot_id
    # adjustments_obj_list = [
    #     TickerAdjustment(ticker="AAPL", delta=-0.003),
    #     TickerAdjustment(ticker="GOOG", delta=0.007)
    # ]
    # expected_deltas_dict = {"AAPL": -0.003, "GOOG": 0.007}
    # # Примечание: такой вызов не пройдет проверку isinstance(item_raw, dict) внутри функции
    # # new_snapshot_id = scenario_adjust_tool(snapshot_id=original_id, adjustments_list_raw=adjustments_obj_list)
    # # ... проверки ...
    pass # Заглушка для этого теста, пока он неактуален для SDK-вызова

# Пример теста для обновления created_at, если бы это было реализовано
# def test_scenario_snapshot_updates_created_at(registry_and_cleanup_scenario: SnapshotRegistry, base_snapshot: MarketSnapshot):
#     registry = registry_and_cleanup_scenario
#     original_id = base_snapshot.meta.id
#     original_created_at = base_snapshot.meta.created_at
#     deltas = {"AAPL": 0.005}

#     # Предположим, что scenario_tool обновляет created_at
#     # Для этого в scenario_tool нужно раскомментировать строку и импортировать datetime, timezone
#     # from datetime import datetime, timezone
#     # scenario_snapshot.meta.created_at = datetime.now(timezone.utc)

#     # Чтобы тест был надежным, нужно мокнуть datetime.now, но для простоты пока пропустим
#     # import time
#     # time.sleep(0.01) # Небольшая задержка, чтобы время точно изменилось

#     new_snapshot_id = scenario_adjust_tool(snapshot_id=original_id, deltas=deltas)
#     scenario_snap: MarketSnapshot = registry.load(new_snapshot_id)
    
#     assert scenario_snap is not None
#     assert scenario_snap.meta.created_at > original_created_at 