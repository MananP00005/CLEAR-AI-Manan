FROM python:3.11-slim

WORKDIR /app

# requirements.txt lives at the repo root, so the build context for this
# Dockerfile must be the repo root (see docker-compose.yml).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/

WORKDIR /app/server

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
