# =========================================================
# Projekt:Alpha execution backend image
# Build:  docker build -t alpha-backend .
# Run:    docker run --env-file .env -p 8000:8000 -v alpha-data:/data alpha-backend
# =========================================================
FROM python:3.11-slim

WORKDIR /srv/alpha

# backend dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# application
COPY app ./app
COPY bin ./bin
COPY data /data

ENV ALPHA_DATA_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)\" || exit 1"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
