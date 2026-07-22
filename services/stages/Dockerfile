FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer-cached)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Run as non-root user
RUN adduser --disabled-password --gecos "" appuser

# Copy service source
COPY --chown=appuser:appuser . .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
