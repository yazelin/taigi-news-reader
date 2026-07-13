from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAN = ROOT / "deploy" / "lan"


def read(relative_path: str) -> str:
    return (LAN / relative_path).read_text(encoding="utf-8")


def test_compose_keeps_uvicorn_off_host_ports_and_drops_privileges():
    compose = read("compose.yaml")
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert "ports:" not in compose
    assert 'expose:\n      - "8765"' in compose
    assert "external: true" in compose
    assert "name: taigi_news_reader_edge" in compose
    assert "nginx_bridge_network" not in compose
    assert compose.count("taigi_news_reader_edge:") == 2
    assert "- taigi-news-reader" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose and "- ALL" in compose
    assert "USER taigi" in dockerfile


def test_lan_environment_is_fail_closed_and_contains_no_example_secret():
    environment = read("backend.env.example")

    assert "TAIGI_OPENAI_API_KEY=\n" in environment
    assert "TAIGI_OPENAI_BASE_URL=https://api.groq.com/openai/v1" in environment
    assert "TAIGI_OPENAI_MODEL=openai/gpt-oss-120b" in environment
    assert "TAIGI_EXTENSION_IDS=\n" in environment
    assert "TAIGI_ALLOW_LOCALHOST_ORIGINS=false" in environment
    assert "TAIGI_REQUIRE_ALLOWED_ORIGIN=true" in environment


def test_nginx_template_has_tls_front_door_controls():
    http = read("nginx/00-taigi-http.conf.example")
    locations = read("nginx/taigi-locations.inc")

    assert "map $http_origin $taigi_extension_origin_allowed" in http
    assert "$http_x_taigi_extension_id|$http_origin" in http
    assert "$taigi_extension_identity_allowed" in http
    assert "$taigi_extension_request_allowed" in http
    assert "REPLACE_WITH_32_CHARACTER_EXTENSION_ID|\" 1;" in http
    assert "map_hash_bucket_size 128" in http
    assert "limit_req_zone" in http
    assert "limit_req_status 429" in http
    assert "resolver 127.0.0.11" in http
    assert "server taigi-news-reader:8765 resolve;" in http
    assert "allow 192.168.11.0/24;" in locations
    assert "deny all;" in locations
    assert locations.count(
        "if ($taigi_extension_request_allowed = 0) { return 403; }"
    ) == 2
    assert locations.count(
        "proxy_set_header X-Taigi-Extension-Id $http_x_taigi_extension_id;"
    ) == 2
    assert "client_max_body_size 32k;" in locations
    assert locations.count("proxy_buffering off;") >= 2
    assert "proxy_pass http://taigi_backend/v1/synthesis-jobs;" in locations
    assert "127.0.0.1:8765" not in locations
    assert "location = /taigi-tts/v1/synthesize" in locations
    assert locations.count("return 404;") >= 2

    syntax_harness = read("nginx/nginx.conf.test")
    assert "include /config/00-taigi-http.conf.example;" in syntax_harness
    assert "include /config/taigi-locations.inc;" in syntax_harness
    assert not (LAN / "nginx" / "taigi-locations.conf.example").exists()


def test_lan_runbook_persists_dedicated_nginx_network_and_rollback():
    runbook = read("README.md")

    assert "docker network create --driver bridge taigi_news_reader_edge" in runbook
    assert "/home/ct/nginx/docker-compose.yml" in runbook
    assert "taigi_news_reader_edge: {}" in runbook
    assert "docker compose up -d --no-deps nginx" in runbook
    assert "/home/ct/nginx/taigi-locations.inc" in runbook
    assert "docker network rm taigi_news_reader_edge" in runbook
