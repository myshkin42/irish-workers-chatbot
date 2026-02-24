# ---------- Stage 1: Build ----------
# Use slim Python image to keep the container small
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies needed by some Python packages (PyMuPDF etc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Stage 2: Runtime ----------
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/

# Fly.io sets PORT env var; default to 8080
ENV PORT=8080

# Run uvicorn bound to 0.0.0.0 so Fly.io can route to it
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
