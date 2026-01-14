# Docker Deployment Examples

This directory contains Docker Compose configurations for different deployment scenarios.

## 📁 Files

| File | Use Case | Description |
|------|----------|-------------|
| `standalone.yml` | Development | Browser pool only, exposes ports to host |
| `with_client.yml` | Small production | Browser pool + single client service |
| `production.yml` | Production | Browser pool + scraper worker |

## 🚀 Quick Start

### Standalone (Development)

```bash
# Start the pool
docker compose -f standalone.yml up -d

# Check logs
docker compose -f standalone.yml logs -f

# Check health
curl http://localhost:8000/pool/status

# Stop
docker compose -f standalone.yml down
```

### With Client Service

```bash
# Start pool + your scraper service
docker compose -f with_client.yml up -d

# Your service accesses pool via:
# http://browser-pool:8000
```

### Production (Scraper Worker)

```bash
# Start pool + scraper worker
docker compose -f production.yml up -d

# Scale to multiple workers if needed
docker compose -f production.yml up -d --scale scraper-worker=3
```

## 🔧 Configuration

### Environment Variables

Key variables to configure in production:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONTEXTS` | 10 | Max concurrent contexts |
| `DEFAULT_DOMAIN_DELAY_MS` | 1000 | Per-domain rate limit |
| `MAX_QUEUE_WAIT_SECONDS` | 300 | Max wait for available context |
| `CDP_PUBLIC_HOST` | localhost | Host in CDP URLs |
| `CDP_PUBLIC_PORT` | 9223 | Port in CDP URLs |
| `LOG_LEVEL` | INFO | Logging verbosity |

### Resource Limits

Add to your service:

```yaml
services:
  browser-pool:
    # ...
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

## 💾 Persistent Storage

Context data (cookies, localStorage) is persisted in Docker volume:

```yaml
volumes:
  - browser-pool-data:/app/data/contexts
```

To backup:

```bash
docker run --rm \
  -v browser-pool-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/contexts-backup.tar.gz /data
```

To restore:

```bash
docker run --rm \
  -v browser-pool-data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/contexts-backup.tar.gz -C /
```

## 🌐 Networking

### Standalone

Ports exposed to host:
- `8000` - API
- `9223` - CDP (optional, for advanced use)

### With Client / Production

Internal network only (not exposed to host):
- Client services access via: `http://browser-pool:8000`

To expose API externally:

```yaml
ports:
  - "8000:8000"
```

## 🔍 Monitoring

### Health Checks

```bash
# Check container health
docker ps

# Check pool status
curl http://localhost:8000/pool/status

# Response:
# {
#   "size": 10,
#   "available": 8,
#   "busy": 2,
#   "contexts": [...]
# }
```

### Logs

```bash
# Follow logs
docker compose -f production.yml logs -f browser-pool

# Last 100 lines
docker compose -f production.yml logs --tail=100 browser-pool
```

## 🐛 Troubleshooting

### Container exits immediately

Check if virtual display is enabled:
```yaml
environment:
  - USE_VIRTUAL_DISPLAY=true  # Required!
```

### Can't access from host

Ensure ports are exposed:
```yaml
ports:
  - "8000:8000"
```

### Contexts lost on restart

Ensure volume is mounted:
```yaml
volumes:
  - browser-pool-data:/app/data/contexts
```

### Out of memory

Reduce `MAX_CONTEXTS` or add memory limits:
```yaml
environment:
  - MAX_CONTEXTS=5  # Reduce
deploy:
  resources:
    limits:
      memory: 2G
```

## 🔐 Security

### Don't expose CDP port publicly

CDP gives full control over browser - only expose internally:

```yaml
# ❌ Bad - exposes to world
ports:
  - "9223:9223"

# ✅ Good - internal only
# No ports section, or expose selectively
ports:
  - "127.0.0.1:9223:9223"
```

### Use secrets for credentials

```yaml
services:
  browser-pool:
    environment:
      - PROXY_URL_FILE=/run/secrets/proxy_url
    secrets:
      - proxy_url

secrets:
  proxy_url:
    file: ./secrets/proxy_url.txt
```

## 📦 Building Custom Image

```bash
# Build from source
docker build -t my-browser-pool:latest .

# Use in compose
image: my-browser-pool:latest
```

## 🚀 Production Checklist

- [ ] Set appropriate `MAX_CONTEXTS` for your RAM
- [ ] Configure persistent volumes
- [ ] Set up health checks
- [ ] Configure log aggregation
- [ ] Set resource limits
- [ ] Use secrets for credentials
- [ ] Configure restart policy
- [ ] Set up monitoring/alerting
- [ ] Test backup/restore procedure
- [ ] Document your deployment
