# Taigi News Reader backend

This FastAPI service translates Traditional Chinese news and returns Taiwanese
Hokkien WAV audio. The self-hosted reference path uses Ollama plus Meta's
`facebook/mms-tts-nan` VITS checkpoint; hosted deployments can instead select
the OpenAI-compatible translator and remote TTS adapters. Local models load only
on the first synthesis request. Provider failures return an error; the service
never falls back to a Mandarin browser voice.

The bundled Qwen translator is an experimental local reference. Translation
output is checked against the MMS checkpoint's exact POJ character vocabulary
before TTS; Ollama and OpenAI-compatible adapters get one strict repair attempt,
then the request fails loudly instead of speaking Chinese, digits, or unsupported
pseudo-romanization. Native-speaker review is still required before treating its
translations as publication-ready.

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

## Test

Tests use injected deterministic providers and never download the MMS model:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```
