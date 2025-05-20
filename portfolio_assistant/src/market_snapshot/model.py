from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel


class SnapshotMeta(BaseModel):
    """
    Metadata for a market snapshot.

    Attributes:
        id: Unique identifier for the snapshot (ISO 8601 UTC format recommended).
        created_at: Timestamp of when the snapshot was created.
        horizon_days: The forecast horizon in days for this snapshot.
        asset_universe: List of asset tickers included in this snapshot.
    """
    id: str
    created_at: datetime
    horizon_days: int
    asset_universe: List[str]


class MarketSnapshot(BaseModel):
    """
    Represents a snapshot of the market at a specific point in time.

    Attributes:
        meta: Metadata associated with this snapshot.
        mu: Dictionary of expected returns for each asset (ticker -> expected_return).
        sigma: Covariance matrix of asset returns (ticker -> {ticker -> covariance}).
        sentiment: Dictionary of sentiment scores for each asset (ticker -> sentiment_score).
        raw_features_path: Path to the raw features file used to generate this snapshot.
    """
    meta: SnapshotMeta
    mu: Dict[str, float]
    sigma: Dict[str, Dict[str, float]]
    sentiment: Dict[str, float]
    raw_features_path: str 