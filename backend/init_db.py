#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

def get_db_connection():
    """Create and return a database connection"""
    load_dotenv()
    
    # Check for required environment variables
    required_vars = ['DB_NAME', 'DB_USER', 'DB_PWD', 'DB_HOST']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
    # Check if running in Cloud Run (INSTANCE_CONNECTION_NAME will be set)
    instance_connection_name = os.getenv('INSTANCE_CONNECTION_NAME')
    if instance_connection_name:
        # Use Unix domain socket for Cloud SQL
        db_socket_dir = '/cloudsql'
        cloud_sql_connection_name = os.getenv('INSTANCE_CONNECTION_NAME')
        
        conn = psycopg2.connect(
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PWD'),
            host=f'{db_socket_dir}/{cloud_sql_connection_name}',
            connect_timeout=30
        )
    else:
        # Use regular connection for local development
        conn = psycopg2.connect(
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PWD'),
            host=os.getenv('DB_HOST'),
            sslmode='require',  # Required for Neon database connections
            connect_timeout=30  # Set connection timeout to 30 seconds
        )
    return conn

def get_current_schema_version(cursor):
    """Get the current schema version from the database"""
    try:
        cursor.execute('SELECT version FROM schema_version')
        result = cursor.fetchone()
        return result[0] if result else 0
    except psycopg2.Error:
        # Table doesn't exist, assume version 0
        return 0

def create_schema_version_table(cursor):
    """Create the schema version tracking table if it doesn't exist"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    ''')

def update_schema_version(cursor, version):
    """Update the schema version in the database"""
    cursor.execute('DELETE FROM schema_version')
    cursor.execute('INSERT INTO schema_version (version) VALUES (%s)', (version,))

def init_db():
    """Initialize or update the database schema"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Create schema version table
        create_schema_version_table(cursor)
        conn.commit()
        
        # Get current schema version
        current_version = get_current_schema_version(cursor)
        
        # Enable required extensions
        cursor.execute('CREATE EXTENSION IF NOT EXISTS vector;')
        cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm;')
        
        # Define the latest schema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transcripts (
                segment_hash TEXT PRIMARY KEY,
                title TEXT,
                date TIMESTAMP,
                youtube_id TEXT,
                source TEXT,
                speaker TEXT,
                company TEXT,
                start_time INTEGER,
                end_time INTEGER,
                duration INTEGER,
                subjects TEXT[],
                download TEXT,
                text TEXT,
                text_vector vector(384),  -- for semantic search
                search_vector tsvector     -- for full-text search
            );
            
            -- Create GiST index for trigram similarity on speaker and company
            CREATE INDEX IF NOT EXISTS idx_speaker_trgm 
            ON transcripts USING gist (speaker gist_trgm_ops);
            
            CREATE INDEX IF NOT EXISTS idx_company_trgm 
            ON transcripts USING gist (company gist_trgm_ops);
            
            -- Create B-tree index for date range queries
            CREATE INDEX IF NOT EXISTS idx_date 
            ON transcripts (date);
            
            -- Create GIN index for full-text search
            CREATE INDEX IF NOT EXISTS idx_search_vector 
            ON transcripts USING gin(search_vector);
            
            -- Create IVF index for vector similarity search
            CREATE INDEX IF NOT EXISTS idx_text_vector 
            ON transcripts USING ivfflat (text_vector vector_cosine_ops)
            WITH (lists = 100);
            
            -- Create index on youtube_id for efficient lookups
            CREATE INDEX IF NOT EXISTS idx_youtube_id
            ON transcripts (youtube_id);
        ''')
        
        # Update schema version to latest
        latest_version = 1  # Increment this when making schema changes
        if current_version < latest_version:
            update_schema_version(cursor, latest_version)
            print(f"Schema updated from version {current_version} to {latest_version}")
        else:
            print(f"Schema is already at latest version {latest_version}")
        
        conn.commit()
        print("Database initialization completed successfully")
        
    except Exception as e:
        conn.rollback()
        print(f"Error initializing database: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    init_db()
