# Taigi News Reader backend

This FastAPI service translates Traditional Chinese news and returns Taiwanese
Hokkien WAV audio. The self-hosted reference path uses Ollama plus Meta's
`facebook/mms-tts-nan` VITS checkpoint; hosted deployments can instead select
the first-class Gemini or generic OpenAI-compatible translator and remote TTS
adapters. Local models load only on the first synthesis request. Provider
failures return an error; the service never falls back to a Mandarin browser
voice.

The bundled Qwen translator is an experimental local reference. Translation
output is checked against the MMS checkpoint's exact POJ character vocabulary
before TTS; Ollama, Gemini, and generic OpenAI-compatible adapters get one strict
repair attempt, then the request fails loudly instead of speaking Chinese,
digits, or unsupported pseudo-romanization. Native-speaker review is still
required before treating its translations as publication-ready.

Gemini uses Google's OpenAI-compatible endpoint directly, without a Google SDK:

```bash
export TAIGI_TRANSLATOR_PROVIDER=gemini
export TAIGI_GEMINI_API_KEY=replace-with-server-side-key
# Defaults:
export TAIGI_GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
export TAIGI_GEMINI_MODEL=gemini-3.5-flash
export TAIGI_GEMINI_TIMEOUT_SECONDS=45
```

The Gemini key stays on the backend. Its adapter uses the same empty-response
retry, exact POJ validation, whitespace normalization, and one strict repair
attempt as the generic OpenAI-compatible adapter. Never commit the key, expose
it to the extension, or print it in client-visible logs.

The first-class Gemini path has been live-tested directly with a real key: a
short sentence and a 116-character news passage both returned HTTP 200, passed
the POJ gate, and produced WAV audio through the local
`facebook/mms-tts-nan` synthesizer. The Chromium 150 async-job E2E also passed:
live health identified concrete Gemini 3.5 Flash plus MMS, and the 116-character
news passage reached `playing` after 50.25 seconds while the service worker
remained alive. The completed job was immediately deleted before offscreen
audio playback; PAUSE, RESUME, and STOP all reached the expected states with no
active job left. Passing this flow and producing WAV do not establish natural
Taiwanese Hokkien quality, so native-speaker and target-user listening review
is still required.

Before using the Gemini API Free tier, note that submitted content may be used
to improve Google products. Operators must disclose that data flow and verify
the terms for the actual account tier; do not treat a hosted request as having
the same privacy boundary as local inference.

## Asynchronous synthesis jobs

The Chrome extension uses the asynchronous job API so no single Manifest V3
fetch must survive a long translation and TTS operation:

1. `POST /v1/synthesis-jobs` returns HTTP 202 with a UUID4 `job_id` and
   `status: "pending"`.
2. Short `GET /v1/synthesis-jobs/{job_id}` requests return `pending`,
   `completed` with the synthesis result, or `failed` with a safe error. A
   terminal response is delivered only once; later GETs return the same 404 as
   an unknown or other subject's job.
3. The client calls `DELETE /v1/synthesis-jobs/{job_id}` after reading a
   terminal result. STOP also sends DELETE, which cancels a still-active task.

Jobs are deliberately process-local and memory-only. The source text exists
only as an argument of the active synthesis task; it is never copied into the
job registry or written to disk. Completed results and safe failure messages
become eligible for opportunistic pruning after 600 seconds; the next job API
operation removes them, while the extension normally deletes them as soon as
it consumes them. IDs are UUID4. Active jobs, all outstanding records,
outstanding records per subject, retained terminal bytes globally, and retained
terminal bytes per subject each have independent caps; excess creation returns
HTTP 429 with retry guidance. A one-shot terminal GET clears its retained
result immediately but leaves a small tombstone so the normal follow-up DELETE
can still succeed. Application shutdown cancels every active task and clears
the registry.

This design has no durable queue: a process restart loses all jobs, and UUID4
is not a substitute for authentication or rate limiting. `POST /v1/synthesize`
remains available for direct API integrations and diagnostics, but the Chrome
flow does not keep that long request open. The offscreen document performs only
Blob conversion and audio playback; it owns no synthesis network request.

## Private-tester access and quotas

Local and mock development stay open by default. A private deployment enables
`TAIGI_REQUIRE_ACCESS_TOKEN=true` and configures
`TAIGI_ACCESS_TOKEN_HASHES` as comma-separated
`pseudonymous-subject=lowercase-sha256` entries. The plaintext invite token is
never configured on the server, bundled in the extension, written to the quota
database, or included in an error. Every actual `/v1/` request then requires
`Authorization: Bearer <invite-token>`; missing, invalid, and revoked values all
receive the same generic 401. Hash comparison checks every configured entry
with `hmac.compare_digest`. Remove a hash and restart to revoke it.

`GET /v1/access` validates the token and returns that subject's current UTC-day
quota plus global usage. Synthesis admission transactionally reserves one job
and the stripped Unicode character count before provider work starts. Accepted
jobs are not refunded after provider failure or cancellation. Per-subject and
global job/character caps are enforced in SQLite with WAL, FULL synchronous,
busy timeout, and `BEGIN IMMEDIATE`; database lock, I/O, or corruption fails the
request closed. Startup, status, and reservation remove non-current dates, so
the durable schema retains only the current UTC date, pseudonymous subject, job
count, and character count—never news text, audio, a raw/digest token, or a
provider key.

The job registry remains process-local, so private deployment must run exactly
one replica and one uvicorn worker. SQLite makes quota admission durable and
atomic, but it does not make synthesis jobs shareable between workers.

The final Chromium 150 fixture remained `preparing` at 37.01 seconds with the
service worker alive, 37 short GET polls completed, and exactly one active job.
STOP issued DELETE (`found=true`), after which the backend had zero jobs and the
extension session no longer held an active job ID. This directly covers the
long-running case that the former single-fetch design could not survive.

## Setup and run

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
ollama pull qwen3:4b-instruct-2507-q4_K_M
set -a; source .env; set +a
uvicorn taigi_news_reader_backend.app:app --host 127.0.0.1 --port 8765
```

The first real request downloads the Hugging Face checkpoint. To exercise the
API without Ollama or a model download, explicitly set
`TAIGI_PROVIDER_MODE=mock`; mock responses identify themselves as such.

## Secure LAN deployment

The target-specific Docker and nginx preparation is in
[`deploy/lan/README.md`](../deploy/lan/README.md). It publishes no backend host
port: the non-root, read-only backend joins a dedicated external edge network
shared only with nginx, and nginx reaches it by a private network alias. The
HTTPS edge pins the exact Chrome extension identity header and cross-checks
Origin when Chrome sends one, restricts the source LAN, rate-limits job creation
and polling separately, and does not expose the retained direct
`POST /v1/synthesize` route.

Set `TAIGI_REQUIRE_ALLOWED_ORIGIN=true`, pin at least one exact
`TAIGI_EXTENSION_IDS` value, and disable localhost origins for that deployment.
Strict origin mode requires every actual `/v1/` request to send the pinned ID in
`X-Taigi-Extension-Id`. A supplied Origin must also be allowed and must match
that ID; CORS preflight is validated by its Origin because browsers do not send
the requested custom headers until preflight succeeds. CORS explicitly permits
`Authorization`. Extension identity remains defense in depth because a
non-browser client can forge both identity headers; the Bearer invite token is
the private-tester authentication credential.

## Test

Tests use injected deterministic providers and never download the MMS model:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

Run the suite for the current result rather than relying on a stale count in
documentation.
