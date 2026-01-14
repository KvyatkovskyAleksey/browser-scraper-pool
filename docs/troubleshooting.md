# Troubleshooting Guide

This guide covers common issues and their solutions when using browser-scraper-pool.

## Quick Diagnostic Commands

```bash
# Check pool status
curl http://localhost:8000/pool/status

# View logs with DEBUG level
LOG_LEVEL=DEBUG uvicorn browser_scraper_pool.main:app

# Docker logs
docker logs browser-pool
docker logs browser-pool --tail=100 -f
```

---

## Common Issues

### Issue: "TargetClosedError" during scraping

**Symptoms:**
- Requests fail with `TargetClosedError`
- Browser crashes intermittently
- All contexts become unavailable

**Cause:**
Browser crashed due to:
- Out of memory
- Segmentation fault
- Chrome bug

**Solution:**
The pool automatically restarts the browser. Check logs to confirm:

```bash
docker logs browser-pool | grep -i restart
```

**Prevention:**
```yaml
# Reduce contexts or add memory
environment:
  - MAX_CONTEXTS=5  # Reduce from 10
deploy:
  resources:
    limits:
      memory: 4G  # Increase memory
```

---

### Issue: Proxy authentication fails (HTTP 407)

**Symptoms:**
- HTTP 407 Proxy Authentication Required errors
- Requests timeout when using proxy

**Cause:**
Proxy requires username/password but browser isn't providing credentials.

**Solutions:**

**Option 1: Include credentials in proxy URL (simple, same machine only)**
```python
proxy = "http://username:password@proxy-server:8080"
```
⚠️ **Limitation**: This only works when browser pool is on the same machine as your client. The browser will prompt for auth credentials interactively.

**Option 2: Use CDP to handle auth (works with remote hosts)**
When browser pool is on a different host (e.g., Docker, remote server), you need to use CDP to intercept and handle proxy authentication challenges programmatically.

See [examples/proxy/proxy_auth_cdp.py](../examples/proxy/proxy_auth_cdp.py) for a complete example of:
- Connecting via CDP
- Setting up Fetch domain to intercept auth requests
- Providing credentials automatically

---

### Issue: Contexts getting evicted too quickly

**Symptoms:**
- Newly created contexts disappear
- `GET /contexts` shows fewer contexts than created
- Frequent context recreation

**Cause:**
Pool is full, eviction algorithm removes idle contexts.

**Solutions:**

**Option 1: Tag important contexts as "protected"**
```python
# Protected contexts are never evicted
await create_context(
    tags=["protected"],
    persistent=True
)
```

**Option 2: Increase pool size**
```yaml
environment:
  - MAX_CONTEXTS=20  # Increase from 10
```

**Option 3: Reduce idle time before eviction**
Edit eviction weights in source code (advanced).

---

### Issue: Rate limiting still blocking requests

**Symptoms:**
- Getting blocked (429/403) despite `DEFAULT_DOMAIN_DELAY_MS` set
- Target website returns errors

**Cause:**
Rate limit delay is **per-context**, not per-pool.
If you have 10 contexts, you're making 10 concurrent requests.

**Solutions:**

**Option 1: Increase delay**
```yaml
environment:
  - DEFAULT_DOMAIN_DELAY_MS=5000  # 5 seconds instead of 1
```

**Option 2: Override per-request**
```python
POST /scrape {
    "url": "https://sensitive-site.com",
    "domain_delay": 10000  # 10 seconds for this request
}
```

**Option 3: Use fewer contexts**
```yaml
environment:
  - MAX_CONTEXTS=3  # Reduce concurrency
```

---

### Issue: Docker container exits immediately

**Symptoms:**
- `docker run` exits with code 1
- Container won't stay running
- No logs in `docker logs`

**Cause:**
Missing X11 display for virtual display (required in headless mode).

**Solution:**
Ensure `USE_VIRTUAL_DISPLAY=true`:

```yaml
environment:
  - BROWSER_HEADLESS=true
  - USE_VIRTUAL_DISPLAY=true  # REQUIRED!
```

---

### Issue: Can't access CDP from outside Docker

**Symptoms:**
- CDP URL works inside container but not from host
- `GET /pool/cdp` returns `ws://browser-pool:9223/...`
- Can't connect from local machine

**Cause:**
CDP port not exposed or wrong host in URL.

**Solution:**

