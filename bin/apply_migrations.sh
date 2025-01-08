#!/bin/bash

# Exit on error
set -e

# Load environment variables
source .env

# Function to run a migration file
run_migration() {
    local file=$1
    echo "Applying migration: $file"
    PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f $file
}

# Create migrations directory if it doesn't exist
mkdir -p backend/migrations

# Get list of migration files
migration_files=(backend/migrations/*.sql)

# Sort files to ensure consistent order
IFS=$'\n' sorted_files=($(sort <<<"${migration_files[*]}"))
unset IFS

# Create migrations tracking table if it doesn't exist
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME <<EOF
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
EOF

# Apply each migration if not already applied
for file in "${sorted_files[@]}"; do
    filename=$(basename "$file")
    
    # Check if migration was already applied
    already_applied=$(PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -tAc \
        "SELECT COUNT(*) FROM schema_migrations WHERE filename = '$filename';")
    
    if [ "$already_applied" -eq "0" ]; then
        # Run the migration
        run_migration "$file"
        
        # Record the migration
        PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c \
            "INSERT INTO schema_migrations (filename) VALUES ('$filename');"
        
        echo "Migration $filename applied successfully"
    else
        echo "Skipping $filename - already applied"
    fi
done

echo "All migrations completed successfully"
