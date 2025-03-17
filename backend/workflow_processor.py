from datetime import datetime
from typing import Optional, List, Dict, Any
from backend.models import JobStatus, WorkflowState
from backend.ingest.models import Transcript
from backend.ingest.transcript_parser import parse_transcript
from backend.ingest.content_processor import ContentProcessor
from backend.ingest.constants import CACHE_DIR, CLIP_DIR
from pathlib import Path
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from backend.transcript_search import TranscriptSearch, with_retry
from backend.r2_manager import R2Manager
from backend.job_manager import JobManager
from backend.ingest.logging_setup import setup_logging, cleanup_logging, logger
import json
import os
import traceback
from contextlib import contextmanager
from dotenv import load_dotenv

# Pool configurations
READ_POOL_CONFIG = {
    'minconn': 10,
    'maxconn': 30
}

WRITE_POOL_CONFIG = {
    'minconn': 5,
    'maxconn': 20
}

# Transaction isolation levels
READ_COMMITTED = "SET TRANSACTION ISOLATION LEVEL READ COMMITTED"
REPEATABLE_READ = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"

def create_readonly_pool():
    """Create a read-only connection pool using optimized configuration"""
    load_dotenv()
    
    # Check for required environment variables
    required_vars = ['DB_NAME', 'DB_USER', 'DB_PWD', 'DB_HOST']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.warning(f"Missing required environment variables: {', '.join(missing_vars)}")
        return None
            
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
            'connect_timeout': 30,  # Set connection timeout to 30 seconds
            'keepalives': 1,  # Enable TCP keepalives
            'keepalives_idle': 10,  # Seconds between TCP keepalives (reduced from 30)
            'keepalives_interval': 5,  # Seconds between keepalive retransmits (reduced from 10)
            'keepalives_count': 10,  # Max number of keepalive retransmits (increased from 5)
            'sslmode': 'require',  # Enforce SSL connection
            'tcp_user_timeout': 10000  # TCP timeout in milliseconds
        }
            
    try:
        # Add read-only option to connection args
        connection_args['options'] = '-c default_transaction_read_only=on'
        
        # Create pool with optimized read configuration
        pool = SimpleConnectionPool(
            **READ_POOL_CONFIG,
            **connection_args
        )
        logger.info("Read-only database connection pool initialized successfully")
        return pool
    except Exception as e:
        logger.error(f"Failed to initialize read-only connection pool: {str(e)}")
        return None

