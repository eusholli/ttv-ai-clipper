#!/usr/bin/env bash

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Function to initialize database if needed
init_database() {
    echo "Checking if database initialization is needed..."
    if ! psql -h "$DB_HOST" -U postgres -lqt | cut -d \| -f 1 | grep -qw transcript_search; then
        echo "Initializing database..."
        psql -h "$DB_HOST" -U postgres -c "CREATE DATABASE transcript_search;"
        psql -h "$DB_HOST" -U postgres -c "CREATE USER transcript_user WITH PASSWORD 'transcript_pwd';"
        psql -h "$DB_HOST" -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE transcript_search TO transcript_user;"
        psql -h "$DB_HOST" -U postgres -d transcript_search -c "GRANT ALL ON SCHEMA public TO transcript_user;"
        psql -h "$DB_HOST" -U postgres -d transcript_search -c "CREATE EXTENSION IF NOT EXISTS vector;"
        echo "Database initialization completed!"
    else
        echo "Database already exists, skipping initialization"
    fi
}

# Check if DB_HOST is provided
if [ -z "$DB_HOST" ]; then
    echo "Error: DB_HOST environment variable is not set"
    echo "Usage: DB_HOST=your_host_here ./bin/init_remote_db.sh"
    exit 1
fi

# Initialize database
init_database
