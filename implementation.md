# Database Access Layer Refactoring

## Current Issues

The current database access strategy in the TTV AI Clipper project has several issues:

1. **Scattered Database Logic**: Database access code is spread across multiple modules (`transcript_search.py`, `workflow_processor.py`, `job_manager.py`), leading to code duplication and maintenance challenges.

2. **Inconsistent Connection Management**: 
   - `TranscriptSearch` manages its own connection pool (`ThreadedConnectionPool`).
   - `WorkflowProcessor` attempts to use a separate read-only pool but falls back to the same pool as `TranscriptSearch` for writes.
   - `JobManager` relies on `TranscriptSearch` for database connections.

3. **Mixed Responsibilities**: 
   - `TranscriptSearch` handles both database operations and NLP/embedding logic.
   - `WorkflowProcessor` manages workflow state and performs database operations across multiple tables.
   - `JobManager` manages jobs and performs database operations on the `ingest_jobs` table.

4. **Performance Concerns**: 
   - Potential read/write contention on the `transcripts` table.
   - Celery workers perform bulk writes while API endpoints perform frequent reads.
   - Inconsistent transaction isolation and timeout management.

5. **Redundant Schema Management**: `JobManager.create_schema()` duplicates schema definition logic already in `schema.sql`.

## Proposed Solution: Data Access Layer (DAL)

We will implement a dedicated Data Access Layer (DAL) in `backend/database/manager.py` that will:

1. **Centralize Database Access**: All SQL operations will be defined in one place.
2. **Manage Connection Pools**: Maintain separate read and write connection pools.
3. **Provide Clear Interface**: Offer simple functions for other modules to call.
4. **Encapsulate DB Logic**: Keep database-specific details contained within the DAL.
5. **Standardize Error Handling**: Implement consistent retry and error handling.

## Implementation Details

### 1. Connection Pool Management

The DAL will manage two distinct connection pools:

```python
# In backend/database/manager.py
self._read_pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=10,  # Optimized for read operations
    maxconn=30,  # Higher limit for concurrent reads
    **read_connection_args
)

self._write_pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=5,   # Fewer write connections needed
    maxconn=20,  # Lower limit to prevent excessive writes
    **write_connection_args
)
```

### 2. Connection Context Managers

The DAL will provide context managers for acquiring and releasing connections:

```python
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
```

### 3. Retry Mechanism

The DAL will include a retry decorator for database operations:

```python
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
```

### 4. Database Functions

The DAL will implement functions for all database operations:

#### Transcript Search Operations

```python
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
                    # ... other fields ...
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
        # ... filter logic ...
    
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
            # ... other fields ...
            'similarity': row[13]
        })
    
    return formatted_results

# ... other transcript search functions ...
```

#### Job Management Operations

```python
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

# ... other job management functions ...
```

#### Workflow Operations

```python
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

                conn.commit()
                
                return {
                    "deleted_transcript_rows": deleted_transcript_rows,
                    "deleted_job_transcript_rows": deleted_job_transcript_rows,
                    "cleared_job_rows": cleared_job_rows
                }
                
            except Exception as e:
                conn.rollback()
                raise e

# ... other workflow operations ...
```

### 5. Module Structure

The DAL module will be structured as follows:

```python
# backend/database/manager.py
import psycopg2
from psycopg2.extras import execute_values
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from functools import wraps
import time
import logging
import os
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)

# Maximum number of retries for database operations
MAX_RETRIES = 5
RETRY_DELAY = 1  # seconds

# Error types to retry on
RETRY_ERRORS = (
    psycopg2.OperationalError,
    psycopg2.InterfaceError,
    psycopg2.InternalError
)

class DatabaseManager:
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
        # ... connection pool creation logic ...
        
    def _create_write_pool(self):
        """Create a write connection pool"""
        # ... connection pool creation logic ...
    
    @contextmanager
    def get_read_conn(self):
        """Context manager for getting a read-only connection"""
        # ... connection management logic ...
    
    @contextmanager
    def get_write_conn(self):
        """Context manager for getting a write connection"""
        # ... connection management logic ...
    
    def close_pools(self):
        """Close all connection pools"""
        if self._read_pool:
            self._read_pool.closeall()
        if self._write_pool:
            self._write_pool.closeall()
    
    # Transcript search operations
    def add_transcripts_batch_db(self, transcripts, embeddings):
        """Batch insert multiple transcripts with their embeddings"""
        # ... implementation ...
    
    def hybrid_search_db(self, search_text, search_embedding, filters=None, semantic_weight=0.5, limit=10):
        """Perform hybrid search"""
        # ... implementation ...
    
    # Job management operations
    def create_job_db(self, url, user_email, status='pending'):
        """Create a new ingest job"""
        # ... implementation ...
    
    # Workflow operations
    def update_workflow_state_db(self, job_id, state, error_message=None):
        """Update job workflow state"""
        # ... implementation ...
    
    # ... other database operations ...
```

