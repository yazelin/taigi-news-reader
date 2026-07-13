from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BETA = ROOT / "deploy" / "private-beta"


def read(relative_path: str) -> str:
    return (BETA / relative_path).read_text(encoding="utf-8")


def test_private_beta_is_separate_and_pins_only_formal_store_identity():
    http = read("nginx/00-taigi-private-beta-http.conf.example")
    locations = read("nginx/taigi-private-beta-locations.inc")
    formal_id = "nejhlfbnjkbdjcaaklaofggkikdlpakn"

    assert f"~^chrome-extension://{formal_id}$ 1;" in http
    assert f"~^{formal_id}\\|$ 1;" in http
    assert f"~^{formal_id}\\|chrome-extension://{formal_id}$ 1;" in http
    assert "REPLACE_WITH_32_CHARACTER_EXTENSION_ID" not in http
    assert (
        'map "$request_method|$taigi_beta_identity_allowed|'
        '$taigi_beta_origin_allowed" '
        "$taigi_beta_edge_gate_allowed" in http
    )
    assert "auth_request /_taigi-private-beta-identity-gate;" in locations
    assert locations.count("auth_request /_taigi-private-beta-identity-gate;") == 3
    assert "if ($taigi_beta_edge_gate_allowed = 0) { return 403; }" in locations
    assert "~^OPTIONS\\|[01]\\|1$ 1;" in http
    assert "~^(?:GET|POST|DELETE)\\|1\\|[01]$ 1;" in http
    assert locations.count("limit_except ") == 4
    assert "$taigi_beta_request_allowed" not in http + locations
    assert not (BETA / "compose.yaml").exists()
    assert not (BETA / "backend.env.example").exists()


def test_private_beta_compose_override_adds_only_fail_closed_bounds():
    override = read("compose.override.yaml")

    assert "TAIGI_ALLOW_DIRECT_SYNTHESIS: \"false\"" in override
    assert "mem_limit: 2g" in override
    assert "mem_reservation: 512m" in override
    assert "memswap_limit: 2g" in override
    assert 'cpus: "4.0"' in override
    assert 'TAIGI_MAX_TEXT_CHARS: "600"' in override
    assert 'TAIGI_MAX_TRANSLATED_CHARS: "2000"' in override
    assert 'TAIGI_MAX_AUDIO_BYTES: "16777216"' in override
    assert 'TAIGI_DAILY_SUBJECT_JOB_LIMIT: "20"' in override
    assert 'TAIGI_DAILY_SUBJECT_CHARACTER_LIMIT: "12000"' in override
    assert 'TAIGI_DAILY_GLOBAL_JOB_LIMIT: "100"' in override
    assert 'TAIGI_DAILY_GLOBAL_CHARACTER_LIMIT: "60000"' in override
    assert "ports:" not in override
    assert "env_file:" not in override
    assert "TAIGI_OPENAI_API_KEY" not in override


def test_private_beta_limits_direct_peer_and_does_not_trust_forwarded_input():
    http = read("nginx/00-taigi-private-beta-http.conf.example")
    locations = read("nginx/taigi-private-beta-locations.inc")

    assert http.count("limit_req_zone $binary_remote_addr") == 4
    assert "limit_conn_zone $binary_remote_addr" in http
    assert (
        "limit_conn_zone $server_name zone=taigi_beta_global_connections:1m;"
        in http
    )
    assert "limit_req_status" not in http
    assert "limit_conn_status" not in http
    directives = tuple(line.lstrip() for line in http.splitlines())
    assert not any(line.startswith("real_ip_header ") for line in directives)
    assert not any(line.startswith("set_real_ip_from ") for line in directives)
    assert "$http_x_forwarded_for" not in http + locations
    assert "$proxy_add_x_forwarded_for" not in locations
    assert locations.count("proxy_set_header X-Forwarded-For $remote_addr;") == 4
    assert locations.count("limit_conn taigi_beta_connections 6;") == 4
    assert locations.count("limit_conn taigi_beta_global_connections 24;") == 4
    assert sum(
        line.strip() == "send_timeout 30s;" for line in locations.splitlines()
    ) == 4
    assert "client_max_body_size 32k;" in locations
    assert locations.count("limit_req_status 429;") == 4
    assert locations.count("limit_conn_status 429;") == 4
    assert locations.count("server_tokens off;") == 8


