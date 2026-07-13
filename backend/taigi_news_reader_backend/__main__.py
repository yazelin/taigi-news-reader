"""Run the local service on its deliberately loopback-only default address."""

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "taigi_news_reader_backend.app:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )
