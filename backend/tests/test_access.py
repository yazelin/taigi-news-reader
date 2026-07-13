from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import asyncio
import hashlib
from pathlib import Path
import sqlite3

import httpx
import pytest

from taigi_news_reader_backend import access as access_module
from taigi_news_reader_backend.access import (
    DailyQuotaStore,
    QuotaExceededError,
    TokenAuthenticator,
)
from taigi_news_reader_backend.app import create_app
from taigi_news_reader_backend.config import AccessTokenHash, Settings


REQUEST = {
    "text": "今天天氣晴朗。",
    "source_language": "zh-TW",
    "target_language": "nan-TW",
    "rate": 1.0,
}
TOKEN_A = "private-tester-token-A"
TOKEN_B = "private-tester-token-B"


def token_hash(subject: str, token: str) -> AccessTokenHash:
    return AccessTokenHash(
        subject=subject,
        sha256=hashlib.sha256(token.encode()).hexdigest(),
    )


def strict_settings(database: Path, **overrides) -> Settings:
    values = {
        "provider_mode": "mock",
        "require_access_token": True,
        "allow_direct_synthesis": False,
        "access_token_hashes": (
            token_hash("tester-a", TOKEN_A),
            token_hash("tester-b", TOKEN_B),
        ),
        "quota_database_path": str(database),
        "daily_subject_job_limit": 3,
        "daily_subject_character_limit": 100,
        "daily_global_job_limit": 5,
        "daily_global_character_limit": 200,
    }
    values.update(overrides)
    return Settings(**values)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


async def test_local_default_stays_open_and_reports_no_authentication():
    app = create_app(Settings(provider_mode="mock"))

    access = await request(app, "GET", "/v1/access")
    synthesis = await request(app, "POST", "/v1/synthesize", json=REQUEST)

    assert access.status_code == 200
    assert access.json() == {
        "authentication_required": False,
        "subject": None,
        "utc_date": None,
        "resets_at": None,
        "limits": None,
        "used": None,
        "remaining": None,
    }
    assert synthesis.status_code == 200


async def test_strict_access_returns_same_generic_401_for_missing_and_wrong_token(
    tmp_path,
):
    app = create_app(strict_settings(tmp_path / "quota.sqlite"))

    missing = await request(app, "GET", "/v1/access")
    wrong = await request(
        app,
        "GET",
        "/v1/access",
        headers=auth("not-the-token"),
    )
    malformed = await request(
        app,
        "GET",
        "/v1/access",
        headers={"Authorization": "Basic abc"},
    )
    health = await request(app, "GET", "/health")

    for response in (missing, wrong, malformed):
        assert response.status_code == 401
        assert response.json() == {
            "detail": "access credential is not accepted"
        }
        assert response.headers["www-authenticate"] == (
            'Bearer realm="taigi-news-reader"'
        )
        assert response.headers["cache-control"] == "no-store"
    assert health.status_code == 200
    app.state.quota_store.close()


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("POST", "/v1/synthesize", {"json": REQUEST}),
        ("POST", "/v1/synthesis-jobs", {"json": REQUEST}),
        ("GET", "/v1/synthesis-jobs/unknown", {}),
        ("DELETE", "/v1/synthesis-jobs/unknown", {}),
    ],
)
async def test_every_synthesis_route_requires_bearer_authentication(
    tmp_path,
    method,
    path,
    kwargs,
):
    database = tmp_path / f"quota-{method}-{len(path)}.sqlite"
    app = create_app(strict_settings(database))

    response = await request(app, method, path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"detail": "access credential is not accepted"}
    app.state.quota_store.close()


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer token with spaces",
        "Bearer ",
        "Bearer\ttoken",
        "Bearer " + "x" * 513,
        "Bearer token\nsecond-header",
    ],
)
def test_token_parser_rejects_non_opaque_or_oversized_credentials(authorization):
    authenticator = TokenAuthenticator((token_hash("tester-a", TOKEN_A),))

    assert authenticator.authenticate(authorization) is None


def test_token_digest_comparison_checks_every_configured_entry(monkeypatch):
    entries = (
        token_hash("tester-a", TOKEN_A),
        token_hash("tester-b", TOKEN_B),
        token_hash("tester-c", "another-token"),
    )
    calls: list[tuple[str, str]] = []
    original = access_module.hmac.compare_digest

    def recording_compare(left: str, right: str) -> bool:
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr(access_module.hmac, "compare_digest", recording_compare)
    authenticator = TokenAuthenticator(entries)

    assert authenticator.authenticate(f"Bearer {TOKEN_A}") == "tester-a"
    assert len(calls) == len(entries)
    calls.clear()
    assert authenticator.authenticate(None) is None
    assert len(calls) == len(entries)


