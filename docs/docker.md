# Docker Documentation

Browser Scraper Pool is available as a Docker image for easy deployment.

## Pulling the Image

```bash
# Latest version
docker pull YOUR_USERNAME/browser-scraper-pool:latest

# Specific version
docker pull YOUR_USERNAME/browser-scraper-pool:0.1.0
```

## Running the Container

### Basic Run

```bash
docker run -d \
  -p 8000:8000 \
  -p 9223:9223 \
  -v browser-pool-data:/app/data/contexts \
  --name browser-pool \
  YOUR_USERNAME/browser-scraper-pool:latest
```

### With All Environment Variables

```bash
docker run -d \
  -p 8000:8000 \
  -p 9223:9223 \
  -e BROWSER_HEADLESS=false \
  -e USE_VIRTUAL_DISPLAY=true \
  -e MAX_CONTEXTS=10 \
  -e CDP_PUBLIC_HOST=localhost \
  -e CDP_PUBLIC_PORT=9223 \
  -v browser-pool-data:/app/data/contexts \
  --name browser-pool \
  YOUR_USERNAME/browser-scraper-pool:latest
```

## Docker Compose

```yaml
services:
  browser-pool:
    image: YOUR_USERNAME/browser-scraper-pool:latest
    ports:
      - "8000:8000"  # API
      - "9223:9223"  # CDP
    volumes:
      - browser-pool-data:/app/data/contexts
    environment:
      - BROWSER_HEADLESS=false
      - USE_VIRTUAL_DISPLAY=true
      - MAX_CONTEXTS=10
      - CDP_PUBLIC_HOST=localhost
      - CDP_PUBLIC_PORT=9223

volumes:
  browser-pool-data:
```

## Ports

| Port | Description |
|------|-------------|
| `8000` | FastAPI HTTP server |
| `9223` | Chrome DevTools Protocol (CDP) WebSocket |

## CDP (Chrome DevTools Protocol) Access

Chrome inside the container binds to `127.0.0.1:9222` only (Patchright limitation).
A socat process forwards external connections from port 9223 to Chrome's internal port.

**For external CDP access:**
1. Map port 9223: `-p 9223:9223`
2. Set `CDP_PUBLIC_HOST` to the host your clients will connect to (e.g., `localhost` or your server IP)
3. Set `CDP_PUBLIC_PORT=9223`

The API endpoints like `/pool/cdp` will return URLs using these configured values.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BROWSER_HEADLESS` | `false` | Run browser in headless mode |
| `USE_VIRTUAL_DISPLAY` | `true` | Use Xvfb virtual display |
| `VIRTUAL_DISPLAY_SIZE` | `1920,1080` | Virtual display resolution |
| `CDP_PORT` | `9222` | Chrome's internal CDP port |
| `CDP_PUBLIC_HOST` | `127.0.0.1` | Host in CDP URLs returned by API |
| `CDP_PUBLIC_PORT` | `9222` | Port in CDP URLs (set to `9223` in Docker) |
| `PERSISTENT_CONTEXTS_PATH` | `./data/contexts` | Path for persistent context storage |
| `MAX_CONTEXTS` | `10` | Maximum browser contexts in pool |
| `DEFAULT_DOMAIN_DELAY_MS` | `1000` | Delay between same-domain requests (ms) |
| `MAX_QUEUE_WAIT_SECONDS` | `300` | Max wait time for context availability |
| `MAX_CONSECUTIVE_ERRORS` | `5` | Errors before context recreation |
| `LOG_LEVEL` | `INFO` | Logging level |

## Volumes

| Path | Description |
|------|-------------|
| `/app/data/contexts` | Persistent browser context storage (cookies, localStorage, etc.) |

Mount a volume to preserve browser contexts across container restarts.
