# backend/database/manager.py
"""
Data Access Layer (DAL) for TTV AI Clipper.
Centralizes all database operations and connection management.
"""

import psycopg2
from psycopg2.extras import execute_values
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from functools import wraps
import time
import logging
import os
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional, Union, Tuple

# Configure logging
logger = logging.getLogger(__name__)

# Maximum number of retries for database operations
MAX_RETRIES = 5
RETRY_DELAY = 1  # seconds

# Error types to retry on
RETRY_ERRORS = (
    psycopg2.OperationalError,  # Connection related errors
    psycopg2.InterfaceError,    # Connection related errors
    psycopg2.InternalError      # Internal database errors
)

def with_retry(func):
    """Decorator to retry database operations with exponential backoff"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except RETRY_ERRORS as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Database operation failed, retrying in {delay}s: {str(e)}")
                    time.sleep(delay)
                    continue
        raise last_error
    return wrapper

class DatabaseManager:
    """
    Singleton class that manages database connections and operations.
    Provides separate connection pools for read and write operations.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        load_dotenv()
        
        # Initialize connection pools
        self._read_pool = self._create_read_pool()
        self._write_pool = self._create_write_pool()
        
        self._initialized = True
    
    def _create_read_pool(self):
        """Create a read-only connection pool"""
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
            connection_args = {
                'dbname': os.getenv('DB_NAME'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PWD'),
                'host': f'{db_socket_dir}/{cloud_sql_connection_name}',
                'connect_timeout': 30
            }
        else:
            # Use regular connection for local development
            connection_args = {
                'dbname': os.getenv('DB_NAME'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PWD'),
                'host': os.getenv('DB_HOST'),
                'sslmode': 'require',  # Required for Neon database connections
                'connect_timeout': 30,  # Set connection timeout to 30 seconds
                'keepalives': 1,  # Enable TCP keepalives
                'keepalives_idle': 5,  # Reduced idle time before first keepalive
                'keepalives_interval': 2,  # More frequent keepalive retransmits
                'keepalives_count': 5,  # Reduced number of retries for faster failure detection
                'tcp_user_timeout': 5000,  # Reduced TCP timeout for faster failure detection
                'application_name': 'ttv-ai-clipper-read'  # Identify application in database logs
            }
            
        # Add read-only option to connection args
        connection_args['options'] = '-c default_transaction_read_only=on'
        
        try:
            # Use optimized pool settings for read operations
            return ThreadedConnectionPool(
                minconn=10,  # Higher minimum connections for read operations
                maxconn=30,  # Higher maximum connections for concurrent reads
                **connection_args
            )
        except Exception as e:
            logger.error(f"Failed to initialize read connection pool: {str(e)}")
            raise
    
    def _create_write_pool(self):
        """Create a write connection pool"""
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
            connection_args = {
                'dbname': os.getenv('DB_NAME'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PWD'),
                'host': f'{db_socket_dir}/{cloud_sql_connection_name}',
                'connect_timeout': 30
            }
        else:
            # Use regular connection for local development
            connection_args = {
                'dbname': os.getenv('DB_NAME'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PWD'),
                'host': os.getenv('DB_HOST'),
                'sslmode': 'require',  # Required for Neon database connections
                'connect_timeout': 30,  # Set connection timeout to 30 seconds
                'keepalives': 1,  # Enable TCP keepalives
                'keepalives_idle': 10,  # Idle time before first keepalive
                'keepalives_interval': 5,  # Seconds between keepalive retransmits
                'keepalives_count': 10,  # Max number of keepalive retransmits
                'tcp_user_timeout': 10000,  # TCP timeout in milliseconds
                'application_name': 'ttv-ai-clipper-write'  # Identify application in database logs
            }
            
        try:
            # Use optimized pool settings for write operations
            return ThreadedConnectionPool(
                minconn=5,   # Fewer minimum connections for write operations
                maxconn=20,  # Lower maximum connections to prevent excessive writes
                **connection_args
            )
        except Exception as e:
            logger.error(f"Failed to initialize write connection pool: {str(e)}")
            raise
    
    @contextmanager
    def get_read_conn(self):
        """Context manager for getting a read-only connection with proper isolation"""
        conn = None
        try:
            conn = self._read_pool.getconn()
            with conn.cursor() as cur:
                # Set read committed isolation level for consistent reads
                cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                # Set statement timeout to prevent long waits
                cur.execute('SET LOCAL statement_timeout = 5000')  # 5 seconds
            yield conn
        except Exception as e:
            logger.error(f"Database read connection error: {str(e)}")
            raise
        finally:
            if conn is not None:
                self._read_pool.putconn(conn)
    
    @contextmanager
    def get_write_conn(self):
        """Context manager for getting a write connection with proper isolation"""
        conn = None
        try:
            conn = self._write_pool.getconn()
            with conn.cursor() as cur:
                # Set repeatable read isolation level for write operations
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                # Set longer timeout for write operations
                cur.execute('SET LOCAL statement_timeout = 30000')  # 30 seconds
            yield conn
        except Exception as e:
            logger.error(f"Database write connection error: {str(e)}")
            raise
        finally:
            if conn is not None:
                self._write_pool.putconn(conn)
    
    def close_pools(self):
        """Close all connection pools"""
        if hasattr(self, '_read_pool') and self._read_pool:
            self._read_pool.closeall()
            self._read_pool = None
        if hasattr(self, '_write_pool') and self._write_pool:
            self._write_pool.closeall()
            self._write_pool = None
        logger.info("Database connection pools closed")
    
    #
    # Transcript Search Operations
    #
    
    @with_retry
    def add_transcript_db(self, segment_hash, title, date, youtube_id, source, speaker, 
                         company=None, start_time=None, end_time=None, duration=None, 
                         subjects=None, download=None, text=None, embedding=None):
        """Add a single transcript entry with all its metadata"""
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute('''
                        INSERT INTO transcripts (
                            segment_hash, title, date, youtube_id, source, speaker, company,
                            start_time, end_time, duration, subjects, download, text,
                            text_vector, search_vector
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            to_tsvector('english', COALESCE(%s, '') || ' ' || 
                                                 COALESCE(%s, '') || ' ' || 
                                                 COALESCE(%s, '') || ' ' ||
                                                 COALESCE(%s, ''))
                        )
                    ''', (
                        segment_hash, title, date, youtube_id, source, speaker, company,
                        start_time, end_time, duration, subjects, download, text,
                        embedding,
                        title, speaker, company, text
                    ))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    raise e
    
    @with_retry
    def add_transcripts_batch_db(self, transcripts, embeddings):
        """Batch insert multiple transcripts with their embeddings"""
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                # Prepare data for batch insert
                data = []
                for transcript, embedding in zip(transcripts, embeddings):
                    data.append((
                        transcript['segment_hash'],
                        transcript['title'],
                        transcript['date'],
                        transcript['youtube_id'],
                        transcript['source'],
                        transcript['speaker'],
                        transcript.get('company'),
                        transcript.get('start_time'),
                        transcript.get('end_time'),
                        transcript.get('duration'),
                        transcript.get('subjects'),
                        transcript.get('download'),
                        transcript['text'],
                        embedding,
                        # Concatenate fields for full-text search
                        f"{transcript['title']} {transcript['speaker']} {transcript.get('company', '')} {transcript['text']}"
                    ))
                
                try:
                    execute_values(
                        cur,
                        '''
                        INSERT INTO transcripts (
                            segment_hash, title, date, youtube_id, source, speaker, company,
                            start_time, end_time, duration, subjects, download, text,
                            text_vector, search_vector
                        )
                        VALUES %s
                        ''',
                        data,
                        template='''(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, to_tsvector('english', %s))'''
                    )
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    raise e
    
    @with_retry
    def hybrid_search_db(self, search_text, search_embedding, filters=None, semantic_weight=0.5, limit=10):
        """Perform hybrid search combining semantic similarity, full-text search, and metadata filtering"""
        # Initialize filters dict if None
        if filters is None:
            filters = {}
            
        # Build the query
        query = '''
            WITH combined_scores AS (
                SELECT 
                    segment_hash,
                    title,
                    date,
                    youtube_id,
                    source,
                    speaker,
                    company,
                    start_time,
                    end_time,
                    duration,
                    subjects,
                    download,
                    text,
                    -- Combine semantic and full-text search scores
                    (
                        %s * (1 - (text_vector <=> %s::vector)) +
                        %s * ts_rank_cd(search_vector, plainto_tsquery('english', %s))
                    ) as similarity
                FROM transcripts
                WHERE 1=1
        '''
        
        params = [
            semantic_weight,
            search_embedding,
            1 - semantic_weight,
            search_text
        ]
        
        # Add filters if provided
        if filters:
            if 'date_range' in filters:
                query += ' AND date BETWEEN %s AND %s'
                params.extend([filters['date_range'][0], filters['date_range'][1]])
            
            # Handle speakers and companies with OR logic when both are present
            if 'speakers' in filters and filters['speakers'] and 'companies' in filters and filters['companies']:
                query += ' AND (speaker = ANY(%s) OR company = ANY(%s))'
                params.extend([filters['speakers'], filters['companies']])
            else:
                # If only one filter is present, use normal AND logic
                if 'speakers' in filters and filters['speakers']:
                    query += ' AND speaker = ANY(%s)'
                    params.append(filters['speakers'])
                if 'companies' in filters and filters['companies']:
                    query += ' AND company = ANY(%s)'
                    params.append(filters['companies'])

            if 'subjects' in filters and filters['subjects']:
                query += ' AND subjects && ARRAY[%s]'
                params.append(filters['subjects'])
                        
            if 'min_duration' in filters:
                query += ' AND duration >= %s'
                params.append(filters['min_duration'])
            
            if 'max_duration' in filters:
                query += ' AND duration <= %s'
                params.append(filters['max_duration'])
                
            if 'title' in filters and filters['title']:
                query += ' AND title ILIKE %s'
                params.append(f'%{filters["title"]}%')
        
        # Complete the query
        query += '''
            )
            SELECT * FROM combined_scores
            ORDER BY similarity DESC
            LIMIT %s;
        '''
        params.append(limit)
        
        # Execute search
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                results = cur.fetchall()
        
        # Format results
        formatted_results = []
        for row in results:
            formatted_results.append({
                'segment_hash': row[0],
                'title': row[1],
                'date': row[2],
                'youtube_id': row[3],
                'source': row[4],
                'speaker': row[5],
                'company': row[6],
                'start_time': row[7],
                'end_time': row[8],
                'duration': row[9],
                'subjects': row[10],
                'download': row[11],
                'text': row[12],
                'similarity': row[13]
            })
        
        return formatted_results
    
    @with_retry
    def get_metadata_by_hash_db(self, segment_hash):
        """Get metadata for a specific segment by its hash"""
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT 
                        segment_hash, title, date, youtube_id, source, speaker, company,
                        start_time, end_time, duration, subjects, download, text
                    FROM transcripts 
                    WHERE segment_hash = %s
                ''', (segment_hash,))
                
                result = cur.fetchone()
        
        if result:
            return {
                'segment_hash': result[0],
                'title': result[1],
                'date': result[2],
                'youtube_id': result[3],
                'source': result[4],
                'speaker': result[5],
                'company': result[6],
                'start_time': result[7],
                'end_time': result[8],
                'duration': result[9],
                'subjects': result[10],
                'download': result[11],
                'text': result[12]
            }
        return None
    
    @with_retry
    def get_available_filters_db(self):
        """Fetch and store unique values for each filterable field from the database"""
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                # Get unique speakers
                cur.execute('SELECT DISTINCT speaker FROM transcripts ORDER BY speaker')
                speakers = [row[0] for row in cur.fetchall()]

                # Get unique dates and format them
                cur.execute('''
                    SELECT DISTINCT date::date 
                    FROM transcripts 
                    ORDER BY date DESC
                ''')
                dates = [row[0].strftime("%b %d, %Y") for row in cur.fetchall()]

                # Get unique titles
                cur.execute('SELECT DISTINCT title FROM transcripts ORDER BY title')
                titles = [row[0] for row in cur.fetchall()]

                # Get unique companies
                cur.execute('SELECT DISTINCT company FROM transcripts ORDER BY company')
                companies = [row[0] for row in cur.fetchall() if row[0] is not None]

                # Get unique subjects
                cur.execute('SELECT DISTINCT unnest(subjects) FROM transcripts ORDER BY 1')
                subjects = [row[0] for row in cur.fetchall() if row[0] is not None]

                return {
                    "speakers": speakers,
                    "dates": dates,
                    "titles": titles,
                    "companies": companies,
                    "subjects": subjects
                }
    
    #
    # Job Management Operations
    #
    
    @with_retry
    def create_job_db(self, url, user_email, status='pending'):
        """Create a new ingest job"""
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO ingest_jobs (url, status, user_email)
                    VALUES (%s, %s, %s)
                    RETURNING id, url, status, created_at, started_at, completed_at, error_message, user_email, detailed_workflow_state
                ''', (url, status, user_email))
                
                conn.commit()
                row = cur.fetchone()
        
        return row
    
    @with_retry
    def get_job_db(self, job_id):
        """Get job by ID"""
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT id, url, status, created_at, started_at, completed_at, error_message, user_email, detailed_workflow_state
                    FROM ingest_jobs
                    WHERE id = %s
                ''', (job_id,))
                
                return cur.fetchone()
    
    @with_retry
    def list_jobs_db(self, user_email=None, limit=100):
        """List jobs with optional filtering by user"""
        query = '''
            SELECT id, url, status, created_at, started_at, completed_at, error_message, user_email, detailed_workflow_state
            FROM ingest_jobs
        '''
        params = []
        
        if user_email:
            query += ' WHERE user_email = %s'
            params.append(user_email)
            
        query += ' ORDER BY created_at DESC LIMIT %s'
        params.append(limit)
        
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()
    
    @with_retry
    def update_job_status_db(self, job_id, status, error_message=None):
        """Update job status and timestamps"""
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE ingest_jobs 
                    SET status = %s,
                        error_message = COALESCE(%s, error_message),
                        started_at = CASE 
                            WHEN status = %s AND started_at IS NULL THEN CURRENT_TIMESTAMP
                            ELSE started_at
                        END,
                        completed_at = CASE 
                            WHEN status IN (%s, %s, %s) THEN CURRENT_TIMESTAMP
                            ELSE completed_at
                        END
                    WHERE id = %s
                ''', (status, error_message, 'running', 
                      'completed', 'failed', 'deleted', 
                      job_id))
                conn.commit()
    
    @with_retry
    def get_job_log_db(self, job_id):
        """Get the log file content for a job"""
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT last_log_file FROM ingest_jobs WHERE id = %s', (job_id,))
                result = cur.fetchone()
                return result[0] if result and result[0] else ""
    
    @with_retry
    def update_log_file_db(self, job_id, log_content):
        """Update the log file content for a job"""
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE ingest_jobs 
                    SET last_log_file = %s
                    WHERE id = %s
                ''', (log_content, job_id))
                conn.commit()

    @with_retry
    def get_archivable_jobs_db(self) -> List[Tuple[int, Optional[str]]]:
        """Get job_id and youtube_id for jobs ready for archival/deletion"""
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT id, metadata->>'youtube_id' as youtube_id 
                    FROM ingest_jobs 
                    WHERE status IN ('completed', 'failed', 'deleted')
                ''')
                return cur.fetchall()
    
    #
    # Workflow Operations
    #
    
    @with_retry
    def get_job_details_db(self, job_id):
        """Get detailed job information including metadata and transcript"""
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT 
                        i.status,
                        i.workflow_state,
                        i.detailed_workflow_state,
                        i.html_fetch_success,
                        i.video_fetch_success,
                        i.error_message,
                        i.parsing_status,
                        i.metadata,
                        i.raw_transcript
                    FROM ingest_jobs i
                    WHERE i.id = %s
                ''', (job_id,))
                result = cur.fetchone()
                
                if not result:
                    raise ValueError(f"Job {job_id} not found")
                
                (status, workflow_state, detailed_workflow_state, 
                 html_fetch_success, video_fetch_success, error_message, 
                 parsing_status, metadata, raw_transcript) = result
                
                return {
                    "metadata": metadata or {},
                    "raw_transcript": raw_transcript or "",
                    "job": {
                        "id": job_id,
                        "status": status,
                        "workflow_state": workflow_state,
                        "detailed_workflow_state": detailed_workflow_state,
                        "html_fetch_success": html_fetch_success,
                        "video_fetch_success": video_fetch_success,
                        "error_message": error_message,
                        "parsing_status": parsing_status if parsing_status else {"success": False, "error": ""}
                    }
                }
    
    @with_retry
    def update_workflow_state_db(self, job_id, state, error_message=None):
        """Update job workflow state"""
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                # Get previous state for logging
                cur.execute('SELECT workflow_state FROM ingest_jobs WHERE id = %s', (job_id,))
                result = cur.fetchone()
                prev_state = result[0] if result else None
                
                # Update state
                cur.execute('''
                    UPDATE ingest_jobs 
                    SET workflow_state = %s,
                        detailed_workflow_state = %s,
                        error_message = COALESCE(%s, error_message)
                    WHERE id = %s
                ''', (state, state, error_message, job_id))
                conn.commit()
                
        return prev_state
    
    @with_retry
    def update_content_db(self, job_id, content):
        """Update transcript content in ingest_jobs and job_transcripts"""
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT i.metadata, i.raw_transcript, jt.transcript 
                    FROM ingest_jobs i 
                    LEFT JOIN job_transcripts jt ON i.id = jt.job_id 
                    WHERE i.id = %s
                ''', (job_id,))
                result = cur.fetchone()
                existing_metadata = result[0] if result and result[0] else {}
                existing_raw = result[1] if result and result[1] else ""
                existing_transcript = result[2] if result and result[2] else {}
        
        # Create updated content
        updated_metadata = content.get("metadata", existing_metadata)
        updated_raw_transcript = content.get("raw_transcript", existing_raw)
        updated_transcript = {
            "metadata": updated_metadata,
            "raw_transcript": updated_raw_transcript,
            "transcript": content.get("transcript", existing_transcript.get("transcript", []))
        }
        
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                # Update metadata and raw_transcript in ingest_jobs
                cur.execute('''
                    UPDATE ingest_jobs 
                    SET metadata = %s::jsonb,
                        raw_transcript = %s,
                        transcript_edited_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (psycopg2.extras.Json(updated_metadata), updated_raw_transcript, job_id))

                # Update or insert full transcript in job_transcripts
                cur.execute('''
                    INSERT INTO job_transcripts (job_id, transcript)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (job_id) 
                    DO UPDATE SET transcript = EXCLUDED.transcript
                ''', (job_id, psycopg2.extras.Json(updated_transcript)))
                
                conn.commit()
        
        return updated_transcript
    
    @with_retry
    def delete_job_content_db(self, job_id, youtube_id):
        """Delete all content related to a job including database entries"""
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                try:
                    # Delete from transcripts table
                    cur.execute(
                        'DELETE FROM transcripts WHERE youtube_id = %s',
                        (youtube_id,)
                    )
                    deleted_transcript_rows = cur.rowcount

                    # Delete from job_transcripts
                    cur.execute(
                        'DELETE FROM job_transcripts WHERE job_id = %s',
                        (job_id,)
                    )
                    deleted_job_transcript_rows = cur.rowcount

                    # Clear all related columns in ingest_jobs except state-related and user columns
                    cur.execute('''
                        UPDATE ingest_jobs 
                        SET metadata = NULL,
                            raw_transcript = NULL,
                            parsing_status = NULL,
                            html_fetch_success = NULL,
                            video_fetch_success = NULL,
                            error_message = NULL,
                            transcript_edited_at = NULL
                        WHERE id = %s
                    ''', (job_id,))
                    cleared_job_rows = cur.rowcount
                    
                    # Also delete the main job entry itself
                    cur.execute(
                        'DELETE FROM ingest_jobs WHERE id = %s',
                        (job_id,)
                    )
                    deleted_ingest_job_rows = cur.rowcount

                    conn.commit()
                    
                    return {
                        "deleted_transcript_rows": deleted_transcript_rows,
                        "deleted_job_transcript_rows": deleted_job_transcript_rows,
                        "cleared_job_rows": cleared_job_rows, # This is now effectively 0 as the row is deleted
                        "deleted_ingest_job_rows": deleted_ingest_job_rows
                    }
                    
                except Exception as e:
                    conn.rollback()
                    raise e

    @with_retry
    def delete_content_archive_db(self):
        """
        DEPRECATED: This method is complex and doesn't handle R2. 
        Use get_archivable_jobs_db and delete_job_content_db instead.
        Original logic kept for reference but should not be used.
        """
        logger.warning("delete_content_archive_db is deprecated and should not be used.")
        # Original logic below (commented out or kept minimal for safety)
        # ... original logic ...
        # Returning minimal structure to avoid breaking existing calls immediately,
        # but emphasizing deprecation.
        return {
            "deleted_jobs_count": 0,
            "processed_jobs": []
        }
        
        # --- Start of Original Logic (kept for reference, but inactive) ---
        # with self.get_write_conn() as conn:
        #     with conn.cursor() as cur:
        #         # Find all inactive jobs
        #         cur.execute('''
        #             SELECT id, metadata->>'youtube_id' as youtube_id 
        #             FROM ingest_jobs 
        #             WHERE status IN ('completed', 'failed')
        #             FOR UPDATE
        #         ''')
        #         inactive_jobs = cur.fetchall()
                
        #         results = []
        #         # Delete content for each inactive job
        #         for job_id, youtube_id in inactive_jobs:
        #             try:
        #                 # Delete from transcripts table
        #                 cur.execute(
        #                     'DELETE FROM transcripts WHERE youtube_id = %s',
        #                     (youtube_id,)
        #                 )
        #                 deleted_transcript_rows = cur.rowcount

        #                 # Delete from job_transcripts
        #                 cur.execute(
        #                     'DELETE FROM job_transcripts WHERE job_id = %s',
        #                     (job_id,)
        #                 )
        #                 deleted_job_transcript_rows = cur.rowcount

        #                 # Clear all related columns in ingest_jobs except state-related and user columns
        #                 cur.execute('''
        #                     UPDATE ingest_jobs 
        #                     SET metadata = NULL,
        #                         raw_transcript = NULL,
        #                         parsing_status = NULL,
        #                         html_fetch_success = NULL,
        #                         video_fetch_success = NULL,
        #                         error_message = NULL,
        #                         transcript_edited_at = NULL
        #                     WHERE id = %s
        #                 ''', (job_id,))
        #                 cleared_job_rows = cur.rowcount
                        
        #                 results.append({
        #                     "job_id": job_id,
        #                     "youtube_id": youtube_id,
        #                     "deleted_transcript_rows": deleted_transcript_rows,
        #                     "deleted_job_transcript_rows": deleted_job_transcript_rows,
        #                     "cleared_job_rows": cleared_job_rows
        #                 })
        #             except Exception as e:
        #                 logger.error(f"Failed to delete content for job {job_id}: {str(e)}")
                
        #         # Delete all deleted jobs
        #         cur.execute(
        #             'DELETE FROM ingest_jobs WHERE status = %s', ['deleted']
        #         )
        #         deleted_jobs_count = cur.rowcount
                
        #         conn.commit()
                
        #         return {
        #             "deleted_jobs_count": deleted_jobs_count,
        #             "processed_jobs": results
        #         }
        # --- End of Original Logic ---

    @with_retry
    def validate_transcript_db(self, job_id, parsing_status):
        """Store parsing status in database"""
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE ingest_jobs 
                    SET parsing_status = %s::jsonb
                    WHERE id = %s
                ''', (psycopg2.extras.Json(parsing_status), job_id))
                conn.commit()
