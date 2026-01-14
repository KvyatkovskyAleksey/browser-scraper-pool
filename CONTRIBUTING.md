# Contributing to Browser Scraper Pool

Thank you for your interest in contributing! This document will help you get started.

## 🚀 Quick Start for Contributors

### Prerequisites
- Python 3.13+
- Chrome/Chromium browser
- Docker (for testing)

### Setup Development Environment

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/browser-scraper-pool.git
   cd browser-scraper-pool
   ```

2. **Install dependencies with uv**
   ```bash
   uv sync --extra dev
   ```

3. **Activate the virtual environment**
   ```bash
   source .venv/bin/activate  # Linux/Mac
   # or
   .venv\Scripts\activate  # Windows
   ```

4. **Run tests to verify setup**
   ```bash
   pytest
   ```

## 🏗️ Architecture Overview

Browser Scraper Pool uses a modular architecture:

```
browser_scraper_pool/
├── main.py              # FastAPI app entry point
├── config.py            # Configuration via pydantic-settings
├── pool/                # Core pool logic
│   ├── context_pool.py      # Singleton browser + context management
│   ├── rate_limiter.py      # Per-domain rate limiting
│   ├── eviction.py          # Context eviction scoring
│   └── request_queue.py     # Internal request queue
├── api/                 # FastAPI endpoints
│   ├── scrape.py            # POST /scrape (main endpoint)
│   ├── contexts.py          # /contexts CRUD
│   └── pool.py              # /pool status and CDP info
└── models/              # Pydantic schemas
    └── schemas.py
```

### Key Design Decisions

**Why single browser with multiple contexts?**
- More efficient than multiple browser instances
- Shared memory and browser cache
- Easier to manage and monitor

**Why FastAPI?**
- Native async/await support
- Automatic API documentation
- Pydantic validation
- Great performance

**Why Patchright instead of Playwright?**
- Patchright is a fork of Playwright with modifications to bypass bot detection systems
- Patches the browser to pass anti-bot checks on targeted websites
- Maintains API compatibility with Playwright while adding stealth capabilities
- More information: https://pypi.org/project/patchright/

## 🧪 Running Tests

### Run all tests
```bash
pytest
```

### Run specific test file
```bash
pytest tests/test_context_pool.py
```

### Run with coverage
```bash
pytest --cov=browser_scraper_pool --cov-report=html
open htmlcov/index.html
```

### Run integration tests (requires Chrome)
```bash
pytest tests/test_context_pool_integration.py
```

### Test Structure
- **Unit tests**: No Chrome required, use mocks
- **Integration tests**: Real Chrome instance, slower but comprehensive
- **API tests**: Test HTTP endpoints
- **Component tests**: Test individual modules in isolation

## 📝 Coding Standards

### Code Style
- Follow PEP 8
- Use `ruff` for linting (pre-configured)
- Max line length: 100
- Use type hints for all public functions
- Docstrings for all modules, classes, and public functions

### Example Function
```python
async def create_context(
    proxy: str | None = None,
    tags: list[str] | None = None
) -> Context:
    """
    Create a new browser context.

    Args:
        proxy: Optional proxy URL (e.g., "http://proxy:8080")
        tags: Optional tags for context selection

    Returns:
        Context: The created context object

    Raises:
        PoolFullError: If pool is at max capacity
    """
    ...
```

### Adding New Features
1. Write tests first (TDD approach)
2. Implement feature
3. Add type hints and docstrings
4. Update CHANGELOG.md
5. Add example to examples/ if relevant

## 🐛 Bug Reports

When reporting bugs, include:
- Python version
- Browser version
- Minimal reproducible example
- Logs with `LOG_LEVEL=DEBUG`

## ✅ Pull Request Process

1. **Update CHANGELOG.md** with your changes
2. **Add tests** for new functionality
3. **Run tests** and ensure all pass
4. **Update documentation** if needed
5. **Squash commits** into logical units
6. **Push to fork** and open PR

### PR Title Format
- `feat: Add support for custom user agents`
- `fix: Handle proxy timeout errors gracefully`
- `docs: Update Docker deployment guide`
- `test: Add integration tests for CDP`

### PR Checklist
- [ ] Tests pass locally
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Commit messages follow conventional commits

## 🎯 Good First Issues

Look for issues tagged `good first issue` for contributor-friendly tasks.

Examples:
- Add new example to examples/
- Improve error messages
- Add more test coverage
- Update documentation

## 💬 Communication

- **Discussions**: Use GitHub Discussions for questions
- **Issues**: Use GitHub Issues for bugs and feature requests

## 🙏 Thank You

Your contributions help make browser-scraper-pool better for everyone!
