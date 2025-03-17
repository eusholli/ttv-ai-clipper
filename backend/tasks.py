import asyncio
import json
import traceback
from dataclasses import asdict
from celery import Celery
from backend.ingest.video_processor import VideoProcessor
from backend.ingest.constants import CACHE_DIR, CLIP_DIR
from backend.workflow_processor import WorkflowProcessor
from backend.ingest.transcript_db_manager import TranscriptDbManager
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Initialize and configure Celery
celery = Celery('tasks')
celery.config_from_object('backend.celeryconfig')

# Configure logging for Celery tasks
celery.conf.worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
celery.conf.worker_task_log_format = (
    '[%(asctime)s: %(levelname)s/%(processName)s] '
    '[%(task_name)s(%(task_id)s)] %(message)s'
)

@celery.task(bind=True, name='tasks.process_url')
def process_url_task(self, url: str, job_id: int, auto_approve: bool = False):
    """
    Celery task for processing URLs and extracting transcripts.
    
    Args:
        self: Task instance (injected by Celery)
        url: URL to process
        job_id: Job identifier
        auto_approve: Whether to auto-process transcript if parsing is successful
    """
    from backend.ingest.url_processor import UrlProcessor
    
    processor = UrlProcessor(CACHE_DIR)
    workflow_processor = WorkflowProcessor()
    
    try:
        logger.info(f"Starting URL processing for job {job_id}")
        
        # Create and setup event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Process URL and get result
            result = loop.run_until_complete(processor.process_url(url, job_id))
        finally:
            loop.close()
            
        if not result:
            raise Exception("Failed to process URL")
            
        # Update workflow state to editing_metadata if not already done
        # (process_url might have already updated the state)
        db_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(db_loop)
        try:
            # Check current state
            with workflow_processor.get_read_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute('SELECT workflow_state FROM ingest_jobs WHERE id = %s', (job_id,))
                    result = cur.fetchone()
                    current_state = result[0] if result else None
            
            # Only update if not already in editing_metadata or completed state
            if current_state not in ('editing_metadata', 'completed'):
                # Note: This is where we centrally manage state transitions
                # For non-auto-approve jobs, we set to editing_metadata
                # For auto-approve jobs with successful parsing, we'll proceed to video processing
                if not auto_approve:
                    logger.info(f"Standard workflow for job {job_id}, transitioning to editing_metadata")
                    db_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'editing_metadata'))
                
            # Check if we should auto-process the transcript
            if auto_approve:
                logger.info(f"Auto-approve enabled for job {job_id}, checking parsing status")
                try:
                    # Get the current parsing status
                    with workflow_processor.get_read_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute('''
                                SELECT parsing_status
                                FROM ingest_jobs 
                                WHERE id = %s
                            ''', (job_id,))
                            result = cur.fetchone()
                            parsing_status = result[0] if result else None

                    if parsing_status and parsing_status.get('success', False):
                        logger.info(f"Parsing successful, bypassing editing_metadata state and proceeding to video processing")
                        # First update the workflow state to fetching_video to ensure UI updates
                        db_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'fetching_video'))
                        # Then start the video processing task
                        db_loop.run_until_complete(workflow_processor.process_transcript(job_id))
                    else:
                        logger.info(f"Parsing failed or not ready, requiring manual review for job {job_id}")
                        # Set to editing_metadata for manual review
                        if current_state not in ('editing_metadata', 'completed'):
                            db_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'editing_metadata'))
                except Exception as e:
                    logger.error(f"Error checking parsing status: {str(e)}")
                    # Default to editing_metadata for safety
                    if current_state not in ('editing_metadata', 'completed'):
                        db_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'editing_metadata'))
        finally:
            db_loop.close()
            
        return {"success": True, "job_id": job_id}
        
    except Exception as e:
        error_msg = f"Error in URL processing task: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        
        # Update workflow state to failed
        error_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(error_loop)
        try:
            error_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'failed', error_msg))
        finally:
            error_loop.close()
            
        raise


@celery.task(bind=True, name='tasks.process_video')
def process_video_task(self, info: dict, job_id: int):
    """
    Celery task for processing video content.
    
    Args:
        self: Task instance (injected by Celery)
        info: Video information dictionary
        job_id: Job identifier
    """
    processor = VideoProcessor(CACHE_DIR, CLIP_DIR)
    workflow_processor = WorkflowProcessor()
    transcript_db_manager = TranscriptDbManager()
    processor.workflow_processor = workflow_processor
    
    try:
        logger.info(f"Starting video processing for job {job_id}")
        
        # Create and setup event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Process video and get result
            result = loop.run_until_complete(processor.process_video(info, job_id))
            
            # Handle coroutines in transcript metadata if present
            if hasattr(result, 'transcript'):
                for segment in result.transcript:
                    for key, value in segment.metadata.items():
                        if asyncio.iscoroutine(value):
                            logger.info(f"Found coroutine in metadata key {key}")
                            segment.metadata[key] = loop.run_until_complete(value)
        finally:
            loop.close()

        # If we have a valid result with transcript, update the database
        if result and hasattr(result, 'transcript'):
            try:
                # Create new loop for database operations
                db_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(db_loop)
                try:
                    # Update transcripts
                    db_loop.run_until_complete(transcript_db_manager.update_transcripts(result))
                    
                    # Store result in database
                    result_dict = result.model_dump()
                    logger.info(f"Successfully converted result to dict with keys: {result_dict.keys()}")
                    
                    with workflow_processor._write_pool.getconn() as conn:
                        with conn.cursor() as cur:
                            cur.execute('''
                                UPDATE ingest_jobs 
                                SET metadata = %s::jsonb,
                                    raw_transcript = %s
                                WHERE id = %s
                            ''', (json.dumps(result.metadata), result.raw_transcript, job_id))
                            
                            cur.execute('''
                                INSERT INTO job_transcripts (job_id, transcript)
                                VALUES (%s, %s::jsonb)
                                ON CONFLICT (job_id) 
                                DO UPDATE SET transcript = EXCLUDED.transcript
                            ''', (job_id, result.model_dump_json()))
                            
                            conn.commit()
                    
                    # Mark as completed only after all database operations succeed
                    db_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'completed'))
                    return result_dict
                    
                finally:
                    db_loop.close()
                    
            except Exception as db_error:
                error_msg = f"Database operation failed: {str(db_error)}"
                logger.error(error_msg)
                # Create new loop for error state update
                error_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(error_loop)
                try:
                    error_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'failed', error_msg))
                finally:
                    error_loop.close()
                raise
                
    except Exception as e:
        error_msg = f"Error in video processing task: {str(e)}"
        logger.error(error_msg)
        # Create new loop for error state update
        error_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(error_loop)
        try:
            error_loop.run_until_complete(workflow_processor.update_workflow_state(job_id, 'failed', error_msg))
        finally:
            error_loop.close()
        raise
