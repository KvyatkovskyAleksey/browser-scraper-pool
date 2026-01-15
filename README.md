# Browser Scraper Pool

[![PyPI version](https://badge.fury.io/py/browser-scraper-pool.svg)](https://badge.fury.io/py/browser-scraper-pool)
[![Python Version](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/KvyatkovskyAleksey/browser-scraper-pool/actions/workflows/test.yml/badge.svg)](https://github.com/KvyatkovskyAleksey/browser-scraper-pool/actions/workflows/test.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/kvyatkovskyaleksey/browser-scraper-pool)](https://hub.docker.com/r/kvyatkovskyaleksey/browser-scraper-pool)
[![GitHub Stars](https://img.shields.io/github/stars/KvyatkovskyAleksey/browser-scraper-pool?style=social)](https://github.com/KvyatkovskyAleksey/browser-scraper-pool)

🚀 **Production-ready web scraping service with smart context management, proxy rotation, and self-healing capabilities**

**Tired of managing browser instances, proxy rotation, and rate limiting yourself?**
Browser Scraper Pool handles all the complexity so you can focus on extracting data.

✨ **Zero-config scraping** - Single endpoint, automatic context management
🔄 **Smart proxy rotation** - Per-context proxy assignment with health tracking
⚡ **Self-healing** - Auto-recreation on errors, browser crash recovery
🐳 **Docker-ready** - One container, no browser setup headaches

## Features

- **Reusable browser contexts** with proxy support and custom tags
- **Smart context selection** based on tags and availability
- **Per-context domain rate limiting** to avoid being blocked
- **Automatic context health tracking** and recreation on errors
- **CDP access** for custom network interception

## Installation

```bash
# Requires Python 3.13+

# Clone the repository
git clone <repo-url>
cd browser-scraper-pool

# Install dependencies
uv sync

# Install Patchright browsers
patchright install chromium
```

## 🎯 Quick Start

Choose your use case:

### I want to scrape a single URL (Simple)

```bash
# One-line curl example
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "get_content": true}'
```

### I want to scrape with Python client (Common)

```python
import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/scrape",
            json={
                "url": "https://example.com",
                "get_content": True,
                "wait_for": "networkidle"
            }
        )
        result = response.json()
        print(f"Status: {result['status']}")
        print(f"Content: {result['content'][:100]}...")

asyncio.run(main())
```

### I want to run in Docker (Production)

```bash
docker run -d \
  -p 8000:8000 \
  -p 9223:9223 \
  -e BROWSER_HEADLESS=true \
  -e USE_VIRTUAL_DISPLAY=true \
  kvyatkovskyaleksey/browser-scraper-pool:latest
```

See [Docker Documentation](docs/docker.md) for full deployment guide.

## 🏗️ Architecture

```mermaid
graph TD
    A[Client Request] --> B[POST /scrape]
    B --> C{Context Available?}
    C -->|Yes| D[Select Context by Tags]
    C -->|No| E[Request Queue]
    E -->|Wait max 5 min| F[Timeout 503]
    E -->|Context available| D
    D --> G{Rate Limited?}
    G -->|Yes| H[Wait or Pick Another]
    G -->|No| I[Execute Request]
    H --> I
    I --> J[Return Result]
    I --> K{Error?}
    K -->|Consecutive errors > 5| L[Recreate Context]
    K -->|TargetClosedError| M[Restart Browser]

    style A fill:#e1f5fe
    style B fill:#fff3e0
    style D fill:#e8f5e9
    style I fill:#f3e5f5
    style J fill:#e1f5fe
```

**Key Design**: One browser instance + multiple isolated contexts
- **3x less memory** than multiple browser instances
- **Shared browser cache** for faster loading
- **Isolated contexts** with separate cookies, proxies, and storage

## ✨ Why Browser Scraper Pool?

### 🎯 Smart Context Management
- **Tag-based selection** - Route requests to contexts with specific tags (e.g., "premium", "residential-proxy")
- **Automatic eviction** - Intelligently removes idle contexts when pool is full
- **Protected contexts** - Tag important contexts as "protected" to prevent eviction

### 🛡️ Production-Ready Features
- **Per-domain rate limiting** - Avoid blocks with intelligent delays (configurable per domain)
- **Auto-recovery** - Context recreation after 5 consecutive errors
- **Browser crash recovery** - Automatic restart on TargetClosedError
- **Request queue** - Wait up to 5 minutes for available context

### 🔧 Advanced Capabilities
- **CDP access** - Chrome DevTools Protocol for custom network interception
- **Proxy authentication** - Handle 407 errors via CDP
- **Persistent contexts** - Save/load cookies and localStorage
- **Resource blocking** - Faster scraping by blocking images/fonts/stylesheets

### 🐳 Docker-Native
- Single container with socat for CDP forwarding
- Persistent volume for context storage
- Environment-based configuration
- Health checks and auto-restart policies

## 📊 How It Compares

| Feature | browser-scraper-pool | puppeteer-cluster | scrapyd |
|---------|---------------------|-------------------|---------|
| Context-per-browser | ✅ Efficient | ❌ One browser per worker | ❌ Not browser-based |
| Per-domain rate limiting | ✅ Built-in | ❌ Manual | ❌ Manual |
| Auto-recovery on errors | ✅ Yes | ❌ Manual | ❌ Manual |
| Proxy authentication | ✅ Via CDP | ❌ Complex | ❌ Manual |
| Docker support | ✅ First-class | ⚠️ Requires setup | ⚠️ Requires setup |
| Python async | ✅ FastAPI | ❌ Node.js only | ⚠️ Sync-only |

## Usage

```bash
curl -X POST http://localhost:8000/contexts \
  -H "Content-Type: application/json" \
  -d '{"proxy": "http://user:pass@proxy:8080", "tags": ["premium"]}'
```

### Scrape a URL

```bash
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "tags": ["premium"],
    "get_content": true
  }'
```

Response:
```json
{
  "success": true,
  "url": "https://example.com",
  "status": 200,
  "content": "<html>...",
  "context_id": "ctx-123"
}
```

### Execute JavaScript

```bash
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "script": "document.title"
  }'
```

### Take a Screenshot

```bash
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "screenshot": true,
    "get_content": false
  }'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/scrape` | POST | Main endpoint - scrape URL with smart context selection |
| `/contexts` | POST | Create a new context |
| `/contexts` | GET | List all contexts |
| `/contexts/{id}` | GET | Get context details |
| `/contexts/{id}` | DELETE | Remove a context |
| `/contexts/{id}/tags` | PATCH | Update context tags |
| `/pool/status` | GET | Get pool status |
| `/pool/cdp` | GET | Get CDP endpoint URL |

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BROWSER_HEADLESS` | `false` | Run browser in headless mode |
| `USE_VIRTUAL_DISPLAY` | `true` | Use virtual display (X server) |
| `VIRTUAL_DISPLAY_SIZE` | `1920,1080` | Virtual display resolution |
| `CDP_PORT` | `9222` | Chrome DevTools Protocol port (internal) |
| `CDP_PUBLIC_HOST` | `127.0.0.1` | Host in CDP URLs (for Docker: `localhost`) |
| `CDP_PUBLIC_PORT` | `9222` | Port in CDP URLs (for Docker: `9223`) |
| `PERSISTENT_CONTEXTS_PATH` | `./data/contexts` | Path for persistent context storage |
| `MAX_CONTEXTS` | `10` | Maximum contexts in pool |
| `DEFAULT_DOMAIN_DELAY_MS` | `1000` | Delay between requests to same domain |
| `MAX_QUEUE_WAIT_SECONDS` | `300` | Max wait time for context availability |
| `MAX_CONSECUTIVE_ERRORS` | `5` | Errors before context recreation |
| `LOG_LEVEL` | `INFO` | Logging level |

## Running Tests

```bash
pytest
```

## Docker

See [Docker Documentation](docs/docker.md) for full details.

### Quick Start

```bash
# Pull and run
docker run -d -p 8000:8000 -p 9223:9223 YOUR_USERNAME/browser-scraper-pool:latest
```
