# Internet-facing private beta ingress

This directory is a deployment **template and runbook**, not a deployed service.
It exposes the existing single-worker backend on `192.168.11.11` only through
the already trusted HTTPS nginx virtual host at
`https://ching-tech.ddns.net/taigi-tts`. It does not modify provider secrets,
open a backend host port, obtain a certificate, change router/firewall rules, or
submit the Chrome Web Store item.

The formal private-beta extension ID is
`nejhlfbnjkbdjcaaklaofggkikdlpakn`. That ID and its Origin are public and
forgeable; they are only defense in depth. Every actual `/v1/` request must also
pass the backend's per-tester Bearer authentication, durable quota, owner-bound
job checks, and process-capacity controls.

## Security boundary and go/no-go checks

Keep using [`deploy/lan/compose.yaml`](../lan/compose.yaml) and its private
Docker network instead of duplicating the backend deployment. Before enabling
the Internet location, all of these conditions are mandatory:

- The backend has no `ports:` mapping. Only nginx and the one backend container
  are members of `taigi_news_reader_edge`; public firewall/NAT exposes HTTPS
  only, never port 8765.
- The backend uses exactly one replica and one uvicorn worker. Its job registry
  is process-local. The quota SQLite file remains on the `quota-data` volume and
  fails closed on database errors. Merge this directory's Compose override so
  the beta container has a 2 GiB hard memory/no-swap cap; an OOM is a failed
  request, not permission to exhaust the shared host. Its four-core CPU quota
  preserves practical local MMS latency without consuming every core on a
  larger shared host.
- The Compose override itself fixes `TAIGI_REQUIRE_ACCESS_TOKEN=true`, the
  exact formal ID in `TAIGI_EXTENSION_IDS`,
  `TAIGI_ALLOW_LOCALHOST_ORIGINS=false`,
  `TAIGI_REQUIRE_ALLOWED_ORIGIN=true`, and
  `TAIGI_ALLOW_DIRECT_SYNTHESIS=false`. The effective backend environment must
  additionally contain a non-empty list of independently
  revocable `TAIGI_ACCESS_TOKEN_HASHES`, all subject/global daily quota values,
  and all active/outstanding/terminal-byte caps from
  [`deploy/lan/backend.env.example`](../lan/backend.env.example). Never print the
  effective environment during review.
- The beta override narrows each request to 600 source characters, 6,000
  translated characters, and 16 MiB generated audio. The extension currently
  sends 500-character chunks, so 600 leaves source headroom; the translated-text
  bound accommodates normal expansion from Chinese into POJ without retaining
  the broad LAN diagnostic limit. Daily limits are exactly 20 jobs/12,000 source
  characters per subject and 100 jobs/60,000 source characters globally. These
  are independent hard counters; do not describe byte limits as an audio
  duration guarantee.
- Each tester and reviewer receives a different high-entropy token. Only its
  SHA-256 digest and a non-personal stable subject are configured server-side.
  Raw tokens never enter this repo, the extension ZIP, a URL, nginx config,
  screenshots, request logs, or test output. Provider keys also remain only in
  the target's untracked secret storage, and previously disclosed keys must be
  revoked before this ingress is enabled.
- The existing TLS certificate validates normally from an external network.
  Do not use `curl -k`. Confirm the public DNS result and certificate belong to
  the intended host before changing ingress.
- nginx receives Internet connections directly (normal router NAT is fine).
  The effective server must not enable `real_ip_header`, broad
  `set_real_ip_from`, PROXY protocol, or another mechanism that lets an
  arbitrary client change `$remote_addr`. This template intentionally ignores
  incoming `X-Forwarded-For` and keys limits on direct `$binary_remote_addr`.
  If a CDN or load balancer is introduced, stop here and design a separately
  reviewed trusted-proxy configuration pinned to that provider's source ranges.
- Provider data controls and the Chrome Web Store privacy disclosure are
  complete. In particular, confirm the replacement Groq project's required
  retention/ZDR setting before sending real news text.

The included nginx controls are request-size, request-rate, and connection
limits per direct source address plus a 24-request global concurrency ceiling
on this one host. They are **not a WAF**, bot detection, account system,
or volumetric DDoS protection. A saturated home uplink or large distributed
attack can still make the service unavailable. A broader public launch needs a
managed edge/WAF or equivalent reviewed protection; do not describe this beta
template as providing one.

## Stage and validate without enabling it

Back up the target nginx Compose file and configuration first. Build the exact
reviewed backend revision, then merge the small beta override with the existing
LAN Compose definition. The override fixes strict authentication/origin policy
and the formal extension ID, disables direct synthesis, narrows
per-request/daily bounds, and adds CPU/memory/no-swap caps without copying
secrets or the full service definition. Because strict authentication is fixed
here, a missing `TAIGI_ACCESS_TOKEN_HASHES` makes application startup fail:

```bash
cd deploy/private-beta
docker compose --env-file ../lan/lan.env \
  -f ../lan/compose.yaml -f compose.override.yaml config -q
docker compose --env-file ../lan/lan.env \
  -f ../lan/compose.yaml -f compose.override.yaml build backend
docker compose --env-file ../lan/lan.env \
  -f ../lan/compose.yaml -f compose.override.yaml up -d backend

CONTAINER=$(docker compose --env-file ../lan/lan.env \
  -f ../lan/compose.yaml -f compose.override.yaml ps -q backend)
docker inspect --format '{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}} {{.HostConfig.CpuQuota}} {{.HostConfig.CpuPeriod}}' \
  "$CONTAINER"
```

Both reported byte values must be `2147483648`; `docker inspect` must also show
a `400000` CPU quota with the normal `100000` period. Startup must fail closed
if direct synthesis is enabled while strict token mode is active. Do not use an
unreviewed image that predates this check.

Copy the two private-beta nginx files to paths managed by the existing nginx
deployment, leaving the repo's LAN files unchanged:

```bash
install -m 0644 nginx/00-taigi-private-beta-http.conf.example \
  /home/ct/nginx/00-taigi-private-beta-http.conf
install -m 0644 nginx/taigi-private-beta-locations.inc \
  /home/ct/nginx/taigi-private-beta-locations.inc
```

The first file must be loaded once in nginx's `http` context. Keep the `.inc`
suffix on the second file so a `conf.d/*.conf` glob cannot load `location`
directives at the wrong context. Test the repo copies in isolation:

```bash
docker run --rm \
  -v "$PWD/nginx:/config:ro" \
  nginx:1.29.3-alpine \
  nginx -t -c /config/nginx.conf.test
docker run --rm \
  -v "$PWD/nginx:/beta:ro" \
  -v "$PWD/../lan/nginx:/lan:ro" \
  nginx:1.29.3-alpine \
  nginx -t -c /beta/nginx.with-lan-http.conf.test
```

Then inspect the **effective** target configuration without writing it to a
shared log or issue. Confirm there is no inherited real-IP trust, request-body
logging, Authorization logging, or second public route to this backend:

```bash
docker exec nginx nginx -t
docker exec nginx nginx -T > /tmp/nginx-private-beta-effective.conf
grep -nE '^[[:space:]]*(real_ip_header|set_real_ip_from)[[:space:]]|^[[:space:]]*listen .*proxy_protocol' \
  /tmp/nginx-private-beta-effective.conf
grep -nE -A 12 '^[[:space:]]*log_format[[:space:]]' \
  /tmp/nginx-private-beta-effective.conf
rm -f /tmp/nginx-private-beta-effective.conf
docker network inspect taigi_news_reader_edge
```

The first grep must return no effective real-IP directives. Inspect every log
format shown by the second command and reject any that includes Authorization,
cookies, request bodies, or news text. The expected
`proxy_set_header Authorization` lines in this template are necessary to
authenticate at the app and are not log directives. Network inspection must
show only nginx and the backend.

In the existing TLS `server` block, replace the live LAN location include with:

```nginx
include /home/ct/nginx/taigi-private-beta-locations.inc;
```

Do not include both location files: they own identical paths. The separate
`00-taigi-private-beta-http.conf` uses unique maps, zones, and upstream names, so
the unchanged LAN `http` helpers may remain loaded for fast rollback. Run
`nginx -t` inside the real container and reload only after it succeeds:

```bash
docker exec nginx nginx -t
docker exec nginx nginx -s reload
```

The edge exposes exactly:

- public, non-billable `GET /taigi-tts/health` (Authorization is stripped);
- authenticated `GET /taigi-tts/v1/access`;
- authenticated async job `POST`, status `GET`, and cleanup `DELETE` routes,
  plus their exact-Origin CORS preflights.

`POST /taigi-tts/v1/synthesize` and every other `/taigi-tts/` path return 404.
All exposed responses are `no-store`; request bodies are capped at 32 KiB for
job creation and 1 KiB elsewhere. API access logs are off, cookies are stripped,
proxy caching/storage is disabled, request buffering is disabled on `/v1/`, and
forwarded client addresses are overwritten with direct `$remote_addr`.
The public identity/Origin check uses an internal `auth_request`, which runs
after nginx's pre-access request/connection limit modules; rejected identities
do not bypass those limits through an early rewrite return. The backend still
independently requires the exact identity and Bearer token before provider work.
For `/v1/`, nginx removes upstream CORS fields and emits one pinned
`chrome-extension://nejhlfbnjkbdjcaaklaofggkikdlpakn` value only when that exact
Origin was received. There is no reflection or wildcard. This keeps edge 403
and 429 responses readable by the formal extension and exposes only the
four quota/rate-limit headers; an untrusted Origin receives no CORS permission.
nginx error logs can still contain client IP, method, path, status, and limit
events, but must never be configured to include Authorization, cookies, request
bodies, or news text. Do not enable nginx debug logging in production.