## Changes to Existing Modules

### 1. TranscriptSearch

```python
# backend/transcript_search.py
from backend.database.manager import DatabaseManager

class TranscriptSearch:
    def __init__(self):
        """Initialize required extensions"""
        # Initialize database manager
        self.dal = DatabaseManager()
        
        # Initialize models as None for lazy loading
        self._nlp = None
        self._model = None
        self._filter_values = None
        
        # Initialize filter values
        self._filter_values = self.get_available_filters()
    
    # ... NLP and embedding methods remain unchanged ...
    
    def add_transcript(self, segment_hash, text, title, date, youtube_id, source, speaker, company=None, start_time=None, end_time=None, duration=None, subjects=None, download=None):
        """Add a single transcript entry with all its metadata"""
        # Generate embedding using quantized model
        embedding = self.encode_text(text)
        
        # Use DAL to add transcript
        self.dal.add_transcript_db(
            segment_hash, title, date, youtube_id, source, speaker, company,
            start_time, end_time, duration, subjects, download, text, embedding
        )
    
    def add_transcripts_batch(self, transcripts):
        """Batch insert multiple transcripts"""
        # Generate embeddings for all texts
        texts = [t['text'] for t in transcripts]
        embeddings = self.encode_text(texts)
        
        # Use DAL to add transcripts
        self.dal.add_transcripts_batch_db(transcripts, embeddings)
    
    def hybrid_search(self, search_text, filters=None, semantic_weight=0.5, limit=10):
        """Perform hybrid search"""
        # Generate embedding for semantic search
        search_embedding = self.encode_text(search_text)
        
        # Use DAL to perform search
        return self.dal.hybrid_search_db(search_text, search_embedding, filters, semantic_weight, limit)
    
    def get_metadata_by_hash(self, segment_hash):
        """Get metadata for a specific segment by its hash"""
        return self.dal.get_metadata_by_hash_db(segment_hash)
    
    def get_available_filters(self):
        """Returns the stored filter values"""
        try:
            self._filter_values = self.dal.get_available_filters_db()
            return self._filter_values
        except Exception as e:
            logger.error(f"Error fetching filter values: {str(e)}")
            # If we have cached values, return those instead of failing
            if self._filter_values is not None:
                logger.info("Returning cached filter values due to database error")
                return self._filter_values
            raise
    
    @classmethod
    def close_pool(cls):
        """Close the connection pool"""
        DatabaseManager().close_pools()
        logger.info("Database connection pools closed")
```

### 2. WorkflowProcessor

```python
# backend/workflow_processor.py
from backend.database.manager import DatabaseManager

class WorkflowProcessor:
    def __init__(self):
        self.job_manager = JobManager()
        self.r2_manager = R2Manager()
        self.dal = DatabaseManager()

    async def update_workflow_state(self, job_id, state, error_message=None):
        """Update job workflow state and map to job status"""
        logger.info(f"Updating workflow state for job {job_id} to '{state}'")
        status = None
        if state == 'failed':
            status = JobStatus.FAILED
            logger.error(f"Job {job_id} failed: {error_message}")
        elif state == 'completed':
            status = JobStatus.COMPLETED
            logger.info(f"Job {job_id} completed successfully")
        elif state == 'editing_metadata':
            status = JobStatus.WAITING
            logger.info(f"Job {job_id} awaiting metadata review")
        elif state == 'deleted':
            status = JobStatus.DELETED
            logger.info(f"Job {job_id} deleted")
        elif state in ('fetching_html', 'html_fetched', 'fetching_video', 'video_fetched', 'generating_clips'):
            status = JobStatus.RUNNING
            logger.info(f"Job {job_id} running: {state}")

        try:
            # Update workflow state in database
            prev_state = self.dal.update_workflow_state_db(job_id, state, error_message)
            logger.info(f"Job {job_id} state transition: {prev_state or 'None'} -> {state}")

            # Update job status if needed
            if status:
                logger.info(f"Updating job {job_id} status to {status}")
                await self.job_manager.update_job_status(job_id, status, error_message)
                
        except Exception as e:
            error_msg = f"Failed to update workflow state for job {job_id}: {str(e)}"
            logger.error(error_msg)
            raise

    async def delete_content(self, job_id):
        """Delete all content related to a job including cache files and database entries"""
        # Get job info
        job = self.job_manager.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Setup job-specific logging
        from backend.ingest.logging_setup import setup_logging, cleanup_logging
        db_handler = setup_logging(job_id)
        start_time = datetime.now()

        try:
            logger.info(f"Starting content deletion for job {job_id}")
            logger.info(f"Job details: ID={job_id}, URL={job.url}, user={job.user_email}")
            
            # Get youtube_id from metadata
            job_details = self.dal.get_job_details_db(job_id)
            youtube_id = job_details.get("metadata", {}).get("youtube_id", "Unknown")
            logger.info(f"Retrieved youtube_id: {youtube_id}")

            # Delete clips from R2
            r2_start = datetime.now()
            logger.info(f"Beginning R2 clip deletion for youtube_id: {youtube_id}")
            deleted_clips = self.r2_manager.delete_files_by_prefix(youtube_id)
            r2_duration = (datetime.now() - r2_start).total_seconds()
            logger.info(f"R2 deletion completed in {r2_duration:.2f} seconds: {deleted_clips} clips deleted")

            # Delete database entries
            logger.info("Beginning database cleanup phase")
            db_start = datetime.now()
            
            result = self.dal.delete_job_content_db(job_id, youtube_id)
            
            db_duration = (datetime.now() - db_start).total_seconds()
            logger.info(f"Database cleanup completed in {db_duration:.2f} seconds")

            # Update workflow state and job status to deleted
            logger.info(f"Updating job {job_id} to {WorkflowState.DELETED} state")
            await self.update_workflow_state(job_id, WorkflowState.DELETED)
            
            # Log completion summary
            total_duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"""Content deletion completed successfully in {total_duration:.2f} seconds:
                - Deleted {deleted_clips} R2 clips
                - Deleted {result['deleted_transcript_rows']} transcript entries
                - Deleted {result['deleted_job_transcript_rows']} job transcript entries
                - Cleared data from {result['cleared_job_rows']} ingest job rows""")
                
        except Exception as e:
            error_msg = f"Failed to delete content: {str(e)}"
            logger.error(error_msg)
            raise
        finally:
            if db_handler:
                cleanup_logging(db_handler)

    # ... other methods ...
```

