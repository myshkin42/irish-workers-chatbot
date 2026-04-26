from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


class LookupStore:
    # Single-process in-memory store. Replace with Redis/DB if scaling beyond one Fly machine.
    def __init__(self, ttl_minutes: int):
        self.ttl = timedelta(minutes=ttl_minutes)
        self._items: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self._lock = Lock()

    def store(self, result: dict[str, Any]) -> str:
        lookup_id = str(uuid4())
        with self._lock:
            self._purge_expired_locked()
            self._items[lookup_id] = (datetime.now(timezone.utc), result)
        return lookup_id

    def get(self, lookup_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._purge_expired_locked()
            item = self._items.get(lookup_id)
            if item is None:
                return None

            created_at, result = item
            if datetime.now(timezone.utc) - created_at > self.ttl:
                self._items.pop(lookup_id, None)
                return None

            return result

    def _purge_expired_locked(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            lookup_id
            for lookup_id, (created_at, _) in self._items.items()
            if now - created_at > self.ttl
        ]
        for lookup_id in expired:
            self._items.pop(lookup_id, None)
