FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY taigi_news_reader_backend ./taigi_news_reader_backend

# Hosted deployments using remote TTS avoid the multi-gigabyte Torch layer.
# Build with --build-arg INSTALL_LOCAL_MMS=1 for the local MMS provider.
ARG INSTALL_LOCAL_MMS=0
RUN if [ "$INSTALL_LOCAL_MMS" = "1" ]; then \
      python -m pip install --no-cache-dir '.[tts]'; \
    else \
      python -m pip install --no-cache-dir .; \
    fi

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=2)"]

CMD ["uvicorn", "taigi_news_reader_backend.app:app", "--host", "0.0.0.0", "--port", "8765"]
