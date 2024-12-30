#!/bin/bash -x

# Function to check if PostgreSQL is ready
wait_for_postgres() {
    echo "Waiting for PostgreSQL to start..."
    while ! pg_isready -h localhost -U postgres > /dev/null 2>&1; do
        sleep 1
    done
    echo "PostgreSQL is ready!"
}

# Function to initialize database if needed
init_database() {
    echo "Checking if database initialization is needed..."
    if ! su postgres -c "psql -lqt | cut -d \| -f 1 | grep -qw transcript_search"; then
        echo "Initializing database..."
        su postgres -c "createdb transcript_search"
        su postgres -c "psql -c \"CREATE USER transcript_user WITH PASSWORD 'transcript_pwd';\""
        su postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE transcript_search TO transcript_user;\""
        su postgres -c "psql -d transcript_search -c \"GRANT ALL ON SCHEMA public TO transcript_user;\""
        su postgres -c "psql -d transcript_search -c 'CREATE EXTENSION IF NOT EXISTS vector;'"
        echo "Database initialization completed!"
    else
        echo "Database already exists, skipping initialization"
    fi
}

# Start PostgreSQL
echo "Starting PostgreSQL..."
pg_ctlcluster 16 main start

# Wait for PostgreSQL and initialize database
wait_for_postgres
init_database

# Start FastAPI
echo "Starting FastAPI..."
. /app/venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 --log-level info \
    --log-config /app/logging.conf &

# Wait for FastAPI to start
echo "Waiting for FastAPI to start..."
while ! curl -s http://localhost:8000/api/version > /dev/null; do
    sleep 1
done
echo "FastAPI is ready!"

# Start Nginx
echo "Starting Nginx..."
nginx -g "daemon off;" 2>/var/log/nginx/error.log &

