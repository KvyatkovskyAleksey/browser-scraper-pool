#!/bin/bash
set -e

# Start socat to forward external CDP connections to Chrome's localhost
# Chrome listens on 127.0.0.1:9222, we expose it on 0.0.0.0:9223
socat TCP-LISTEN:9223,fork,reuseaddr TCP:127.0.0.1:9222 &

# Start the FastAPI server
exec uv run uvicorn browser_scraper_pool.main:app --host 0.0.0.0 --port 8000
