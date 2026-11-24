# Backend — O-RAN Control Dashboard API
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# ADB is used by the authenticated remote-device endpoints.
RUN apt-get update \
    && apt-get install -y --no-install-recommends adb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code. NOTE: backend/.env is git-ignored and intentionally NOT copied;
# config comes from K8s via Secret/ConfigMap (load_dotenv() in main.py does
# not override already-set OS env vars).
COPY . .

# Data directory (persistent via volume if enabled)
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
