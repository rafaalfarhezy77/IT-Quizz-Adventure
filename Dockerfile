# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Hindari pembuatan file .pyc dan pastikan log langsung tampil di stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    PORT=5000

# Install utilitas curl untuk healthcheck container
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Salin dependencies terlebih dahulu untuk memanfaatkan Docker Layer Caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Salin seluruh kode program aplikasi
COPY . .

# Pastikan folder instance dan uploads tersedia serta entrypoint executable
RUN mkdir -p /app/instance/uploads/hardware && \
    chmod +x /app/entrypoint.sh

# Port aplikasi
EXPOSE 5000

# Healthcheck otomatis setiap 30 detik
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
