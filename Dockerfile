# ---- Build stage ----
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Install into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# ---- Production stage ----
FROM python:3.11-slim AS production

# Security: minimal runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Non-root user
RUN useradd --create-home --uid 1000 tws && \
    mkdir -p /app/data && \
    chown -R tws:tws /app
WORKDIR /app
USER tws

# Labels for traceability
LABEL org.opencontainers.image.title="Text Watermark Studio" \
      org.opencontainers.image.description="Independent, offline verification of AI text watermarks" \
      org.opencontainers.image.license="MIT" \
      org.opencontainers.image.source="https://github.com/erikgieske/text-watermark-studio"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

CMD ["uvicorn", "ai_watermark_toolkit.api.fastapi_app:app", "--host", "0.0.0.0", "--port", "8080"]
