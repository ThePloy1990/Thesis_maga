import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

import redis

from .model import MarketSnapshot, SnapshotMeta


class SnapshotRegistry:
    """
    Manages the storage and retrieval of MarketSnapshot objects.

    Uses Redis for quick access and a local file system directory as an S3 stub
    for persistent storage.
    """

    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379, s3_stub_path: str = 'local/snapshots'):
        """
        Initializes the SnapshotRegistry.

        Args:
            redis_host: Hostname for the Redis server.
            redis_port: Port number for the Redis server.
            s3_stub_path: Path to the local directory serving as an S3 stub.
        """
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
        self.s3_stub_path = Path(s3_stub_path)
        self.s3_stub_path.mkdir(parents=True, exist_ok=True)
        self._snapshot_key_prefix = "snapshot:"

    def _generate_snapshot_id(self) -> str:
        """Generates a unique snapshot ID based on the current UTC time."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")

    def save(self, snapshot: MarketSnapshot) -> str:
        """
        Saves a MarketSnapshot to Redis and the S3 stub.

        If the snapshot's metadata does not have an ID, a new one is generated.

        Args:
            snapshot: The MarketSnapshot object to save.

        Returns:
            The ID of the saved snapshot.
        """
        if not snapshot.meta.id:
            # Формируем новые метаданные, учитывая обновлённые имена полей.
            timestamp = getattr(snapshot.meta, "timestamp", None) or datetime.now(timezone.utc)

            snapshot.meta = SnapshotMeta(
                snapshot_id=self._generate_snapshot_id(),
                timestamp=timestamp,
                tickers=snapshot.meta.tickers,
                description=getattr(snapshot.meta, "description", None),
                source=getattr(snapshot.meta, "source", None),
                properties=getattr(snapshot.meta, "properties", None),
            )

        snapshot_id = snapshot.meta.id
        snapshot_json = snapshot.model_dump_json()

        # Save to Redis
        self.redis_client.set(f"{self._snapshot_key_prefix}{snapshot_id}", snapshot_json)

        # Save to S3 stub (local file)
        s3_file_path = self.s3_stub_path / f"{snapshot_id}.json"
        with open(s3_file_path, 'w') as f:
            f.write(snapshot_json)

        return snapshot_id

    def load(self, snapshot_id: str) -> Optional[MarketSnapshot]:
        """
        Loads a MarketSnapshot from Redis or the S3 stub.

        It first tries to load from Redis. If not found, it tries the S3 stub.

        Args:
            snapshot_id: The ID of the snapshot to load.

        Returns:
            The MarketSnapshot object if found, otherwise None.
        """
        # Try to load from Redis
        snapshot_json = self.redis_client.get(f"{self._snapshot_key_prefix}{snapshot_id}")
        if snapshot_json:
            try:
                return MarketSnapshot.model_validate_json(snapshot_json)
            except Exception as e:
                # Если не удалось загрузить напрямую, попробуем обновить структуру
                try:
                    snapshot_data = json.loads(snapshot_json)
                    # Обновляем метаданные для соответствия новым полям
                    if "meta" in snapshot_data:
                        meta = snapshot_data["meta"]
                        # Переименовываем поля в соответствии с новыми именами
                        if "snapshot_id" in meta and "id" not in meta:
                            meta["id"] = meta["snapshot_id"]
                        if "timestamp" in meta and "created_at" not in meta:
                            meta["created_at"] = meta["timestamp"]
                        if "tickers" in meta and "asset_universe" not in meta:
                            meta["asset_universe"] = meta["tickers"]
                        # Проверяем наличие horizon_days
                        if "horizon_days" not in meta:
                            if "properties" in meta and meta["properties"] is not None and "horizon_days" in meta["properties"]:
                                meta["horizon_days"] = meta["properties"]["horizon_days"]
                            else:
                                meta["horizon_days"] = 30  # Значение по умолчанию, если нет

                        return MarketSnapshot.model_validate(snapshot_data)
                except Exception as conversion_error:
                    print(f"Failed to convert old format: {conversion_error}")
                    raise e

        # Try to load from S3 stub
        s3_file_path = self.s3_stub_path / f"{snapshot_id}.json"
        if s3_file_path.exists():
            with open(s3_file_path, 'r') as f:
                snapshot_data = json.load(f)

            # Обновляем метаданные для соответствия новым полям
            if "meta" in snapshot_data:
                meta = snapshot_data["meta"]
                # Переименовываем поля в соответствии с новыми именами
                if "snapshot_id" in meta and "id" not in meta:
                    meta["id"] = meta["snapshot_id"]
                if "timestamp" in meta and "created_at" not in meta:
                    meta["created_at"] = meta["timestamp"]
                if "tickers" in meta and "asset_universe" not in meta:
                    meta["asset_universe"] = meta["tickers"]
                # Проверяем наличие horizon_days
                if "horizon_days" not in meta:
                    if "properties" in meta and meta["properties"] is not None and "horizon_days" in meta["properties"]:
                        meta["horizon_days"] = meta["properties"]["horizon_days"]
                    else:
                        meta["horizon_days"] = 30  # Значение по умолчанию, если нет

            try:
                return MarketSnapshot.model_validate(snapshot_data)
            except Exception as e:
                print(f"Failed to load snapshot from S3 stub: {e}")
                raise

        return None

    def _get_all_snapshot_ids_from_stub(self) -> List[str]:
        """Lists all snapshot IDs from the S3 stub based on filenames."""
        ids = []
        for f_path in self.s3_stub_path.glob('*.json'):
            ids.append(f_path.stem) # f_path.stem is filename without extension
        # Sort by typical ID format (timestamp-based)
        ids.sort(reverse=True)
        return ids

    def latest(self, before: Optional[datetime] = None) -> Optional[MarketSnapshot]:
        """
        Retrieves the latest MarketSnapshot.

        If 'before' is specified, it retrieves the latest snapshot created before
        that datetime.
        This implementation primarily relies on the S3 stub for determining recency
        if Redis doesn't have an easy way to list/sort keys by creation without custom indexing.

        Args:
            before: Optional datetime to filter snapshots. If provided, returns the
                    latest snapshot created strictly before this time.

        Returns:
            The latest MarketSnapshot object if found, otherwise None.
        """
        snapshot_ids = []
        # Attempt to get keys from Redis first, though listing by pattern and sorting can be inefficient
        # For robust 'latest' especially with 'before', S3 stub or a dedicated sorted set in Redis is better.
        # Here, we'll use S3 stub as the primary source for ordering if 'before' is used or for a full scan.

        redis_keys = self.redis_client.keys(f"{self._snapshot_key_prefix}*")
        # Extract IDs from Redis keys: b'snapshot:id' -> 'id'
        # And decode from bytes if necessary (decode_responses=True should handle it)
        redis_snapshot_ids = [key.split(':', 1)[1] for key in redis_keys]

        # Use S3 stub for a more reliable chronological order if many snapshots exist
        # or if 'before' filtering is needed across all snapshots.
        s3_snapshot_ids = self._get_all_snapshot_ids_from_stub()

        # Combine and unique IDs, prioritizing S3 for order if needed, though simple sort might suffice here.
        # A more robust approach for `before` would iterate and parse `created_at` from each snapshot meta.
        all_ids = sorted(list(set(redis_snapshot_ids + s3_snapshot_ids)), reverse=True)

        if not all_ids:
            return None

        if before:
            # Ensure 'before' is timezone-aware (UTC) if comparing with timezone-aware created_at
            if before.tzinfo is None:
                before = before.replace(tzinfo=timezone.utc)

            for snapshot_id in all_ids:
                # We need to load the snapshot to check its created_at time
                # This could be inefficient if there are many snapshots.
                # A better approach would be to store created_at in the key or a sorted set.
                try:
                    # Snapshot IDs are like "2023-10-27T10-30-00.123456Z"
                    # Attempt to parse datetime directly from ID for filtering if ID format is guaranteed
                    # This is a common pattern for time-sortable IDs.
                    dt_from_id_str = snapshot_id.replace('Z', '+00:00') # make it compatible with fromisoformat
                    # Python's fromisoformat might struggle with high-precision microseconds or 'Z'
                    # A more robust parsing might be needed if IDs vary.
                    # Simplification: assuming ID itself is sortable and reflects creation time accurately enough for 'before'.
                    # Or load snapshot meta, which is more robust:
                    potential_snapshot = self.load(snapshot_id)
                    if potential_snapshot and potential_snapshot.meta.created_at < before:
                        return potential_snapshot
                except ValueError: # Handle cases where ID is not a parsable datetime
                    # Fallback to loading if ID isn't directly comparable or parsable as a date
                    potential_snapshot = self.load(snapshot_id)
                    if potential_snapshot and potential_snapshot.meta.created_at < before:
                        return potential_snapshot
            return None # No snapshot found before the given datetime
        else:
            # Return the most recent one (first in sorted list)
            return self.load(all_ids[0])

    def delete_all_snapshots_dangerously(self):
        """
        Deletes all snapshots from Redis and the S3 stub.
        This is a dangerous operation and should be used with caution.
        """
        # Delete from Redis
        redis_keys = self.redis_client.keys(f"{self._snapshot_key_prefix}*")
        if redis_keys:
            self.redis_client.delete(*redis_keys)

        # Delete from S3 stub
        for f_path in self.s3_stub_path.glob('*.json'):
            os.remove(f_path)
        print(f"All snapshots deleted from Redis and {self.s3_stub_path}")
