#!/usr/bin/env python3
import os
import psycopg2
from init_db import get_db_connection, get_current_schema_version, create_schema_version_table, update_schema_version

def get_migration_files():
    """Get a sorted list of migration files from the migrations directory"""
    migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
    migration_files = []
    
    for filename in os.listdir(migrations_dir):
        if filename.endswith('.sql'):
            version = int(filename.split('_')[0])
            migration_files.append((version, os.path.join(migrations_dir, filename)))
    
    return sorted(migration_files)  # Sort by version number

def read_migration_file(filepath):
    """Read the contents of a migration file"""
    with open(filepath, 'r') as f:
        return f.read()

def verify_required_tables(cursor):
    """Verify that required tables exist, reset version if they don't"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'ingest_jobs'
        );
    """)
    ingest_jobs_exists = cursor.fetchone()[0]
    
    if not ingest_jobs_exists:
        print("Required tables missing - resetting schema version to 0")
        cursor.execute('DELETE FROM schema_version')
        cursor.execute('INSERT INTO schema_version (version) VALUES (0)')
        return 0
    return get_current_schema_version(cursor)

def apply_migrations():
    """Apply any pending database migrations"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Create schema version table if it doesn't exist
        create_schema_version_table(cursor)
        conn.commit()
        
        # Verify required tables and get/set current version
        current_version = verify_required_tables(cursor)
        conn.commit()
        print(f"Current database schema version: {current_version}")
        
        # Get available migrations
        migrations = get_migration_files()
        if not migrations:
            print("No migration files found")
            return
            
        latest_version = migrations[-1][0]
        
        if current_version >= latest_version:
            print(f"Database is already at latest version {latest_version}")
            return
            
        # Apply pending migrations
        for version, filepath in migrations:
            if version > current_version:
                print(f"Applying migration version {version} from {os.path.basename(filepath)}")
                try:
                    # Read and execute migration file
                    migration_sql = read_migration_file(filepath)
                    cursor.execute(migration_sql)
                    
                    # Update schema version
                    update_schema_version(cursor, version)
                    conn.commit()
                    print(f"Successfully applied migration version {version}")
                    
                except Exception as e:
                    conn.rollback()
                    print(f"Error applying migration version {version}: {e}")
                    raise
        
        print(f"Database successfully updated to version {latest_version}")
        
    except Exception as e:
        conn.rollback()
        print(f"Error updating database: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    apply_migrations()
