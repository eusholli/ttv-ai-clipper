#!/bin/sh

# Activate virtual environment
. /app/venv/bin/activate

# Start FastAPI with minimal logging (warning level)
uvicorn main:app --host 0.0.0.0 --port 8000 --log-level warning > /var/log/fastapi/access.log 2> /var/log/fastapi/error.log &

# Start Nginx in quiet mode
nginx -g "daemon off;" 2>/var/log/nginx/error.log