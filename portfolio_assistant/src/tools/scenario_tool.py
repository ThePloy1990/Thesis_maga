import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Any

from pydantic import Field, BaseModel, ValidationError

from src.market_snapshot.snapshot import MarketSnapshot, SnapshotMeta
from src.market_snapshot.snapshot_registry import SnapshotRegistry

# Pydantic модель для одной корректировки тикера
class TickerAdjustment(BaseModel):
    ticker: str = Field(..., description="The ticker symbol for the adjustment.")
    delta: float = Field(..., description="The delta adjustment value for the ticker's 'mu'.")

def _generate_short_hash(data_string: str, length: int = 8) -> str:
    """Helper to generate a short, deterministic hash for snapshot ID suffixes."""
    return hashlib.sha256(data_string.encode()).hexdigest()[:length]

def _internal_scenario_adjust_tool_logic(snapshot_id: str, deltas_json_string: str) -> str:
    """
    (Actual implementation) Adjusts the 'mu' values in a given market snapshot based on a JSON string
    of ticker adjustments and saves it as a new snapshot. This function contains the core logic
    and is intended for direct testing.

    Args:
        snapshot_id: The ID of the base market snapshot to use.
        deltas_json_string: A JSON string representing a list of ticker adjustments.
                            Example: '[{"ticker": "AAPL", "delta": -0.01}, {"ticker": "MSFT", "delta": 0.005}]'

    Returns:
        The ID of the newly created and saved scenario snapshot.
    """
    registry = SnapshotRegistry()
    original_snapshot = registry.load(snapshot_id)
    if not original_snapshot:
        raise ValueError(f"Snapshot with ID '{snapshot_id}' not found.")

    try:
        adjustments_list_raw = json.loads(deltas_json_string)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format for deltas_json_string: {e}. Input was: {deltas_json_string}")

    if not isinstance(adjustments_list_raw, list):
        raise TypeError(f"Parsed deltas_json_string must be a list, got {type(adjustments_list_raw)}. Parsed data: {adjustments_list_raw}")

    deltas: Dict[str, float] = {}
    processed_adjustments: List[TickerAdjustment] = []
    for i, item_raw in enumerate(adjustments_list_raw):
        if not isinstance(item_raw, dict):
            raise TypeError(f"Each item in the parsed list must be a dictionary, item at index {i} is {type(item_raw)}. Item: {item_raw}")
        try:
            adjustment = TickerAdjustment(**item_raw)
            processed_adjustments.append(adjustment)
        except ValidationError as e:
            raise ValueError(f"Invalid data for TickerAdjustment at index {i}: {e}. Input was: {item_raw}")

    for item in processed_adjustments:
        if item.ticker in deltas:
            print(f"Warning: Duplicate ticker '{item.ticker}' in adjustments list. Using the latest value: {item.delta}")
        deltas[item.ticker] = item.delta
    
    new_mu = original_snapshot.mu.copy()
    for ticker, delta_value in deltas.items():
        if ticker in new_mu:
            new_mu[ticker] += delta_value
        else:
            print(f"Warning: Ticker '{ticker}' in deltas not found in original snapshot's mu. Adjustment for this ticker will be skipped.")

    deltas_repr = json.dumps(deltas, sort_keys=True)
    scenario_suffix = f"scn-{_generate_short_hash(deltas_repr)}"
    
    base_id_for_new = original_snapshot.meta.id.split('-scn-')[0]
    new_id = f"{base_id_for_new}-{scenario_suffix}"
    
    new_meta_properties = {
        **(getattr(original_snapshot.meta, 'properties', None) or {}),
        "base_snapshot_id": original_snapshot.meta.id,
        "applied_deltas": deltas
    }

    meta_kwargs_for_new = {
        "id": new_id,
        "asset_universe": original_snapshot.meta.tickers,
        "created_at": datetime.now(timezone.utc),
        "horizon_days": getattr(original_snapshot.meta, "horizon_days", 30),
        "description": f"Scenario based on {original_snapshot.meta.id} with deltas applied. Deltas: {deltas_repr}",
        "source": "scenario_adjustment_tool",
        "properties": new_meta_properties,
    }

    new_meta = SnapshotMeta(**meta_kwargs_for_new)

    scenario_snapshot = MarketSnapshot(
        meta=new_meta,
        mu=new_mu,
        sigma=original_snapshot.sigma.copy(), 
        market_caps=original_snapshot.market_caps.copy() if original_snapshot.market_caps else None,
        prices=original_snapshot.prices.copy() if original_snapshot.prices else None,
        sentiment=original_snapshot.sentiment.copy() if hasattr(original_snapshot, 'sentiment') and original_snapshot.sentiment else None,
        raw_features_path=original_snapshot.raw_features_path if hasattr(original_snapshot, 'raw_features_path') else None
    )

    registry.save(scenario_snapshot)
    return new_id

# Экспортируем функцию без декоратора, чтобы её можно было вызывать напрямую из тестов.
def scenario_adjust_tool(snapshot_id: str, deltas_json_string: str) -> str:
    """
    Adjusts the 'mu' values in a given market snapshot based on a JSON string of ticker adjustments
    and saves it as a new snapshot.

    Args:
        snapshot_id: The ID of the base market snapshot to use.
        deltas_json_string: A JSON string representing a list of ticker adjustments.
                            Each item in the list should be a dictionary containing a 'ticker' (str)
                            and a 'delta' (float).
                            Example: '[{"ticker": "AAPL", "delta": -0.01}, {"ticker": "MSFT", "delta": 0.005}]'

    Returns:
        The ID of the newly created and saved scenario snapshot.
    """
    return _internal_scenario_adjust_tool_logic(snapshot_id, deltas_json_string)
