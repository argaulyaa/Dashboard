# Backend — O-RAN Control Dashboard API
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System deps (minimal; paramiko is pure-python, no extra system libs needed)
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
