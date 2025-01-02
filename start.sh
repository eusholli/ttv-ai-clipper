#!/bin/bash -x

# Start FastAPI
echo "Starting FastAPI..."
. /app/venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4 --log-level info \
    --log-config /app/logging.conf &

# Start Nginx
echo "Starting Nginx..."
nginx -g "daemon off;" 2>/var/log/nginx/error.log
