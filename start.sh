#!/bin/sh

# Activate virtual environment
. /app/venv/bin/activate

# Start FastAPI with debug logging - changed host to 0.0.0.0 to allow container internal access
uvicorn main:app --host 0.0.0.0 --port 8000 --log-level debug > /var/log/fastapi/access.log 2> /var/log/fastapi/error.log &

# Start Nginx with error logging
nginx -g "daemon off;" 2>/var/log/nginx/error.log