### 3. JobManager

```python
# backend/job_manager.py
from backend.database.manager import DatabaseManager

class JobManager:
    def __init__(self):
        load_dotenv()
        self.dal = DatabaseManager()
        
        # Email settings
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("FROM_EMAIL")

    async def create_job(self, url, user_email):
        """Create a new ingest job"""
        row = self.dal.create_job_db(url, user_email, JobStatus.PENDING)
        
        return Job(
            id=row[0],
            url=row[1],
            status=row[2],
            created_at=row[3],
            started_at=row[4],
            completed_at=row[5],
            error_message=row[6],
            user_email=row[7],
            detailed_workflow_state=row[8]
        )

    def get_job(self, job_id):
        """Get job by ID"""
        row = self.dal.get_job_db(job_id)
        if not row:
            return None
        
        return Job(
            id=row[0],
            url=row[1],
            status=row[2],
            created_at=row[3],
            started_at=row[4],
            completed_at=row[5],
            error_message=row[6],
            user_email=row[7],
            detailed_workflow_state=row[8]
        )

    def list_jobs(self, user_email=None, limit=100):
        """List jobs with optional filtering by user"""
        rows = self.dal.list_jobs_db(user_email, limit)
        
        return [
            Job(
                id=row[0],
                url=row[1],
                status=row[2],
                created_at=row[3],
                started_at=row[4],
                completed_at=row[5],
                error_message=row[6],
                user_email=row[7],
                detailed_workflow_state=row[8]
            )
            for row in rows
        ]

    async def update_job_status(self, job_id, status, error_message=None):
        """Update job status and timestamps"""
        self.dal.update_job_status_db(job_id, status, error_message)

    def get_job_log(self, job_id):
        """Get the log file content for a job"""
        return self.dal.get_job_log_db(job_id)

    def update_log_file(self, job_id, log_content):
        """Update the log file content for a job"""
        self.dal.update_log_file_db(job_id, log_content)

    # Email functionality remains unchanged
    def send_email(self, to_email, subject, body):
        """Send email notification"""
        # ... implementation ...
```

## Benefits of the DAL Approach

1. **Simplified Code**: Each module focuses on its core responsibility without database-specific code.
2. **Improved Maintainability**: Database changes only need to be made in one place.
3. **Better Performance**: Separate read and write pools reduce contention.
4. **Enhanced Encapsulation**: Database details are hidden from business logic.
5. **Consistent Error Handling**: Retry logic is centralized and standardized.
6. **Clearer Responsibilities**: Each module has a well-defined role.
7. **Easier Testing**: Database operations can be mocked more easily.
8. **Optimized Connection Management**: Pools are sized appropriately for their workload.

## Implementation Steps

1. Create the `backend/database` directory
2. Implement the `backend/database/manager.py` module
3. Refactor `transcript_search.py` to use the DAL
4. Refactor `workflow_processor.py` to use the DAL
5. Refactor `job_manager.py` to use the DAL
6. Update `main.py` to initialize and close the DAL
7. Test the refactored code
