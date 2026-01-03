FROM python:3.13-slim

# Install xvfb for virtual display and socat for CDP port forwarding
RUN apt-get update && apt-get install -y --no-install-recommends xvfb socat \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install dependencies
RUN uv sync --no-dev

# Install Chrome with all dependencies
RUN uv run patchright install --with-deps chrome

# Create data directory for persistent contexts
RUN mkdir -p /app/data/contexts

# Copy entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose ports (8000=API, 9223=CDP via socat)
EXPOSE 8000 9223

# Run the server with socat for CDP forwarding
CMD ["/app/entrypoint.sh"]