def test_private_beta_exposes_only_health_access_and_async_jobs():
    locations = read("nginx/taigi-private-beta-locations.inc")

    assert "location = /taigi-tts/health" in locations
    assert "location = /taigi-tts/v1/access" in locations
    assert "location = /taigi-tts/v1/synthesis-jobs" in locations
    assert "location ^~ /taigi-tts/v1/synthesis-jobs/" in locations
    assert "location = /taigi-tts/v1/synthesize" in locations
    assert "location ^~ /taigi-tts/v1/" in locations
    assert "location ^~ /taigi-tts/" in locations
    assert "location = /taigi-tts {" in locations
    assert locations.count("return 404;") == 4
    assert (
        "proxy_pass http://taigi_private_beta_backend/v1/synthesize" not in locations
    )
    assert (
        locations.count("proxy_set_header Authorization $http_authorization;") == 3
    )
    assert 'proxy_set_header Authorization "";' in locations
    assert locations.count("access_log off;") == 9
    assert "$request_body" not in locations
    assert "$http_cookie" not in locations
    assert locations.count('proxy_set_header Cookie "";') == 4
    assert locations.count('proxy_set_header Forwarded "";') == 4


def test_private_beta_edge_errors_use_only_pinned_readable_cors():
    http = read("nginx/00-taigi-private-beta-http.conf.example")
    locations = read("nginx/taigi-private-beta-locations.inc")
    formal_origin = "chrome-extension://nejhlfbnjkbdjcaaklaofggkikdlpakn"

    assert "map $http_origin $taigi_beta_cors_origin" in http
    assert f'~^{formal_origin}$ "{formal_origin}";' in http
    assert "Access-Control-Allow-Origin *" not in http + locations
    assert locations.count(
        "add_header Access-Control-Allow-Origin $taigi_beta_cors_origin always;"
    ) == 5
    assert locations.count(
        'add_header Access-Control-Allow-Headers "Authorization, Content-Type, '
        'X-Taigi-Extension-Id" always;'
    ) == 5
    assert locations.count(
        'add_header Access-Control-Expose-Headers "Retry-After, X-RateLimit-Reset, '
        'X-RateLimit-Remaining, X-RateLimit-Scope" always;'
    ) == 5
    assert locations.count('add_header Vary "Origin" always;') == 5
    assert locations.count("proxy_hide_header Access-Control-Allow-Origin;") == 3
    assert locations.count("proxy_hide_header Access-Control-Expose-Headers;") == 3
    assert locations.count("proxy_hide_header Vary;") == 3


def test_private_beta_uses_no_store_headers_and_streams_job_results():
    locations = read("nginx/taigi-private-beta-locations.inc")

    assert locations.count('add_header Cache-Control "no-store, max-age=0" always;') == 8
    assert locations.count(
        'add_header Strict-Transport-Security "max-age=31536000" always;'
    ) == 8
    assert locations.count('add_header X-Content-Type-Options "nosniff" always;') == 8
    assert locations.count("proxy_buffering off;") == 2
    assert locations.count("proxy_request_buffering off;") == 3
    assert locations.count("proxy_cache off;") == 4
    assert locations.count("proxy_store off;") == 4
    assert locations.count("proxy_hide_header Set-Cookie;") == 4
    assert "proxy_pass http://taigi_private_beta_backend/health;" in locations
    assert "proxy_pass http://taigi_private_beta_backend/v1/access;" in locations
    assert "proxy_pass http://taigi_private_beta_backend/v1/synthesis-jobs;" in locations


def test_private_beta_runbook_is_fail_closed_and_honest_about_edge_limits():
    runbook = read("README.md")

    for required in (
        "TAIGI_REQUIRE_ACCESS_TOKEN=true",
        "TAIGI_REQUIRE_ALLOWED_ORIGIN=true",
        "TAIGI_ALLOW_LOCALHOST_ORIGINS=false",
        "TAIGI_ALLOW_DIRECT_SYNTHESIS=false",
        "TAIGI_ACCESS_TOKEN_HASHES",
        "one uvicorn worker",
        "not a WAF",
        "volumetric DDoS protection",
        "Do not use `curl -k`",
        "must never be configured to include Authorization",
        "second tester token",
        "one-shot egress",
        "docker exec nginx nginx -t",
        "Rollback",
    ):
        assert required in runbook

    assert "docker exec nginx nginx -s reload" in runbook
    assert "never port 8765" in runbook
    assert "do not submit the Web Store" in runbook


def test_private_beta_nginx_syntax_harnesses_cover_rollback_state():
    harness = read("nginx/nginx.conf.test")
    combined = read("nginx/nginx.with-lan-http.conf.test")

    assert "include /config/00-taigi-private-beta-http.conf.example;" in harness
    assert "include /config/taigi-private-beta-locations.inc;" in harness
    assert "deploy/lan" not in harness
    assert "include /lan/00-taigi-http.conf.example;" in combined
    assert "include /beta/00-taigi-private-beta-http.conf.example;" in combined
    assert "include /beta/taigi-private-beta-locations.inc;" in combined
    assert "include /lan/taigi-locations.inc;" not in combined
