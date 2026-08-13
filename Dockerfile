FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

# P0-1/P2-5: non-root + Healthcheck. Der 0.0.0.0-Bind ist durch die
# fail-closed-Auth geschützt (ohne AI_WM_API_KEY lehnt die API jeden Request
# mit 401 ab); für lokale Nutzung bindet docker-compose auf 127.0.0.1.
RUN useradd --create-home --uid 1000 tws && mkdir -p /app/data && chown -R tws:tws /app
USER tws

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1
CMD ["uvicorn", "ai_watermark_toolkit.api.fastapi_app:app", "--host", "0.0.0.0", "--port", "8080"]
