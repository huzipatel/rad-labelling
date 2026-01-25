#!/bin/bash

echo "=== Starting Application ==="
echo "Redis URL: ${REDIS_URL:-redis://localhost:6379/0}"

# Run database migrations
echo "Running database migrations..."
alembic upgrade head || echo "Migration warning (may already be applied)"

# Start Celery worker in background
# High concurrency for maximum download throughput with multiple API keys
echo "Starting Celery worker with concurrency=16..."
celery -A app.tasks.celery_tasks worker --loglevel=info --concurrency=16 &
CELERY_PID=$!
echo "Celery worker started with PID: $CELERY_PID"

# Wait a moment for Celery to initialize
sleep 3

# Start the main application (uvicorn)
echo "Starting FastAPI server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