async def test_access_endpoint_validates_token_and_returns_subject_quota_status(
    tmp_path,
):
    app = create_app(strict_settings(tmp_path / "quota.sqlite"))

    response = await request(
        app,
        "GET",
        "/v1/access",
        headers=auth(TOKEN_A),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["authentication_required"] is True
    assert body["subject"] == "tester-a"
    assert body["used"] == {
        "subject_jobs": 0,
        "subject_characters": 0,
        "global_jobs": 0,
        "global_characters": 0,
    }
    assert body["limits"] == {
        "subject_jobs": 3,
        "subject_characters": 100,
        "global_jobs": 5,
        "global_characters": 200,
    }
    assert body["remaining"] == body["limits"]
    assert body["resets_at"].endswith("Z")
    app.state.quota_store.close()


async def test_strict_private_access_never_registers_direct_synthesis(tmp_path):
    app = create_app(strict_settings(tmp_path / "quota.sqlite"))

    response = await request(
        app,
        "POST",
        "/v1/synthesize",
        headers=auth(TOKEN_A),
        json=REQUEST,
    )

    assert response.status_code == 404
    app.state.quota_store.close()


async def test_cors_preflight_allows_authorization_and_401_is_readable(tmp_path):
    extension_id = "a" * 32
    settings = strict_settings(
        tmp_path / "quota.sqlite",
        extension_ids=(extension_id,),
        allow_localhost_origins=False,
        require_allowed_origin=True,
    )
    app = create_app(settings)
    origin = f"chrome-extension://{extension_id}"

    preflight = await request(
        app,
        "OPTIONS",
        "/v1/access",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": (
                "authorization,x-taigi-extension-id"
            ),
        },
    )
    unauthorized = await request(
        app,
        "GET",
        "/v1/access",
        headers={
            "Origin": origin,
            "X-Taigi-Extension-Id": extension_id,
        },
    )

    assert preflight.status_code == 200
    assert "authorization" in preflight.headers[
        "access-control-allow-headers"
    ].lower()
    assert unauthorized.status_code == 401
    assert unauthorized.headers["access-control-allow-origin"] == origin
    app.state.quota_store.close()


async def test_per_subject_job_quota_is_atomic_and_returns_utc_retry_info(tmp_path):
    app = create_app(
        strict_settings(
            tmp_path / "quota.sqlite",
            daily_subject_job_limit=1,
        )
    )

    accepted = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=REQUEST,
    )
    rejected = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=REQUEST,
    )

    assert accepted.status_code == 202
    assert rejected.status_code == 429
    assert rejected.json() == {"detail": "daily synthesis quota exceeded"}
    assert rejected.headers["x-ratelimit-scope"] == "subject_jobs"
    assert int(rejected.headers["retry-after"]) > 0
    assert int(rejected.headers["x-ratelimit-reset"]) > 0
    status = await request(app, "GET", "/v1/access", headers=auth(TOKEN_A))
    assert status.json()["used"]["subject_jobs"] == 1
    app.state.quota_store.close()


async def test_character_quota_counts_stripped_unicode_text_for_jobs(
    tmp_path,
):
    app = create_app(
        strict_settings(
            tmp_path / "quota.sqlite",
            daily_subject_character_limit=7,
        )
    )
    first = {**REQUEST, "text": "  台語  "}
    second = {**REQUEST, "text": "新聞朗讀測試"}

    accepted = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=first,
    )
    rejected = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=second,
    )

    assert accepted.status_code == 202
    assert rejected.status_code == 429
    assert rejected.headers["x-ratelimit-scope"] == "subject_characters"
    status = await request(app, "GET", "/v1/access", headers=auth(TOKEN_A))
    assert status.json()["used"]["subject_characters"] == 2
    app.state.quota_store.close()


