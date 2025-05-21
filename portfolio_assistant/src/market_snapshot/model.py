from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field, ConfigDict


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
    # Основные поля для совместимости с Pydantic 2.x
    snapshot_id: str = Field(alias="snapshot_id", default="")
    timestamp: datetime = Field(alias="timestamp", default_factory=lambda: datetime.now(timezone.utc))
    tickers: List[str] = Field(alias="tickers", default_factory=list)
    description: Optional[str] = Field(alias="description", default=None)
    source: Optional[str] = Field(alias="source", default=None)
    properties: Optional[Dict[str, Any]] = Field(alias="properties", default=None)
    
    # Обратная совместимость с предыдущей версией модели
    id: str = Field(alias="id", default="")
    created_at: datetime = Field(alias="created_at", default_factory=lambda: datetime.now(timezone.utc))
    asset_universe: List[str] = Field(alias="asset_universe", default_factory=list)
    horizon_days: int = Field(default=30)
    
    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True
    )
    
    def __init__(self, **data):
        super().__init__(**data)
        
        # Синхронизируем алиасы при инициализации
        if not self.id and "snapshot_id" in data:
            self.id = data["snapshot_id"]
        elif not self.snapshot_id and "id" in data:
            self.snapshot_id = data["id"]
            
        if not self.created_at and "timestamp" in data:
            self.created_at = data["timestamp"]
        elif not self.timestamp and "created_at" in data:
            self.timestamp = data["created_at"]
            
        if not self.asset_universe and "tickers" in data:
            self.asset_universe = data["tickers"]
        elif not self.tickers and "asset_universe" in data:
            self.tickers = data["asset_universe"]


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