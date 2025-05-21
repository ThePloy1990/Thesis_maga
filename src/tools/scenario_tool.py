import uuid
import hashlib
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any

from pydantic import Field, BaseModel, ValidationError
import json

from pf_agents import function_tool
from market_snapshot.snapshot import MarketSnapshot, SnapshotMeta
from market_snapshot.snapshot_registry import SnapshotRegistry

# Новая Pydantic модель для одной корректировки тикера
class TickerAdjustment(BaseModel):
    ticker: str = Field(..., description="The ticker symbol for the adjustment.")
    delta: float = Field(..., description="The delta adjustment value for the ticker's 'mu'.")

# Helper to generate a short, deterministic hash for snapshot ID suffixes
def _generate_short_hash(data_string: str, length: int = 8) -> str:
    return hashlib.sha256(data_string.encode()).hexdigest()[:length]

@function_tool(strict_json_schema=False) # Пока оставляем False
def scenario_adjust_tool(snapshot_id: str, adjustments_list_raw: List[Dict[str, Any]]) -> str:
    """
    Adjusts the 'mu' values in a given market snapshot based on a list of ticker adjustments
    and saves it as a new snapshot.

    Args:
        snapshot_id: The ID of the base market snapshot to use.
        adjustments_list_raw: A list of dictionaries, where each dictionary represents a ticker adjustment.
                              Each dictionary must contain a 'ticker' (str) and a 'delta' (float).
                              Example: [{"ticker": "AAPL", "delta": -0.01}, {"ticker": "MSFT", "delta": 0.005}]

    Returns:
        The ID of the newly created and saved scenario snapshot.
    """
    registry = SnapshotRegistry()
    original_snapshot = registry.load_snapshot(snapshot_id)
    if not original_snapshot:
        raise ValueError(f"Snapshot with ID '{snapshot_id}' not found.")

    deltas: Dict[str, float] = {}
    if not isinstance(adjustments_list_raw, list):
        raise TypeError(f"adjustments_list_raw must be a list, got {type(adjustments_list_raw)}")

    processed_adjustments: List[TickerAdjustment] = []
    for i, item_raw in enumerate(adjustments_list_raw):
        if not isinstance(item_raw, dict):
            raise TypeError(f"Each item in adjustments_list_raw must be a dictionary, item at index {i} is {type(item_raw)}")
        try:
            adjustment = TickerAdjustment(**item_raw)
            processed_adjustments.append(adjustment)
        except ValidationError as e:
            raise ValueError(f"Invalid data for TickerAdjustment at index {i}: {e}. Input was: {item_raw}")

    for item in processed_adjustments:
        if item.ticker in deltas:
            print(f"Warning: Duplicate ticker '{item.ticker}' in adjustments_list. Using the latest value: {item.delta}")
        deltas[item.ticker] = item.delta
    
    new_mu = original_snapshot.mu.copy()
    for ticker, delta_value in deltas.items():
        if ticker in new_mu:
            new_mu[ticker] += delta_value
        else:
            print(f"Warning: Ticker '{ticker}' in deltas not found in original snapshot's mu. Adjustment for this ticker will be skipped.")

    deltas_repr = json.dumps(deltas, sort_keys=True)
    scenario_suffix = f"scn-{_generate_short_hash(deltas_repr)}"
    
    base_id_for_new = original_snapshot.meta.snapshot_id.split('-scn-')[0]
    new_id = f"{base_id_for_new}-{scenario_suffix}"
    
    new_meta = SnapshotMeta(
        snapshot_id=new_id,
        tickers=original_snapshot.meta.tickers, 
        timestamp=datetime.now(timezone.utc), 
        description=f"Scenario based on {original_snapshot.meta.snapshot_id} with deltas applied. Deltas: {deltas_repr}",
        source="scenario_adjustment_tool",
        properties={
            **(original_snapshot.meta.properties or {}),
            "base_snapshot_id": original_snapshot.meta.snapshot_id,
            "applied_deltas": deltas
        }
    )

    scenario_snapshot = MarketSnapshot(
        meta=new_meta,
        mu=new_mu,
        sigma=original_snapshot.sigma.copy(), 
        market_caps=original_snapshot.market_caps.copy() if original_snapshot.market_caps else None,
        prices=original_snapshot.prices.copy() if original_snapshot.prices else None,
    )

    registry.save_snapshot(scenario_snapshot)
    return new_id 