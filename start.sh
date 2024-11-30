#!/bin/bash
# start.sh

# Activate virtual environment
source /app/venv/bin/activate

# Start FastAPI in the background
uvicorn main:app --host 0.0.0.0 --port 8000 &

# Start Nginx in the foreground
nginx -g "daemon off;"