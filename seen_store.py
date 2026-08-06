"""
seen_store.py – Persistent store for already-seen job IDs.

Tracks which jobs have been processed to avoid sending duplicate
notifications across GitHub Actions runs. Entries older than
MAX_AGE_DAYS are automatically pruned on each load.
"""

import json
import logging
import os
import shutil
import time
from typing import List, Set

logger = logging.getLogger("SeenStore")

# Jobs older than this are forgotten (they've long expired anyway)
MAX_AGE_DAYS = 30

# Default path — can be overridden via config or env
DEFAULT_SEEN_FILE = os.path.join(os.path.dirname(__file__), "seen_jobs.json")


class SeenStore:
    """Manages a {job_id: timestamp} dictionary persisted to JSON."""

    def __init__(self, filepath: str = DEFAULT_SEEN_FILE):
        self.filepath = filepath
        self._store: dict[str, float] = {}  # job_id → unix timestamp
        self._load()

    # ── Public API ────────────────────────────────────

    def is_seen(self, job_id: str) -> bool:
        """Return True if this job_id has been seen before."""
        return job_id in self._store

    def mark_seen(self, job_ids: List[str]) -> None:
        """Mark a list of job_ids as seen with current timestamp."""
        now = time.time()
        for jid in job_ids:
            if jid not in self._store:
                self._store[jid] = now

    def filter_new(self, jobs) -> list:
        """Return only jobs whose job_id hasn't been seen before.
        
        Args:
            jobs: List of Job dataclass instances (from scraper.py).
            
        Returns:
            List of unseen Job instances.
        """
        return [j for j in jobs if not self.is_seen(j.job_id)]

    def save(self) -> None:
        """Persist the store to disk atomically."""
        try:
            target_dir = os.path.dirname(self.filepath) or "."
            os.makedirs(target_dir, exist_ok=True)
            
            import tempfile
            with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
                json.dump(self._store, tf, indent=2)
                temp_name = tf.name

            os.replace(temp_name, self.filepath)
            logger.info(f"Saved {len(self._store)} seen job IDs to {self.filepath}")
        except OSError as e:
            logger.error(f"Failed to save seen store: {e}")

    @property
    def count(self) -> int:
        """Number of tracked job IDs."""
        return len(self._store)

    # ── Internal ──────────────────────────────────────

    def _load(self) -> None:
        """Load from disk and prune old entries."""
        if not os.path.exists(self.filepath):
            logger.info(f"No seen store found at {self.filepath} — starting fresh.")
            self._store = {}
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            # Backup corrupted file instead of silently wiping all seen data
            backup_path = self.filepath + ".bak"
            try:
                shutil.copy2(self.filepath, backup_path)
                logger.error(f"❌ Seen store corrupted ({e}). Backup saved to {backup_path}. Starting fresh.")
            except OSError:
                logger.error(f"❌ Seen store corrupted ({e}). Could not create backup. Starting fresh.")
            self._store = {}
            return

        # Handle legacy format: list of IDs (no timestamps)
        if isinstance(raw, list):
            logger.info("Migrating legacy seen store (list → dict with timestamps).")
            now = time.time()
            self._store = {str(jid): now for jid in raw}
        elif isinstance(raw, dict):
            self._store = {str(k): float(v) for k, v in raw.items()}
        else:
            logger.warning("Unexpected seen store format — starting fresh.")
            self._store = {}
            return

        self._prune()

    def _prune(self) -> None:
        """Remove entries older than MAX_AGE_DAYS."""
        cutoff = time.time() - (MAX_AGE_DAYS * 86400)
        before = len(self._store)
        self._store = {jid: ts for jid, ts in self._store.items() if ts > cutoff}
        pruned = before - len(self._store)
        if pruned:
            logger.info(f"Pruned {pruned} expired entries (>{MAX_AGE_DAYS} days old).")