async def test_global_quota_combines_subjects_without_leaking_job_ownership(tmp_path):
    app = create_app(
        strict_settings(
            tmp_path / "quota.sqlite",
            daily_global_job_limit=1,
        )
    )

    created = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=REQUEST,
    )
    job_id = created.json()["job_id"]
    hidden_get = await request(
        app,
        "GET",
        f"/v1/synthesis-jobs/{job_id}",
        headers=auth(TOKEN_B),
    )
    hidden_delete = await request(
        app,
        "DELETE",
        f"/v1/synthesis-jobs/{job_id}",
        headers=auth(TOKEN_B),
    )
    rejected = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_B),
        json=REQUEST,
    )
    owner_get = await request(
        app,
        "GET",
        f"/v1/synthesis-jobs/{job_id}",
        headers=auth(TOKEN_A),
    )

    assert created.status_code == 202
    assert hidden_get.status_code == 404
    assert hidden_delete.status_code == 404
    assert hidden_get.json() == hidden_delete.json() == {
        "detail": "synthesis job not found"
    }
    assert rejected.status_code == 429
    assert rejected.headers["x-ratelimit-scope"] == "global_jobs"
    assert owner_get.status_code == 200
    app.state.quota_store.close()


async def test_global_character_quota_combines_distinct_subjects(tmp_path):
    app = create_app(
        strict_settings(
            tmp_path / "quota.sqlite",
            daily_global_character_limit=10,
        )
    )
    six_characters = {**REQUEST, "text": "一二三四五六"}
    five_characters = {**REQUEST, "text": "七八九十甲"}

    first = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=six_characters,
    )
    second = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_B),
        json=five_characters,
    )

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.headers["x-ratelimit-scope"] == "global_characters"
    app.state.quota_store.close()


class AlwaysFailingService:
    async def synthesize(self, text: str, rate: float):
        from taigi_news_reader_backend.providers import ProviderError

        raise ProviderError("upstream failed")

    async def aclose(self) -> None:
        return None


class NeverFinishingService:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release = asyncio.Event()

    async def synthesize(self, text: str, rate: float):
        self.started.set()
        try:
            await self.release.wait()
            return None
        except asyncio.CancelledError:
            self.cancelled.set()
            raise

    async def aclose(self) -> None:
        return None


async def test_failed_accepted_job_is_not_refunded(tmp_path):
    settings = strict_settings(
        tmp_path / "quota.sqlite",
        daily_subject_job_limit=1,
    )
    service = AlwaysFailingService()
    app = create_app(settings, service=service)
    created = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=REQUEST,
    )
    for _ in range(100):
        failed = await request(
            app,
            "GET",
            f"/v1/synthesis-jobs/{created.json()['job_id']}",
            headers=auth(TOKEN_A),
        )
        if failed.status_code == 200 and failed.json()["status"] == "failed":
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError("job never failed")

    rejected = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=REQUEST,
    )

    assert rejected.status_code == 429
    assert rejected.headers["x-ratelimit-scope"] == "subject_jobs"
    app.state.quota_store.close()


async def test_deleted_accepted_job_is_not_refunded_after_provider_drains(tmp_path):
    settings = strict_settings(
        tmp_path / "quota.sqlite",
        daily_subject_job_limit=1,
        max_active_jobs=1,
    )
    service = NeverFinishingService()
    app = create_app(settings, service=service)
    created = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=REQUEST,
    )
    await asyncio.wait_for(service.started.wait(), timeout=1)
    deleted = await request(
        app,
        "DELETE",
        f"/v1/synthesis-jobs/{created.json()['job_id']}",
        headers=auth(TOKEN_A),
    )
    assert service.cancelled.is_set() is False
    still_active = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=REQUEST,
    )
    assert still_active.status_code == 429
    assert still_active.headers["x-ratelimit-scope"] == "active_jobs"

    service.release.set()
    job_id = created.json()["job_id"]
    for _ in range(100):
        if app.state.job_manager._jobs[job_id].status != "pending":
            break
        await asyncio.sleep(0)
    rejected = await request(
        app,
        "POST",
        "/v1/synthesis-jobs",
        headers=auth(TOKEN_A),
        json=REQUEST,
    )

    assert deleted.status_code == 204
    assert rejected.status_code == 429
    assert rejected.headers["x-ratelimit-scope"] == "subject_jobs"
    app.state.quota_store.close()


def quota_store(database: Path, clock, **overrides) -> DailyQuotaStore:
    values = {
        "subject_job_limit": 2,
        "subject_character_limit": 10,
        "global_job_limit": 3,
        "global_character_limit": 20,
        "clock": clock,
    }
    values.update(overrides)
    return DailyQuotaStore(str(database), **values)


