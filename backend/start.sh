#!/bin/bash

# Start Celery worker in background
echo "Starting Celery worker..."
celery -A app.tasks.celery_tasks worker --loglevel=info --concurrency=2 &

# Wait a moment for Celery to initialize
sleep 3

# Start the main application (uvicorn)
echo "Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

