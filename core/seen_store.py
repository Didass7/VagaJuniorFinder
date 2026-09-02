"""
seen_store.py – Persistent store for already-seen job IDs.

Tracks which jobs have been processed to avoid sending duplicate
notifications across GitHub Actions runs. Entries older than
MAX_AGE_DAYS are automatically pruned on each load.
Uses SQLite for robust, thread-safe atomic operations.
"""

from __future__ import annotations
import json
import logging
import os
import time
import threading
import sqlite3
from typing import List

logger = logging.getLogger("SeenStore")

# Jobs older than this are forgotten (they've long expired anyway)
MAX_AGE_DAYS = 30

# Default path
DEFAULT_SEEN_FILE = os.path.join(os.path.dirname(__file__), "seen_jobs.db")
LEGACY_JSON_FILE = os.path.join(os.path.dirname(__file__), "seen_jobs.json")

class SeenStore:
    """Manages a {job_id: timestamp} dictionary persisted to SQLite with thread-safety."""

    def __init__(self, filepath: str = DEFAULT_SEEN_FILE):
        self.legacy_json = LEGACY_JSON_FILE
        if filepath.endswith('.json'):
            self.legacy_json = filepath
            filepath = filepath[:-5] + '.db'
            
        self.filepath = filepath
        self._lock = threading.Lock()
        
        # Connect to SQLite. check_same_thread=False allows sharing across threads,
        # provided we serialize writes with our _lock.
        self.conn = sqlite3.connect(self.filepath, check_same_thread=False)
        self._init_db()
        self._migrate_legacy_if_needed()
        self._prune()

    def _init_db(self):
        with self._lock:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    job_id TEXT PRIMARY KEY,
                    seen_at REAL
                )
            ''')
            # WAL mode for better concurrency and safety
            self.conn.execute('PRAGMA journal_mode=WAL')
            self.conn.commit()

    def _migrate_legacy_if_needed(self):
        # Check if json exists, and if DB is empty, import it
        if os.path.exists(self.legacy_json):
            with self._lock:
                c = self.conn.cursor()
                c.execute('SELECT COUNT(*) FROM seen_jobs')
                if c.fetchone()[0] == 0:
                    logger.info(f"Migrating legacy JSON store from {self.legacy_json} to SQLite.")
                    try:
                        with open(self.legacy_json, 'r', encoding='utf-8') as f:
                            raw = json.load(f)
                        
                        now = time.time()
                        records = []
                        if isinstance(raw, list):
                            records = [(str(jid), now) for jid in raw]
                        elif isinstance(raw, dict):
                            records = [(str(k), float(v)) for k, v in raw.items()]
                        
                        c.executemany('INSERT OR IGNORE INTO seen_jobs (job_id, seen_at) VALUES (?, ?)', records)
                        self.conn.commit()
                        logger.info("Migration complete.")
                        
                        # Rename the json file to indicate it's migrated
                        os.rename(self.legacy_json, self.legacy_json + ".migrated")
                    except Exception as e:
                        logger.error(f"Failed to migrate legacy JSON: {e}")

    # ── Public API ────────────────────────────────────

    def is_seen(self, job_id: str) -> bool:
        """Return True if this job_id has been seen before."""
        with self._lock:
            c = self.conn.cursor()
            c.execute('SELECT 1 FROM seen_jobs WHERE job_id = ?', (job_id,))
            return c.fetchone() is not None

    def is_seen_candidate(self, title: str, company: str = "", link: str = "") -> bool:
        """Computes hash and checks if title + company + link combination has been seen.
        
        Uses the same hash algorithm as Job.__post_init__ to ensure early-skip
        optimization works correctly during scraping.
        """
        import hashlib
        try:
            from scrapers import normalize_title_company_for_hash
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
        if not job_ids:
            return
        now = time.time()
        records = [(jid, now) for jid in job_ids]
        with self._lock:
            self.conn.executemany('INSERT OR IGNORE INTO seen_jobs (job_id, seen_at) VALUES (?, ?)', records)
            self.conn.commit()

    def filter_new(self, jobs) -> list:
        """Return only jobs whose job_id hasn't been seen before, deduplicating across current batch as well."""
        if not jobs:
            return []
            
        job_ids = list(set(j.job_id for j in jobs))
        # Handle SQLite limits (max 999 variables per query in older sqlite versions)
        seen_in_db = set()
        
        with self._lock:
            c = self.conn.cursor()
            for i in range(0, len(job_ids), 900):
                chunk = job_ids[i:i+900]
                placeholders = ','.join('?' * len(chunk))
                c.execute(f'SELECT job_id FROM seen_jobs WHERE job_id IN ({placeholders})', chunk)
                seen_in_db.update(row[0] for row in c.fetchall())

        unseen_jobs = []
        seen_in_batch = set()
        for j in jobs:
            if j.job_id in seen_in_db or j.job_id in seen_in_batch:
                continue
            seen_in_batch.add(j.job_id)
            unseen_jobs.append(j)
            
        return unseen_jobs

    def save(self) -> None:
        """Persist the store to disk. In SQLite mode, this is a no-op as writes auto-commit."""
        pass

    @property
    def count(self) -> int:
        """Number of tracked job IDs."""
        with self._lock:
            c = self.conn.cursor()
            c.execute('SELECT COUNT(*) FROM seen_jobs')
            return c.fetchone()[0]

    # ── Internal ──────────────────────────────────────

    def _prune(self) -> None:
        """Remove entries older than MAX_AGE_DAYS."""
        cutoff = time.time() - (MAX_AGE_DAYS * 86400)
        with self._lock:
            c = self.conn.cursor()
            c.execute('DELETE FROM seen_jobs WHERE seen_at < ?', (cutoff,))
            pruned = c.rowcount
            self.conn.commit()
            
        if pruned > 0:
            logger.info(f"Pruned {pruned} expired entries (>{MAX_AGE_DAYS} days old).")