## External smoke test

Run these from a non-LAN network before giving the build to a reviewer. Use the
exact URL and never bypass TLS validation:

```bash
BASE=https://ching-tech.ddns.net/taigi-tts
ID=nejhlfbnjkbdjcaaklaofggkikdlpakn

curl --fail --show-error "$BASE/health"
curl -i -X POST "$BASE/v1/synthesize"
curl -i "$BASE/v1/access" \
  -H "Origin: chrome-extension://$ID" \
  -H "X-Taigi-Extension-Id: $ID" \
  -H 'Authorization: Bearer deliberately-invalid'
curl -i "$BASE/v1/access" \
  -H "Origin: chrome-extension://$ID" \
  -H 'X-Taigi-Extension-Id: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  -H 'Authorization: Bearer deliberately-invalid'
curl -i -X OPTIONS "$BASE/v1/synthesis-jobs" \
  -H "Origin: chrome-extension://$ID" \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type,x-taigi-extension-id'
curl -i -X OPTIONS "$BASE/v1/synthesis-jobs" \
  -H 'Origin: https://not-allowed.example' \
  -H 'Access-Control-Request-Method: POST'
```

Expected results are health 200, sync route 404, generic invalid-token 401,
wrong-identity 403, allowed preflight 200 with only the formal extension Origin,
and wrong-Origin 403 without an allow-origin header. The 401 and identity 403
must each carry exactly one formal `Access-Control-Allow-Origin`, never `*`, so
the extension can read the status. Missing/wrong extension identity must fail
before provider work. Confirm the health request has no Authorization at the
backend and none of these calls produces provider traffic.

For the authenticated smoke, read a dedicated low-quota test token without
placing it in shell history or curl's argument list. `printf` is a bash builtin;
curl reads the sensitive header from standard input:

```bash
read -rsp 'private-beta token: ' TOKEN; echo
auth_curl() {
  printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" |
    curl --config - "$@"
}

auth_curl --fail --show-error "$BASE/v1/access" \
  -H "Origin: chrome-extension://$ID" \
  -H "X-Taigi-Extension-Id: $ID"
auth_curl --fail --show-error -X POST "$BASE/v1/synthesis-jobs" \
  -H "Origin: chrome-extension://$ID" \
  -H "X-Taigi-Extension-Id: $ID" \
  -H 'Content-Type: application/json' \
  --data '{"text":"今天天氣很好。","rate":1.0}'

unset -f auth_curl
unset TOKEN
```

Capture the returned UUID locally, then poll the exact job path with the same
stdin-header pattern until it completes. Verify the first completed GET returns
real Taiwanese WAV data, the second GET is 404 (one-shot egress), and DELETE is
204. With a second tester token, GET and DELETE of the first subject's UUID must
both look like an unknown job (404). Verify a deliberately low test quota returns
429 and UTC retry/quota headers without a provider call. Finally, send enough
unauthenticated create requests from the same external IP to observe edge 429;
wait for the rate window before continuing. Do not run quota or rate-limit tests
with the reviewer's production allowance.

From the target, separately confirm the backend still has no host port, the
quota database survives a backend restart, only the current UTC day's counters
remain, and the container stays at one replica/worker. Complete the extension's
fresh-profile, STOP, replay-cache-hit-with-zero-network, and cache-clear tests.
Record only statuses, counts, package hash, and timestamps—never raw tokens,
token digests, provider keys, tester identifiers, article text, or audio.

## Rollback

Rollback changes ingress before stopping the backend:

1. Restore the backed-up TLS server configuration (or swap the include back to
   `/home/ct/nginx/taigi-locations.inc`).
2. Run `docker exec nginx nginx -t`. If it fails, do not reload or restart;
   repair the staged files while the old master continues serving.
3. Reload nginx, then externally verify `/taigi-tts` is no longer public and
   confirm all unrelated virtual hosts and TLS certificates still work.
4. Remove the private-beta live copies only after no server references them.
   The repo templates and LAN templates remain untouched.
5. Revoke beta invite-token hashes if the exposure is ending. Stop the backend
   only after ingress is closed; keep the dedicated network and quota volume
   unless the operator has separately approved their deletion.

If authentication, quota storage, exact-ID checks, external TLS, or source-IP
limits fail at any point, perform this rollback and do not submit the Web Store
item.
