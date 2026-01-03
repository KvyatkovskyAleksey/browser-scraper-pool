# Browser Scraper Pool

Web scraping context pool service with smart context management using Patchright + FastAPI.

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

## Quick Start

```bash
# Start the server
uvicorn browser_scraper_pool.main:app --reload
```

## Usage

### Create a Context

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
| `CDP_PORT` | `9222` | Chrome DevTools Protocol port |
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
