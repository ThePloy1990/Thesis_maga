from datetime import datetime
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field


class SnapshotMeta(BaseModel):
    """
    Metadata for a market snapshot.

    Attributes:
        snapshot_id: Unique identifier for the snapshot (ISO 8601 UTC format recommended).
        timestamp: Timestamp of when the snapshot was created.
        tickers: List of asset tickers included in this snapshot.
        description: Optional description of the snapshot.
        source: Optional source of the snapshot.
        properties: Optional additional properties for the snapshot.
    """
    snapshot_id: str = Field(validation_alias="id", serialization_alias="id")
    timestamp: datetime = Field(validation_alias="created_at", serialization_alias="created_at")
    tickers: List[str] = Field(validation_alias="asset_universe", serialization_alias="asset_universe")
    description: Optional[str] = None
    source: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None

    # ---- Convenience read-only aliases (backwards-compatibility) ----------------
    @property
    def id(self) -> str:  # type: ignore
        """Alias for accessing as meta.id in existing code."""
        return self.snapshot_id

    @property
    def created_at(self) -> datetime:  # type: ignore
        """Alias to timestamp for compatibility."""
        return self.timestamp

    @property
    def asset_universe(self) -> List[str]:  # type: ignore
        """Alias to tickers."""
        return self.tickers

    @property
    def horizon_days(self) -> Optional[int]:  # type: ignore
        """Extract horizon from properties (used in tests)."""
        if self.properties and "horizon_days" in self.properties:
            try:
                return int(self.properties["horizon_days"])
            except (TypeError, ValueError):
                return None
        return None


class MarketSnapshot(BaseModel):
    """
    Represents a snapshot of the market at a specific point in time.

    Attributes:
        meta: Metadata associated with this snapshot.
        mu: Dictionary of expected returns for each asset (ticker -> expected_return).
        sigma: Covariance matrix of asset returns (ticker -> {ticker -> covariance}).
        sentiment: Dictionary of sentiment scores for each asset (ticker -> sentiment_score).
        raw_features_path: Path to the raw features file used to generate this snapshot.
        market_caps: Optional dictionary of market caps for each asset (ticker -> market_cap).
        prices: Optional dictionary of prices for each asset (ticker -> price).
    """
    meta: SnapshotMeta
    mu: Dict[str, float]
    sigma: Dict[str, Dict[str, float]]
    sentiment: Optional[Dict[str, float]] = None
    raw_features_path: Optional[str] = None
    market_caps: Optional[Dict[str, float]] = None
    prices: Optional[Dict[str, float]] = None 