import asyncio
import json
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
