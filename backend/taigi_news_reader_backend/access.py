"""Invite-token authentication and durable daily quota accounting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import hmac
import math
from pathlib import Path
import re
import sqlite3
import threading
from typing import Callable, Iterable

from .config import AccessTokenHash, Settings


OPEN_ACCESS_SUBJECT = "local-open-access"
_BEARER_PATTERN = re.compile(r"(?i:Bearer) ([^\s]{1,512})\Z")
_DUMMY_TOKEN = b"invalid-or-missing-bearer-token"


class TokenAuthenticator:
    """Match opaque bearer tokens without retaining their plaintext values."""

    def __init__(self, entries: Iterable[AccessTokenHash]) -> None:
        self._entries = tuple(entries)

    def authenticate(self, authorization: str | None) -> str | None:
        match = _BEARER_PATTERN.fullmatch(authorization or "")
        candidate = match.group(1).encode("utf-8") if match else _DUMMY_TOKEN
        digest = hashlib.sha256(candidate).hexdigest()
        matched_subject: str | None = None

        # Always compare against every configured digest. This prevents an
        # entry's position from becoming a useful timing signal.
        for entry in self._entries:
            matches = hmac.compare_digest(digest, entry.sha256)
            if matches and match is not None:
                matched_subject = entry.subject
        return matched_subject


@dataclass(frozen=True, slots=True)
class QuotaSnapshot:
    subject: str
    utc_date: date
    resets_at: datetime
    subject_jobs: int
    subject_characters: int
    global_jobs: int
    global_characters: int
    subject_job_limit: int
    subject_character_limit: int
    global_job_limit: int
    global_character_limit: int


class QuotaExceededError(RuntimeError):
    """A request would exceed a configured UTC-day quota."""

    def __init__(self, *, scope: str, resets_at: datetime) -> None:
        super().__init__("daily synthesis quota exceeded")
        self.scope = scope
        self.resets_at = resets_at

    def response_headers(self, now: datetime | None = None) -> dict[str, str]:
        current = now or datetime.now(UTC)
        retry_seconds = max(
            1,
            math.ceil((self.resets_at - current.astimezone(UTC)).total_seconds()),
        )
        return {
            "Retry-After": str(retry_seconds),
            "X-RateLimit-Reset": str(int(self.resets_at.timestamp())),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Scope": self.scope,
        }


class DailyQuotaStore:
    """SQLite-backed, transactionally enforced per-subject and global quotas."""

    def __init__(
        self,
        database_path: str,
        *,
        subject_job_limit: int,
        subject_character_limit: int,
        global_job_limit: int,
        global_character_limit: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._database_path = database_path
        self._subject_job_limit = subject_job_limit
        self._subject_character_limit = subject_character_limit
        self._global_job_limit = global_job_limit
        self._global_character_limit = global_character_limit
        self._clock = clock
        self._lock = threading.RLock()

        if database_path != ":memory:":
            parent = Path(database_path).expanduser().resolve().parent
            if not parent.is_dir():
                raise ValueError(
                    f"quota database parent directory does not exist: {parent}"
                )

        self._connection = sqlite3.connect(
            database_path,
            timeout=10,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.execute("PRAGMA busy_timeout = 10000")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_usage (
                utc_date TEXT NOT NULL,
                subject TEXT NOT NULL,
                jobs INTEGER NOT NULL CHECK (jobs >= 0),
                characters INTEGER NOT NULL CHECK (characters >= 0),
                PRIMARY KEY (utc_date, subject)
            ) WITHOUT ROWID
            """
        )
        _, today, _ = self._current_day()
        self._prune_other_days(today)

    @classmethod
    def from_settings(cls, settings: Settings) -> "DailyQuotaStore":
        return cls(
            settings.quota_database_path,
            subject_job_limit=settings.daily_subject_job_limit,
            subject_character_limit=settings.daily_subject_character_limit,
            global_job_limit=settings.daily_global_job_limit,
            global_character_limit=settings.daily_global_character_limit,
        )

    def reserve(self, subject: str, characters: int) -> QuotaSnapshot:
        if characters < 0:
            raise ValueError("characters must not be negative")
        _, today, resets_at = self._current_day()

        with self._lock:
            cursor = self._connection.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE")
                # Only the current UTC day is operationally useful. Removing
                # older rows minimizes retained usage metadata.
                cursor.execute(
                    "DELETE FROM daily_usage WHERE utc_date <> ?",
                    (today.isoformat(),),
                )
                subject_jobs, subject_characters = self._subject_usage(
                    cursor, today, subject
                )
                global_jobs, global_characters = self._global_usage(cursor, today)

                proposed = {
                    "subject_jobs": subject_jobs + 1,
                    "subject_characters": subject_characters + characters,
                    "global_jobs": global_jobs + 1,
                    "global_characters": global_characters + characters,
                }
                limits = {
                    "subject_jobs": self._subject_job_limit,
                    "subject_characters": self._subject_character_limit,
                    "global_jobs": self._global_job_limit,
                    "global_characters": self._global_character_limit,
                }
                for scope in (
                    "subject_jobs",
                    "subject_characters",
                    "global_jobs",
                    "global_characters",
                ):
                    if proposed[scope] > limits[scope]:
                        # Commit only the privacy-minimizing stale-row prune;
                        # no usage increment has happened yet.
                        cursor.execute("COMMIT")
                        raise QuotaExceededError(
                            scope=scope,
                            resets_at=resets_at,
                        )

                cursor.execute(
                    """
                    INSERT INTO daily_usage (utc_date, subject, jobs, characters)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT (utc_date, subject) DO UPDATE SET
                        jobs = jobs + 1,
                        characters = characters + excluded.characters
                    """,
                    (today.isoformat(), subject, characters),
                )
                cursor.execute("COMMIT")
            except QuotaExceededError:
                raise
            except BaseException:
                if self._connection.in_transaction:
                    cursor.execute("ROLLBACK")
                raise
            finally:
                cursor.close()

        return self._snapshot(
            subject,
            today,
            resets_at,
            proposed["subject_jobs"],
            proposed["subject_characters"],
            proposed["global_jobs"],
            proposed["global_characters"],
        )

    def status(self, subject: str) -> QuotaSnapshot:
        _, today, resets_at = self._current_day()
        with self._lock:
            cursor = self._connection.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE")
                cursor.execute(
                    "DELETE FROM daily_usage WHERE utc_date <> ?",
                    (today.isoformat(),),
                )
                subject_jobs, subject_characters = self._subject_usage(
                    cursor, today, subject
                )
                global_jobs, global_characters = self._global_usage(cursor, today)
                cursor.execute("COMMIT")
            except BaseException:
                if self._connection.in_transaction:
                    cursor.execute("ROLLBACK")
                raise
            finally:
                cursor.close()
        return self._snapshot(
            subject,
            today,
            resets_at,
            subject_jobs,
            subject_characters,
            global_jobs,
            global_characters,
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _prune_other_days(self, today: date) -> None:
        with self._lock:
            cursor = self._connection.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE")
                cursor.execute(
                    "DELETE FROM daily_usage WHERE utc_date <> ?",
                    (today.isoformat(),),
                )
                cursor.execute("COMMIT")
            except BaseException:
                if self._connection.in_transaction:
                    cursor.execute("ROLLBACK")
                raise
            finally:
                cursor.close()

    def _current_day(self) -> tuple[datetime, date, datetime]:
        current = self._clock()
        if current.tzinfo is None:
            raise ValueError("quota clock must return a timezone-aware datetime")
        current = current.astimezone(UTC)
        today = current.date()
        resets_at = datetime.combine(today + timedelta(days=1), datetime.min.time(), UTC)
        return current, today, resets_at

    @staticmethod
    def _subject_usage(
        cursor: sqlite3.Cursor, today: date, subject: str
    ) -> tuple[int, int]:
        row = cursor.execute(
            "SELECT jobs, characters FROM daily_usage WHERE utc_date = ? AND subject = ?",
            (today.isoformat(), subject),
        ).fetchone()
        return (int(row[0]), int(row[1])) if row is not None else (0, 0)

    @staticmethod
    def _global_usage(cursor: sqlite3.Cursor, today: date) -> tuple[int, int]:
        row = cursor.execute(
            """
            SELECT COALESCE(SUM(jobs), 0), COALESCE(SUM(characters), 0)
            FROM daily_usage WHERE utc_date = ?
            """,
            (today.isoformat(),),
        ).fetchone()
        assert row is not None
        return int(row[0]), int(row[1])

    def _snapshot(
        self,
        subject: str,
        today: date,
        resets_at: datetime,
        subject_jobs: int,
        subject_characters: int,
        global_jobs: int,
        global_characters: int,
    ) -> QuotaSnapshot:
        return QuotaSnapshot(
            subject=subject,
            utc_date=today,
            resets_at=resets_at,
            subject_jobs=subject_jobs,
            subject_characters=subject_characters,
            global_jobs=global_jobs,
            global_characters=global_characters,
            subject_job_limit=self._subject_job_limit,
            subject_character_limit=self._subject_character_limit,
            global_job_limit=self._global_job_limit,
            global_character_limit=self._global_character_limit,
        )
