#!/bin/bash

# Change to the project root directory
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Set environment variables
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Start Celery worker with configuration
celery -A backend.tasks worker \
    --loglevel=INFO \
    --concurrency=2 \
    --pool=prefork \
    --logfile=/var/log/celery/celery.log \
    --uid=nobody