```yaml
services:
  browser-pool:
    environment:
      # Use service name for internal access
      - CDP_PUBLIC_HOST=browser-pool
      - CDP_PUBLIC_PORT=9223
    ports:
      # Expose to host
      - "9223:9223"
```

For external access from host:
```yaml
environment:
  - CDP_PUBLIC_HOST=localhost  # Use localhost for host access
```

---

### Issue: "Pool is full" error (503)

**Symptoms:**
- HTTP 503 responses
- Error: "No contexts available and pool is full"
- Requests timeout

**Cause:**
All contexts are busy and queue timeout exceeded.

**Solutions:**

**Option 1: Increase queue timeout**
```yaml
environment:
  - MAX_QUEUE_WAIT_SECONDS=600  # 10 minutes instead of 5
```

**Option 2: Increase pool size**
```yaml
environment:
  - MAX_CONTEXTS=20
```

**Option 3: Check for stuck contexts**
```bash
curl http://localhost:8000/contexts | jq '.[] | select(.status=="busy")'
```

If contexts are stuck, restart the pool.

---

### Issue: High memory usage

**Symptoms:**
- Container OOM killed
- Memory usage keeps growing
- Slow performance

**Cause:**
- Too many contexts
- Memory leak in Chrome
- Large page loads

**Solutions:**

**Option 1: Reduce contexts**
```yaml
environment:
  - MAX_CONTEXTS=5
```

**Option 2: Enable resource blocking**
```python
# Default behavior, blocks images/fonts/stylesheets
POST /scrape {
    "url": "https://example.com",
    "block_resources": True
}
```

**Option 3: Set memory limits**
```yaml
deploy:
  resources:
    limits:
      memory: 2G
```

**Option 4: Restart periodically**
```yaml
restart: always  # Auto-restart if OOM
```

---

### Issue: Slow page loads

**Symptoms:**
- Requests take 30+ seconds
- Timeout errors
- Poor performance

**Cause:**
- Waiting for all resources
- No resource blocking
- Slow network/proxy

**Solutions:**

**Option 1: Block unnecessary resources**
```python
# Enabled by default, but you can customize
POST /scrape {
    "url": "https://example.com",
    "block_resources": True  # Block images, fonts, stylesheets
}
```

**Option 2: Use different wait strategy**
```python
POST /scrape {
    "url": "https://example.com",
    "wait_for": "domcontentloaded"  # Faster than networkidle
}
```

**Option 3: Set custom timeout**
```python
POST /scrape {
    "url": "https://example.com",
    "timeout": 10000  # 10 seconds
}
```

---

### Issue: Contexts not persisting

**Symptoms:**
- Cookies lost on restart
- Login sessions expired
- `GET /contexts` shows empty after restart

**Cause:**
Persistent storage not configured.

**Solution:**

```yaml
services:
  browser-pool:
    volumes:
      # Persist context data
      - browser-pool-data:/app/data/contexts

    environment:
      - PERSISTENT_CONTEXTS_PATH=/app/data/contexts
```

When creating contexts:
```python
POST /contexts {
    "persistent": True  # Save cookies/storage
}
```

---

## Getting More Help

### Enable Debug Logging

```bash
# Local
export LOG_LEVEL=DEBUG
uvicorn browser_scraper_pool.main:app

# Docker
docker run -e LOG_LEVEL=DEBUG ...
```

### Check GitHub Issues

Search [existing issues](https://github.com/kvyatkovsky/browser-scraper-pool/issues)

### Create New Issue

Include:
1. Python/browser versions
2. Minimal reproducible example
3. Logs with `LOG_LEVEL=DEBUG`
4. Docker/compose config (if applicable)

### Join Community

- GitHub Discussions: Ask questions
- Check [examples](../examples/) for similar use cases

---

## Prevention Checklist

Use this checklist to avoid common issues:

- [ ] `USE_VIRTUAL_DISPLAY=true` when `BROWSER_HEADLESS=true`
- [ ] Persistent volume mounted for context storage
- [ ] Appropriate `MAX_CONTEXTS` for available RAM
- [ ] `DEFAULT_DOMAIN_DELAY_MS` configured for target sites
- [ ] Health checks enabled
- [ ] Resource limits configured
- [ ] Logs aggregation set up
- [ ] Backup strategy for persistent data
- [ ] Monitoring/alerting configured
