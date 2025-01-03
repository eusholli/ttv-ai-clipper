#!/bin/bash -x

python backend/test_postgresql.py 

# Start FastAPI
echo "Starting FastAPI..."
. /app/venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4 --log-level debug \
    --log-config /app/logging.conf &

# Start Nginx only after FastAPI is confirmed running
echo "Starting Nginx..."
nginx -g "daemon off;" 
