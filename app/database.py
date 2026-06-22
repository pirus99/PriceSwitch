"""SQLite-backed switch-event log with retention cleanup."""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class EventLog:
    """Thread-safe store of switch events."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS switch_events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts         TEXT    NOT NULL,
                    state      TEXT    NOT NULL,
                    price      REAL,
                    mode       TEXT    NOT NULL,
                    reason     TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_ts ON switch_events(ts)"
            )
            self._conn.commit()

    def add_event(
        self,
        state: str,
        price: float | None,
        mode: str,
        reason: str = "",
    ) -> dict:
        """Record a switch event and return the stored row."""
        ts = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO switch_events (ts, state, price, mode, reason) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts, state, price, mode, reason),
            )
            self._conn.commit()
            row_id = cur.lastrowid
        logger.info("Switch event: state=%s price=%s mode=%s (%s)", state, price, mode, reason)
        return {
            "id": row_id,
            "ts": ts,
            "state": state,
            "price": price,
            "mode": mode,
            "reason": reason,
        }

    def recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM switch_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def purge_older_than(self, days: int | None) -> int:
        """Delete events older than ``days``. Returns rows deleted."""
        if not days or days <= 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM switch_events WHERE ts < ?", (cutoff,)
            )
            self._conn.commit()
            deleted = cur.rowcount
        if deleted:
            logger.info("Retention: purged %s events older than %s days", deleted, days)
        return deleted

    def close(self) -> None:
        with self._lock:
            self._conn.close()