class WorkflowProcessor:
    def __init__(self):
        self.job_manager = JobManager()
        self.r2_manager = R2Manager()
        # Initialize pools
        TranscriptSearch.initialize_pool()
        self._write_pool = TranscriptSearch._pool
        # Try to create read pool, fall back to write pool if not possible
        self._read_pool = create_readonly_pool() or self._write_pool
        if self._read_pool is self._write_pool:
            logger.info("Using single connection pool for both reads and writes")

    @contextmanager
    def get_read_connection(self):
        """Context manager for getting a read-only connection with proper isolation"""
        conn = None
        try:
            conn = self._read_pool.getconn()
            with conn.cursor() as cur:
                # Set read committed isolation level for consistent reads
                cur.execute(READ_COMMITTED)
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
    def get_write_connection(self):
        """Context manager for getting a write connection with proper isolation"""
        conn = None
        try:
            conn = self._write_pool.getconn()
            with conn.cursor() as cur:
                # Set repeatable read isolation level for write operations
                cur.execute(REPEATABLE_READ)
                # Set longer timeout for write operations
                cur.execute('SET LOCAL statement_timeout = 30000')  # 30 seconds
            yield conn
        except Exception as e:
            logger.error(f"Database write connection error: {str(e)}")
            raise
        finally:
            if conn is not None:
                self._write_pool.putconn(conn)

    @contextmanager
    def get_db_connection(self):
        """Context manager for getting a database connection for writing"""
        with self.get_write_connection() as conn:
            yield conn

    async def update_workflow_state(self, job_id: int, state: str, error_message: Optional[str] = None):
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
            with self.get_write_connection() as conn:
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
                    
                    logger.info(f"Job {job_id} state transition: {prev_state or 'None'} -> {state}")

            # Update job status if needed
            if status:
                logger.info(f"Updating job {job_id} status to {status}")
                await self.job_manager.update_job_status(job_id, status, error_message)
                
        except Exception as e:
            error_msg = f"Failed to update workflow state for job {job_id}: {str(e)}"
            logger.error(error_msg)
            raise

    @with_retry
    async def process_job(self, job_id: int, auto_approve: bool = False):
        """Process a job in the background"""
        start_time = datetime.now()
        
        job = self.job_manager.get_job(job_id)
        if not job or job.status != JobStatus.PENDING:
            logger.info(f"Skipping job {job_id}: {'not found' if not job else 'not in PENDING state'}")
            return

        try:
            logger.info(f"Starting background processing for job {job_id}")
            logger.info(f"Job details: URL={job.url}, user={job.user_email}")
            
            # Update job status to RUNNING
            await self.job_manager.update_job_status(job_id, JobStatus.RUNNING)
            await self.update_workflow_state(job_id, 'fetching_html')
            
            # Submit URL processing to Celery
            logger.info(f"Submitting URL processing task for job {job_id} to Celery")
            from backend.tasks import process_url_task
            process_url_task.delay(job.url, job_id, auto_approve)
            
            # Note: We don't await completion here as Celery handles it asynchronously
            # The task will update the workflow state when it completes
            logger.info(f"URL processing task submitted to Celery queue")

            # Get log content for email
            logger.info("Retrieving job log for email notification")
            log_content = self.job_manager.get_job_log(job_id)

            # Set email subject and message based on auto_approve
            if auto_approve:
                email_subject = "Ingest Job Processing"
                email_message = f"Your ingest job for URL {job.url} is being processed with auto-approve enabled.\n\n"
            else:
                email_subject = "Ingest Job Ready for Review"
                email_message = f"Your ingest job for URL {job.url} is ready for review.\n\n"

            # Send email notification
            logger.info(f"Sending notification email to {job.user_email}")
            self.job_manager.send_email(
                job.user_email,
                email_subject,
                email_message +
                f"You can review and edit it at: http://localhost:3000/admin/ingest\n\n"
                f"Processing Log:\n{log_content}"
            )
            
            total_duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Job {job_id} processing completed successfully in {total_duration:.2f} seconds")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Job {job_id} failed: {error_msg}")
            logger.error(f"Stack trace:\n{traceback.format_exc()}")

            # Update workflow state to failed
            logger.info(f"Updating job {job_id} to failed state")
            await self.update_workflow_state(job_id, 'failed', error_msg)

            # Get log content for failure email
            logger.info("Retrieving job log for failure email notification")
            log_content = self.job_manager.get_job_log(job_id)

            # Send failure email
            logger.info(f"Sending failure notification email to {job.user_email}")
            self.job_manager.send_email(
                job.user_email,
                "Ingest Job Failed",
                f"Your ingest job for URL {job.url} has failed.\n\n"
                f"Error: {error_msg}\n\n"
                f"Processing Log:\n{log_content}"
            )
            
            total_duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Job {job_id} failed after {total_duration:.2f} seconds")

    @with_retry
    async def update_content(self, job_id: int, content: Dict[str, Any]):
        """Update transcript content in ingest_jobs and job_transcripts"""
        try:
            # Get existing data to preserve structure
            with self.get_read_connection() as conn:
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

            # Create new transcript object with updated content using Pydantic
            updated = Transcript.model_validate({
                "metadata": content.get("metadata", existing_metadata),
                "raw_transcript": content.get("raw_transcript", existing_raw),
                "transcript": content.get("transcript", existing_transcript.get("transcript", []))
            })

            # Update in database
            with self.get_write_connection() as conn:
                with conn.cursor() as cur:
                    # Update metadata and raw_transcript in ingest_jobs
                    cur.execute('''
                        UPDATE ingest_jobs 
                        SET metadata = %s::jsonb,
                            raw_transcript = %s,
                            transcript_edited_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    ''', (json.dumps(updated.metadata), updated.raw_transcript, job_id))

                    # Update or insert full transcript in job_transcripts
                    cur.execute('''
                        INSERT INTO job_transcripts (job_id, transcript)
                        VALUES (%s, %s::jsonb)
                        ON CONFLICT (job_id) 
                        DO UPDATE SET transcript = EXCLUDED.transcript
                    ''', (job_id, updated.model_dump_json()))
                    
                    conn.commit()

            # Parse the transcript
            metadata = updated.metadata
            result = parse_transcript(
                metadata.get('title', ''),
                metadata.get('date', ''),
                metadata.get('youtube_id', ''),
                updated.raw_transcript
            )
            
            # Store parsing status in database
            parsing_status = {
                "success": result["success"],
                "error": result.get("error", "")
            }
            
            with self.get_write_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        UPDATE ingest_jobs 
                        SET parsing_status = %s::jsonb
                        WHERE id = %s
                    ''', (json.dumps(parsing_status), job_id))
                    conn.commit()
            
            return parsing_status
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error updating content: {error_msg}")
            return {"success": False, "error": error_msg}

    @with_retry
    async def delete_content(self, job_id: int) -> None:
        """Delete all content related to a job including cache files and database entries"""
        # Refresh connection pool before deletion to ensure fresh connections
        self._write_pool = TranscriptSearch._pool
        
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
            
            with self.get_write_connection() as conn:
                with conn.cursor() as cur:
                    # Get youtube_id from metadata
                    logger.info("Retrieving job metadata")
                    cur.execute('''
                        SELECT metadata->>'youtube_id' as youtube_id
                        FROM ingest_jobs 
                        WHERE id = %s
                        FOR UPDATE
                    ''', (job_id,))
                    result = cur.fetchone()
                    
                    # Set youtube_id to "Unknown" if undefined, null or empty
                    youtube_id = result[0] if result and result[0] else "Unknown"
                    logger.info(f"Retrieved youtube_id: {youtube_id}")

                    # Delete clips from R2
                    # logger.info(f"While Testing Keep R2 clips for youtube_id: {youtube_id}")
                    r2_start = datetime.now()
                    deleted_clips = 0
                    
                    logger.info(f"Beginning R2 clip deletion for youtube_id: {youtube_id}")
                    deleted_clips = self.r2_manager.delete_files_by_prefix(youtube_id)
                    r2_duration = (datetime.now() - r2_start).total_seconds()
                    logger.info(f"R2 deletion completed in {r2_duration:.2f} seconds: {deleted_clips} clips deleted")

                    # Delete database entries
                    logger.info("Beginning database cleanup phase")
                    db_start = datetime.now()

                    # Delete from transcripts table
                    logger.info("Deleting transcript entries")
                    cur.execute(
                        'DELETE FROM transcripts WHERE youtube_id = %s',
                        (youtube_id,)
                    )
                    deleted_transcript_rows = cur.rowcount
                    logger.info(f"Deleted {deleted_transcript_rows} transcript entries")

                    # Delete from job_transcripts
                    logger.info("Deleting job transcript data")
                    cur.execute(
                        'DELETE FROM job_transcripts WHERE job_id = %s',
                        (job_id,)
                    )
                    deleted_job_transcript_rows = cur.rowcount
                    logger.info(f"Deleted {deleted_job_transcript_rows} job transcript entries")

                    # Clear all related columns in ingest_jobs except state-related and user columns
                    logger.info("Clearing job metadata and transcript data")
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
                    logger.info(f"Cleared data from {cleared_job_rows} ingest job rows")

                    db_duration = (datetime.now() - db_start).total_seconds()
                    logger.info(f"Database cleanup completed in {db_duration:.2f} seconds")

                    conn.commit()

                    # Update workflow state and job status to deleted
                    logger.info(f"Updating job {job_id} to {WorkflowState.DELETED} state")
                    await self.update_workflow_state(job_id, WorkflowState.DELETED)
                    
                    # Log completion summary
                    total_duration = (datetime.now() - start_time).total_seconds()
                    logger.info(f"""Content deletion completed successfully in {total_duration:.2f} seconds:
                        - Deleted {deleted_clips} R2 clips
                        - Deleted {deleted_transcript_rows} transcript entries
                        - Deleted {deleted_job_transcript_rows} job transcript entries
                        - Cleared data from {cleared_job_rows} ingest job rows""")
                        
        except Exception as e:
            error_msg = f"Failed to delete content: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            raise
        finally:
            if db_handler:
                cleanup_logging(db_handler)

    @with_retry
    async def delete_content_archive(self) -> None:
        """Delete all content for completed, failed, or deleted jobs"""
        with self.get_write_connection() as conn:
            with conn.cursor() as cur:
                # Find all inactive jobs
                cur.execute('''
                    SELECT id FROM ingest_jobs 
                    WHERE status IN ('completed', 'failed')
                    FOR UPDATE
                ''')
                inactive_jobs = cur.fetchall()
                
                # Delete content for each inactive job
                for (job_id,) in inactive_jobs:
                    try:
                        await self.delete_content(job_id)
                    except Exception as e:
                        logger.error(f"Failed to delete content for job {job_id}: {str(e)}")
                
                # Delete all deleted jobs
                cur.execute(
                    'DELETE FROM ingest_jobs WHERE status = %s', [JobStatus.DELETED]
                )
                conn.commit()

    @with_retry
    async def validate_transcript(self, content: Dict[str, Any], job_id: int):
        """Validate and parse transcript content"""
        try:
            # Get metadata from the transcript
            metadata = content.get('metadata', {})
            title = metadata.get('title', '')
            date = metadata.get('date', '')
            youtube_id = metadata.get('youtube_id', '')
            transcript_text = content.get('raw_transcript', '')

            # Parse the transcript using parse_transcript
            result = parse_transcript(title, date, youtube_id, transcript_text)
            
            # Store parsing status in database
            with self.get_write_connection() as conn:
                with conn.cursor() as cur:
                    parsing_status = {
                        "success": result["success"],
                        "error": result.get("error", "")
                    }
                    cur.execute('''
                        UPDATE ingest_jobs 
                        SET parsing_status = %s::jsonb
                        WHERE id = %s
                    ''', (json.dumps(parsing_status), job_id))
                    conn.commit()

            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error validating content: {error_msg}")
            
            # Store error status in database
            with self.get_write_connection() as conn:
                with conn.cursor() as cur:
                    parsing_status = {
                        "success": False,
                        "error": error_msg
                    }
                    cur.execute('''
                        UPDATE ingest_jobs 
                        SET parsing_status = %s::jsonb
                        WHERE id = %s
                    ''', (json.dumps(parsing_status), job_id))
                    conn.commit()
            
            return {"success": False, "error": error_msg}

    async def process_transcript(self, job_id: int):
        """Background task for video processing using Celery"""
        try:
            # Get transcript data directly without using get_job_details
            with self.get_read_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('''
                        SELECT metadata->>'title' as title,
                               metadata->>'date' as date,
                               metadata->>'youtube_id' as youtube_id,
                               raw_transcript
                        FROM ingest_jobs 
                        WHERE id = %s
                    ''', (job_id,))
                    result = cur.fetchone()
                    if not result:
                        raise ValueError(f"Job {job_id} not found")
                    
                    title, date, youtube_id, transcript_text = result
            
            # Parse transcript
            parsed_result = parse_transcript(
                title or '',
                date or '',
                youtube_id or '',
                transcript_text or ''
            )
            
            # Update state before video processing
            await self.update_workflow_state(job_id, 'fetching_video')
            
            # Import Celery task
            from backend.tasks import process_video_task
            
            # Convert transcript data using Pydantic model
            transcript_obj = parsed_result["data"]
            transcript_model = Transcript(
                metadata={
                    "title": title,
                    "date": date,
                    "youtube_id": youtube_id,
                    **transcript_obj.metadata
                },
                raw_transcript=transcript_obj.raw_transcript,
                transcript=transcript_obj.transcript
            )
            
            # Submit video processing to Celery with serialized data
            logger.info(f"Submitting video processing task for job {job_id} to Celery")
            process_video_task.delay(transcript_model.model_dump(), job_id)
            
            # Note: We don't await completion here as Celery handles it asynchronously
            # The task will update the workflow state when it completes
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error in background processing: {error_msg}")
            await self.update_workflow_state(job_id, 'failed', error_msg)

    def get_latest_log(self, job_id: int) -> str:
        """Get the latest log content for a job"""
        return self.job_manager.get_job_log(job_id)

    def get_job_details(self, job_id: int) -> Dict[str, Any]:
        """Get job details including metadata and workflow state information"""
        try:
            return self._get_job_details(job_id)
        except psycopg2.OperationalError as e:
            if "SSL" in str(e):
                logger.error(f"SSL connection error for job {job_id}: {str(e)}")
                # Force connection pool refresh on SSL errors
                self._read_pool = create_readonly_pool() or self._write_pool
            else:
                logger.warning(f"Database timeout while fetching job details for job {job_id}: {str(e)}")
            return {
                "metadata": {"title": None, "date": None, "youtube_id": None},
                "raw_transcript": "",
                "job": {
                    "id": job_id,
                    "status": "loading",
                    "workflow_state": "loading",
                    "detailed_workflow_state": "Operation in progress",
                    "html_fetch_success": None,
                    "video_fetch_success": None,
                    "error_message": None,
                    "parsing_status": {"success": False, "error": ""}
                }
            }
        except Exception as e:
            logger.error(f"Error getting job details: {str(e)}")
            raise

    def _get_job_details(self, job_id: int) -> Dict[str, Any]:
        """Internal method to get job details with proper connection handling"""
        try:
            # Get all required fields in a single query
            with self.get_read_connection() as conn:
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

            # Create transcript model with metadata and raw_transcript
            try:
                if metadata:
                    transcript_model = Transcript(
                        metadata=metadata,
                        raw_transcript=raw_transcript or ""
                    )
                else:
                    transcript_model = Transcript()  # Uses default values from model
            except Exception as e:
                logger.error(f"Error creating transcript model: {str(e)}")
                transcript_model = Transcript()  # Fallback to default values

            return {
                "metadata": transcript_model.metadata,
                "raw_transcript": transcript_model.raw_transcript,
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
        except Exception as e:
            logger.error(f"Error getting job details: {str(e)}")
            raise
