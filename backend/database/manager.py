# backend/database/manager.py
"""
Data Access Layer (DAL) for TTV AI Clipper.
Centralizes all database operations and connection management.
"""

import psycopg2
from psycopg2.extras import execute_values, Json
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from functools import wraps
import time
import logging
import os
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional, Union, Tuple
import json # For formatting JSONB query

# Local import for type hint - requires careful handling or moving ParsedQuery
# from backend.query_models import ParsedQuery

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
        # If all retries fail, raise the last encountered error
        logger.error(f"Database operation failed after {MAX_RETRIES} attempts: {last_error}")
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
            # Ensure connection is returned even on error during setup
            if conn is not None:
                self._read_pool.putconn(conn)
            raise
        finally:
            if conn is not None:
                # Ensure connection is returned after use
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
            # Ensure connection is returned even on error during setup
            if conn is not None:
                self._write_pool.putconn(conn)
            raise
        finally:
            if conn is not None:
                 # Ensure connection is returned after use
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
                         subjects=None, download=None, text=None, embedding=None,
                         sentiment_score=None, sentiment_label=None, entities=None):
        """Add a single transcript entry with all its metadata, including sentiment and entities."""
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                try:
                    # Ensure entities is a dict or None for JSONB insertion
                    entities_json = Json(entities) if entities is not None else None

                    cur.execute('''
                        INSERT INTO transcripts (
                            segment_hash, title, date, youtube_id, source, speaker, company,
                            start_time, end_time, duration, subjects, download, text,
                            text_vector, search_vector,
                            sentiment_score, sentiment_label, entities
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            to_tsvector('english', COALESCE(%s, '') || ' ' ||
                                                 COALESCE(%s, '') || ' ' ||
                                                 COALESCE(%s, '') || ' ' ||
                                                 COALESCE(%s, '')),
                            %s, %s, %s
                        )
                    ''', (
                        segment_hash, title, date, youtube_id, source, speaker, company,
                        start_time, end_time, duration, subjects, download, text,
                        embedding,
                        # ts_vector components
                        title, speaker, company, text,
                        # New fields
                        sentiment_score, sentiment_label, entities_json
                    ))
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error adding single transcript {segment_hash}: {e}")
                    raise e

    @with_retry
    def add_transcripts_batch_db(self, transcripts: List[Dict[str, Any]], embeddings: List[List[float]]):
        """Batch insert multiple transcripts with embeddings, sentiment, and entities."""
        with self.get_write_conn() as conn:
            with conn.cursor() as cur:
                # Prepare data for batch insert
                data = []
                for transcript, embedding in zip(transcripts, embeddings):
                    # Ensure entities is suitable for JSONB
                    entities_data = transcript.get('entities')
                    entities_json = Json(entities_data) if entities_data is not None else None

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
                        f"{transcript.get('title', '')} {transcript.get('speaker', '')} {transcript.get('company', '')} {transcript.get('text', '')}",
                        # New fields
                        transcript.get('sentiment_score'),
                        transcript.get('sentiment_label'),
                        entities_json
                    ))

                try:
                    # Note the updated template for new columns
                    execute_values(
                        cur,
                        '''
                        INSERT INTO transcripts (
                            segment_hash, title, date, youtube_id, source, speaker, company,
                            start_time, end_time, duration, subjects, download, text,
                            text_vector, search_vector,
                            sentiment_score, sentiment_label, entities
                        )
                        VALUES %s
                        ''',
                        data,
                        template='''(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, to_tsvector('english', %s), %s, %s, %s)'''
                    )
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error adding batch transcripts: {e}")
                    raise e

    # <<< REVISED hybrid_search_db implementation >>>
    @with_retry
    def hybrid_search_db(self, parsed_query: 'ParsedQuery', search_embedding: List[float], semantic_weight: float = 0.5, limit: int = 10):
        """
        Perform hybrid search using parsed query details, combining semantic similarity,
        full-text search, and enriched metadata filtering (sentiment, entities).
        Handles filter-only searches separately.

        Args:
            parsed_query: The ParsedQuery object containing structured query details.
            search_embedding: The embedding vector generated from the parsed concepts (used only if text search).
            semantic_weight: Weight for semantic search score (0.0 to 1.0) (used only if text search).
            limit: Maximum number of results.

        Returns:
            List of matching transcripts with similarity scores (if applicable).
        """
        # Import here to avoid circular dependency issues at module load time
        from backend.query_models import ParsedQuery

        # Determine if the search is text-based or filter-only
        is_filter_only_search = not parsed_query.original_query or parsed_query.original_query.isspace()
        logger.info(f"Hybrid search mode: {'Filter-only' if is_filter_only_search else 'Text-based'}")

        # --- Build Query Components ---
        select_columns = '''
            segment_hash, title, date, youtube_id, source, speaker, company,
            start_time, end_time, duration, subjects, download, text,
            sentiment_score, sentiment_label, entities
        '''
        from_clause = "FROM transcripts"
        where_clauses = ["WHERE 1=1"] # Start with a base condition
        params = []
        order_by_clause = ""
        similarity_calculation = ""

        # --- Add Similarity Calculation and Params ONLY if search text exists ---
        if not is_filter_only_search:
            similarity_calculation = """,
                (
                    %s * (1 - (text_vector <=> %s::vector)) +
                    %s * ts_rank_cd(search_vector, plainto_tsquery('english', %s))
                ) as similarity
            """
            # Prepend similarity params - MUST match the order in the calculation
            similarity_params = [
                semantic_weight,
                search_embedding,
                1 - semantic_weight,
                parsed_query.original_query # Use original query for full-text
            ]
            params = similarity_params + params # Add similarity params first
            select_columns += similarity_calculation # Add similarity column to SELECT

        # --- Add Filters based on Parsed Query (Metadata, Sentiment, Entities) ---
        filters = parsed_query.filters # Filters merged in TranscriptSearch

        # 1. Standard Metadata Filters (Speaker, Company, Date, Duration, Title, etc.)
        if filters:
            if 'date_range' in filters and filters['date_range'] and len(filters['date_range']) == 2:
                where_clauses.append('date BETWEEN %s AND %s')
                params.extend([filters['date_range'][0], filters['date_range'][1]])

            speaker_filters = filters.get('speakers')
            company_filters = filters.get('companies')

            # Apply speaker/company filters to their dedicated columns
            if speaker_filters and isinstance(speaker_filters, list) and speaker_filters:
                 where_clauses.append('speaker = ANY(%s)')
                 params.append(speaker_filters)
            if company_filters and isinstance(company_filters, list) and company_filters:
                 where_clauses.append('company = ANY(%s)')
                 params.append(company_filters)

            # Subjects filter (might be less relevant now)
            if 'subjects' in filters and filters['subjects'] and isinstance(filters['subjects'], list):
                where_clauses.append('subjects && %s::TEXT[]') # Use explicit cast
                params.append(filters['subjects'])

            if 'min_duration' in filters and filters['min_duration'] is not None:
                try:
                    where_clauses.append('duration >= %s')
                    params.append(int(filters['min_duration']))
                except (ValueError, TypeError):
                    logger.warning(f"Invalid min_duration filter value: {filters['min_duration']}")

            if 'max_duration' in filters and filters['max_duration'] is not None:
                try:
                    where_clauses.append('duration <= %s')
                    params.append(int(filters['max_duration']))
                except (ValueError, TypeError):
                     logger.warning(f"Invalid max_duration filter value: {filters['max_duration']}")

            if 'title' in filters and filters['title']:
                where_clauses.append('title ILIKE %s')
                params.append(f'%{filters["title"]}%')

        # 2. Sentiment Filtering (based on parsed_query.sentiment_intent and sentiment_label column)
        sentiment_intent = parsed_query.sentiment_intent
        target_label = None
        if sentiment_intent == "positive":
            target_label = 'positive'
        elif sentiment_intent == "negative":
            target_label = 'negative'
        elif sentiment_intent == "neutral":
            target_label = 'neutral'
        # For comparative intents, filter by label first, then order by score later
        elif sentiment_intent == "happiest":
            target_label = 'positive' # Filter for positive results first
        elif sentiment_intent == "most_negative":
            target_label = 'negative' # Filter for negative results first

        if target_label:
            where_clauses.append('sentiment_label = %s')
            params.append(target_label)
        # 'objective' and 'unclear' intents do not add sentiment filters by default

        # 3. Entity Filtering (using JSONB @> operator based on parsed_query.entities)
        # This checks if the indexed 'entities' JSONB contains the entities specified *in the query text*.
        # This is separate from the explicit speaker/company filters above.
        if parsed_query.entities:
            for entity_type, entity_list in parsed_query.entities.items():
                if entity_list and isinstance(entity_list, list): # Ensure it's a non-empty list
                    # Construct the JSONB object string for the query for this specific type
                    # Check if the entities column contains the specified entities
                    jsonb_filter = json.dumps({entity_type: entity_list})
                    where_clauses.append('entities @> %s::jsonb')
                    params.append(jsonb_filter)

        # 4. Relationship Filtering (Basic Example: Check if concepts appear in text using FTS)
        # --- Apply ONLY if search text exists ---
        if not is_filter_only_search and parsed_query.relationships:
             # Example: "mentions X and Y" -> check if both X and Y are in text
             related_concepts = parsed_query.search_concepts
             if len(related_concepts) > 1 and " and " in parsed_query.relationships.lower(): # Basic check
                 logger.info(f"Applying relationship filter for concepts: {related_concepts}")
                 for concept in related_concepts:
                     # Add a full-text condition for each concept
                     where_clauses.append("search_vector @@ plainto_tsquery('english', %s)")
                     params.append(concept)

        # --- Determine Ordering ---
        if not is_filter_only_search:
            # Order by similarity if text search was performed
            order_by_clause = "ORDER BY similarity DESC"
            # Adjust for comparative sentiment intents (already filtered by label)
            if sentiment_intent == "happiest":
                # Order positive results by score descending (0-1 range), then similarity
                order_by_clause = "ORDER BY sentiment_score DESC NULLS LAST, similarity DESC"
            elif sentiment_intent == "most_negative":
                 # Order negative results by score ascending (-1 to 0 range), then similarity
                 order_by_clause = "ORDER BY sentiment_score ASC NULLS LAST, similarity DESC"
        else:
            # Default order for filter-only search (no similarity score available)
            # Order by date descending, then start time ascending as a sensible default
            order_by_clause = "ORDER BY date DESC NULLS LAST, start_time ASC NULLS LAST"

        # --- Combine Query Parts ---
        query = f"SELECT {select_columns}\n{from_clause}\n"
        # Combine WHERE clauses with AND
        if len(where_clauses) > 1:
            query += " AND ".join(where_clauses[1:]) # Join clauses after the initial "WHERE 1=1"
        else:
            # If only "WHERE 1=1" exists, we don't need a WHERE clause unless we add more conditions later
            # For safety, keep it simple: if no filters added, the WHERE 1=1 remains.
            # If filters were added, the join above handles it.
            pass # No additional clauses needed if only WHERE 1=1

        query += f"\n{order_by_clause}"
        query += "\nLIMIT %s;"
        params.append(limit)

        logger.debug(f"Executing hybrid search query: {query}")
        # Avoid logging potentially sensitive embeddings/params if necessary
        # logger.debug(f"Query parameters: {params}")

        # Execute search
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                results = cur.fetchall()

        # --- Result Formatting ---
        # Define base column names
        column_names = [
            'segment_hash', 'title', 'date', 'youtube_id', 'source', 'speaker', 'company',
            'start_time', 'end_time', 'duration', 'subjects', 'download', 'text',
            'sentiment_score', 'sentiment_label', 'entities'
        ]
        # Add 'similarity' column name ONLY if it was calculated
        if not is_filter_only_search:
            column_names.append('similarity')

        formatted_results = []
        # Check if the number of columns matches fetchall result
        if results and len(results[0]) != len(column_names):
             logger.error(f"Column name count ({len(column_names)}) does not match fetched data count ({len(results[0])}). Check SELECT statement and conditional 'similarity'.")
             # Fallback or raise error - basic formatting for now
             formatted_results = [list(row) for row in results] # Return raw rows on mismatch
        else:
            for row in results:
                formatted_results.append(dict(zip(column_names, row)))

        return formatted_results
    # <<< END REVISED hybrid_search_db implementation >>>

    @with_retry
    def get_metadata_by_hash_db(self, segment_hash):
        """Get metadata for a specific segment by its hash, including new fields."""
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT
                        segment_hash, title, date, youtube_id, source, speaker, company,
                        start_time, end_time, duration, subjects, download, text,
                        sentiment_score, sentiment_label, entities
                    FROM transcripts
                    WHERE segment_hash = %s
                ''', (segment_hash,))

                result = cur.fetchone()

        if result:
            # Map results to a dictionary including new fields
            column_names = [
                'segment_hash', 'title', 'date', 'youtube_id', 'source', 'speaker', 'company',
                'start_time', 'end_time', 'duration', 'subjects', 'download', 'text',
                'sentiment_score', 'sentiment_label', 'entities'
            ]
            return dict(zip(column_names, result))
        return None

    @with_retry
    def get_available_filters_db(self):
        """Fetch and store unique values for each filterable field from the database"""
        # This might need adjustment if 'subjects' becomes less relevant
        with self.get_read_conn() as conn:
            with conn.cursor() as cur:
                # Get unique speakers
                cur.execute('SELECT DISTINCT speaker FROM transcripts WHERE speaker IS NOT NULL ORDER BY speaker')
                speakers = [row[0] for row in cur.fetchall()]

                # Get unique dates and format them
                cur.execute('''
                    SELECT DISTINCT date::date
                    FROM transcripts
                    WHERE date IS NOT NULL
                    ORDER BY date DESC
                ''')
                # Use ISO format for consistency, frontend can format
                dates = [row[0].isoformat() for row in cur.fetchall()]

                # Get unique titles
                cur.execute('SELECT DISTINCT title FROM transcripts WHERE title IS NOT NULL ORDER BY title')
                titles = [row[0] for row in cur.fetchall()]

                # Get unique companies
                cur.execute('SELECT DISTINCT company FROM transcripts WHERE company IS NOT NULL ORDER BY company')
                companies = [row[0] for row in cur.fetchall()]

                # Get unique subjects (consider deprecating if not used)
                cur.execute('SELECT DISTINCT unnest(subjects) FROM transcripts WHERE subjects IS NOT NULL ORDER BY 1')
                subjects = [row[0] for row in cur.fetchall()]

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
                            WHEN %s = 'running' AND started_at IS NULL THEN CURRENT_TIMESTAMP
                            ELSE started_at
                        END,
                        completed_at = CASE
                            WHEN %s IN ('completed', 'failed', 'deleted') THEN CURRENT_TIMESTAMP
                            ELSE completed_at
                        END
                    WHERE id = %s
                ''', (status, error_message, status, status, job_id)) # Pass status multiple times
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
        # Ensure 'transcript' key exists in updated_transcript
        updated_transcript_data = content.get("transcript", existing_transcript.get("transcript", []))
        updated_transcript = {
            "metadata": updated_metadata,
            "raw_transcript": updated_raw_transcript,
            "transcript": updated_transcript_data
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
                ''', (Json(updated_metadata), updated_raw_transcript, job_id))

                # Update or insert full transcript in job_transcripts
                cur.execute('''
                    INSERT INTO job_transcripts (job_id, transcript)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (job_id)
                    DO UPDATE SET transcript = EXCLUDED.transcript
                ''', (job_id, Json(updated_transcript)))

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
                    # Update: Changed to DELETE the job entirely after clearing related content
                    # cur.execute('''
                    #     UPDATE ingest_jobs
                    #     SET metadata = NULL,
                    #         raw_transcript = NULL,
                    #         parsing_status = NULL,
                    #         html_fetch_success = NULL,
                    #         video_fetch_success = NULL,
                    #         error_message = NULL,
                    #         transcript_edited_at = NULL
                    #     WHERE id = %s
                    # ''', (job_id,))
                    # cleared_job_rows = cur.rowcount

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
                        # "cleared_job_rows": cleared_job_rows, # Removed as job is deleted
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
                ''', (Json(parsing_status), job_id))
                conn.commit()
