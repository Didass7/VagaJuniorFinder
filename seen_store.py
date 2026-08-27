"""
seen_store.py – Persistent store for already-seen job IDs.

Tracks which jobs have been processed to avoid sending duplicate
notifications across GitHub Actions runs. Entries older than
MAX_AGE_DAYS are automatically pruned on each load.
"""

from __future__ import annotations
import json
import logging
import os
import shutil
import time
import threading
from typing import List, Set, Optional, Dict, Any

logger = logging.getLogger("SeenStore")

# Jobs older than this are forgotten (they've long expired anyway)
MAX_AGE_DAYS = 30

# Default path — can be overridden via config or env
DEFAULT_SEEN_FILE = os.path.join(os.path.dirname(__file__), "seen_jobs.json")


class SeenStore:
    """Manages a {job_id: timestamp} dictionary persisted to JSON with thread-safety."""

    def __init__(self, filepath: str = DEFAULT_SEEN_FILE):
        self.filepath = filepath
        self._lock = threading.Lock()
        self._store: dict[str, float] = {}  # job_id → unix timestamp
        self._load()

    # ── Public API ────────────────────────────────────

    def is_seen(self, job_id: str) -> bool:
        """Return True if this job_id has been seen before."""
        with self._lock:
            return job_id in self._store

    def is_seen_candidate(self, title: str, company: str = "", link: str = "") -> bool:
        """Computes hash and checks if title + company + link combination has been seen.
        
        Uses the same hash algorithm as Job.__post_init__ to ensure early-skip
        optimization works correctly during scraping.
        """
        import hashlib
        try:
            from scraper import normalize_title_company_for_hash
            dedup_key = normalize_title_company_for_hash(title, company)
        except Exception:
            dedup_key = f"{title.lower()}_{company.lower()}"
        
        if link:
            link_hash = link.split("?")[0].rstrip("/")
            raw_str = f"{dedup_key}__{link_hash}"
        else:
            raw_str = dedup_key
        
        candidate_id = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()[:16]
        
        # Also check dedup_key-only hash as fallback for legacy entries
        if self.is_seen(candidate_id):
            return True
        
        # Fallback: check without link (covers legacy stored entries)
        if link:
            legacy_id = hashlib.sha256(dedup_key.encode('utf-8')).hexdigest()[:16]
            return self.is_seen(legacy_id)
        
        return False

    def mark_seen(self, job_ids: List[str]) -> None:
        """Mark a list of job_ids as seen with current timestamp."""
        now = time.time()
        with self._lock:
            for jid in job_ids:
                if jid not in self._store:
                    self._store[jid] = now

    def filter_new(self, jobs) -> list:
        """Return only jobs whose job_id hasn't been seen before, deduplicating across current batch as well."""
        seen_in_batch = set()
        unseen_jobs = []
        with self._lock:
            for j in jobs:
                if j.job_id in self._store or j.job_id in seen_in_batch:
                    continue
                seen_in_batch.add(j.job_id)
                unseen_jobs.append(j)
        return unseen_jobs

    def save(self) -> None:
        """Persist the store to disk atomically with thread-safety and cleanup."""
        target_dir = os.path.dirname(self.filepath) or "."
        os.makedirs(target_dir, exist_ok=True)
        
        import tempfile
        temp_name = None
        try:
            with self._lock:
                snapshot = dict(self._store)

            with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
                json.dump(snapshot, tf, indent=2)
                temp_name = tf.name

            os.replace(temp_name, self.filepath)
            temp_name = None  # Replaced successfully
            logger.info(f"Saved {len(snapshot)} seen job IDs to {self.filepath}")
        except OSError as e:
            logger.error(f"Failed to save seen store: {e}")
        finally:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass

    @property
    def count(self) -> int:
        """Number of tracked job IDs."""
        with self._lock:
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
