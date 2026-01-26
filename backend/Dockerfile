# Backend Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /RAG-Platform

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code to maintain local structure
COPY backend ./backend

# Copy scripts directory to maintain local structure
COPY scripts ./scripts

RUN chmod +x ./scripts/*.sh
# Expose port
EXPOSE 8080


# Run the application
CMD ["sh", "-c", "uvicorn backend.app.main:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8080}"]
