# Browser Scraper Pool - Examples

This directory contains practical examples for using browser-scraper-pool in various scenarios.

## 📁 Structure

```
examples/
├── basics/           # Simple getting-started examples
├── proxy/            # Proxy configuration and rotation
├── docker/           # Docker deployment examples
└── integration/      # Integration with other tools (Celery, FastAPI, etc.)
```

## 🚀 Quick Start

### Basics
- **[simple_scrape.py](basics/simple_scrape.py)** - Scrape a single URL with minimal setup
- **[python_client.py](basics/python_client.py)** - Complete Python client with context manager
- **[multiple_requests.py](basics/multiple_requests.py)** - Sequential scraping with context reuse

### Proxy Management
- **[single_proxy.py](proxy/single_proxy.py)** - Use a single proxy for all requests
- **[proxy_rotation.py](proxy/proxy_rotation.py)** - Tag-based proxy rotation strategy
- **[proxy_auth_cdp.py](proxy/proxy_auth_cdp.py)** - Handle 407 proxy authentication via CDP

### Docker Deployment
- **[standalone.yml](docker/standalone.yml)** - Browser pool only
- **[with_client.yml](docker/with_client.yml)** - Browser pool + client service
- **[production.yml](docker/production.yml)** - Full production setup with multiple workers

### Integration
- **[celery_worker.py](integration/celery_worker.py)** - Background scraping with Celery
- **[fastapi_integration.py](integration/fastapi_integration.py)** - Use as part of larger FastAPI app
- **[monitoring.py](integration/monitoring.py)** - Health checks and metrics

## 📖 Usage

All examples assume the browser pool is running at `http://localhost:8000`.

### Starting the pool

**Option 1: Local development**
```bash
uvicorn browser_scraper_pool.main:app --reload
```

**Option 2: Docker**
```bash
docker run -d -p 8000:8000 -p 9223:9223 \
  kvyatkovskyaleksey/browser-scraper-pool:latest
```

### Running examples

```bash
# Basic examples
cd examples/basics
python simple_scrape.py

# Proxy examples
cd examples/proxy
python proxy_rotation.py

# Docker examples
docker compose -f examples/docker/standalone.yml up
```

## 💡 Tips

1. **Start simple** - Begin with `simple_scrape.py` to understand the basics
2. **Use tags** - Tag-based context selection is powerful for organizing scraping jobs
3. **Handle errors** - Always check the `success` field in responses
4. **Monitor pool** - Use `GET /pool/status` to see pool health
5. **Respect rate limits** - Use `domain_delay` to avoid blocks

## 🤝 Contributing

Have a useful example? Please contribute!

1. Add your example to the appropriate directory
2. Include clear comments explaining what it does
3. Add a brief description to this README
4. Ensure it runs without errors

## 📚 Further Reading

- [Main README](../README.md)
- [API Documentation](http://localhost:8000/docs) (when pool is running)
- [Contributing Guide](../CONTRIBUTING.md)
- [Docker Guide](../docs/docker.md)
