FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY services/crawler/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers (Chromium only to save space)
RUN playwright install --with-deps chromium

COPY services/crawler/ .
COPY services/common/ ./services/common/

EXPOSE 8003

# Run the API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