def test_quota_persists_across_restart_and_discards_source_and_token(tmp_path):
    now = lambda: datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
    database = tmp_path / "quota.sqlite"
    store = quota_store(database, now)
    store.reserve("tester-a", 7)
    store.close()

    reopened = quota_store(database, now)
    status = reopened.status("tester-a")

    assert status.subject_jobs == 1
    assert status.subject_characters == 7
    reopened.close()
    connection = sqlite3.connect(database)
    columns = [
        row[1]
        for row in connection.execute("PRAGMA table_info(daily_usage)").fetchall()
    ]
    rows = connection.execute("SELECT * FROM daily_usage").fetchall()
    connection.close()
    assert columns == ["utc_date", "subject", "jobs", "characters"]
    assert rows == [("2026-07-13", "tester-a", 1, 7)]
    database_bytes = database.read_bytes()
    assert TOKEN_A.encode() not in database_bytes
    assert REQUEST["text"].encode() not in database_bytes


def test_quota_resets_at_utc_midnight_and_prunes_the_previous_day(tmp_path):
    current = [datetime(2026, 7, 13, 23, 59, 59, tzinfo=UTC)]
    database = tmp_path / "quota.sqlite"
    store = quota_store(database, lambda: current[0], subject_job_limit=1)
    store.reserve("tester-a", 1)
    with pytest.raises(QuotaExceededError) as caught:
        store.reserve("tester-a", 1)
    assert caught.value.resets_at == datetime(2026, 7, 14, tzinfo=UTC)

    current[0] = datetime(2026, 7, 14, 0, 0, tzinfo=UTC)
    reset = store.reserve("tester-a", 2)

    assert reset.subject_jobs == 1
    assert reset.subject_characters == 2
    rows = store._connection.execute(
        "SELECT utc_date FROM daily_usage"
    ).fetchall()
    assert rows == [("2026-07-14",)]
    store.close()


def test_startup_and_idle_status_prune_non_current_utc_rows(tmp_path):
    current = [datetime(2026, 7, 13, 12, 0, tzinfo=UTC)]
    database = tmp_path / "quota.sqlite"
    store = quota_store(database, lambda: current[0])
    store.reserve("tester-a", 3)
    store.close()

    current[0] = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    reopened = quota_store(database, lambda: current[0])
    assert reopened.status("tester-a").subject_jobs == 0
    assert reopened._connection.execute(
        "SELECT COUNT(*) FROM daily_usage"
    ).fetchone() == (0,)

    reopened.reserve("tester-a", 2)
    current[0] = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    assert reopened.status("tester-a").subject_jobs == 0
    assert reopened._connection.execute(
        "SELECT COUNT(*) FROM daily_usage"
    ).fetchone() == (0,)
    reopened.close()


def test_two_store_instances_cannot_race_past_global_quota(tmp_path):
    now = lambda: datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
    database = tmp_path / "quota.sqlite"
    stores = (
        quota_store(
            database,
            now,
            subject_job_limit=20,
            global_job_limit=10,
            subject_character_limit=100,
            global_character_limit=100,
        ),
        quota_store(
            database,
            now,
            subject_job_limit=20,
            global_job_limit=10,
            subject_character_limit=100,
            global_character_limit=100,
        ),
    )

    def reserve(index: int) -> bool:
        try:
            stores[index % 2].reserve(f"tester-{index}", 1)
        except QuotaExceededError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(reserve, range(20)))

    assert results.count(True) == 10
    assert results.count(False) == 10
    assert stores[0].status("tester-0").global_jobs == 10
    for store in stores:
        store.close()


async def test_revocation_takes_effect_after_hash_is_removed_and_app_restarts(
    tmp_path,
):
    database = tmp_path / "quota.sqlite"
    first = create_app(strict_settings(database))
    assert (
        await request(first, "GET", "/v1/access", headers=auth(TOKEN_A))
    ).status_code == 200
    first.state.quota_store.close()

    revoked_settings = strict_settings(
        database,
        access_token_hashes=(token_hash("tester-b", TOKEN_B),),
    )
    restarted = create_app(revoked_settings)
    revoked = await request(
        restarted,
        "GET",
        "/v1/access",
        headers=auth(TOKEN_A),
    )
    retained = await request(
        restarted,
        "GET",
        "/v1/access",
        headers=auth(TOKEN_B),
    )

    assert revoked.status_code == 401
    assert retained.status_code == 200
    restarted.state.quota_store.close()
