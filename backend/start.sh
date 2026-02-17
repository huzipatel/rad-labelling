#!/bin/bash

set -e  # Exit on error

echo "=== Starting Application ==="
echo "Redis URL: ${REDIS_URL:-redis://localhost:6379/0}"

# Run database migrations
echo "Running database migrations..."
echo "Checking current migration state..."
alembic current || echo "No migrations applied yet"

echo "Applying migrations..."
if alembic upgrade head; then
    echo "✓ Migrations completed successfully"
else
    echo "✗ Migration failed! Check the error above."
    echo "Attempting to show migration history..."
    alembic history --verbose || true
    # Continue anyway - the app might work if tables already exist
    echo "Continuing startup despite migration error..."
fi

echo "Migration state after upgrade:"
alembic current || echo "Could not determine migration state"

# Start Celery worker in background with beat scheduler
# High concurrency for maximum download throughput with multiple API keys
# --beat enables scheduled tasks (hourly reconciliation)
echo "Starting Celery worker with concurrency=16 and beat scheduler..."
celery -A app.tasks.celery_tasks worker --beat --loglevel=info --concurrency=16 &
CELERY_PID=$!
echo "Celery worker started with PID: $CELERY_PID"

# Wait a moment for Celery to initialize
sleep 3

# Start the main application (uvicorn)
echo "Starting FastAPI server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
