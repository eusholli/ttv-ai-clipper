from datetime import datetime
from typing import Optional, List, Dict, Any
from backend.models import JobStatus, WorkflowState
from backend.transcript_search import TranscriptSearch, with_retry
from backend.r2_manager import R2Manager
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class WorkflowManager:
    def __init__(self):
        # Import at runtime to avoid circular dependency
        from backend.job_manager import JobManager
        self.job_manager = JobManager()
        self.search = TranscriptSearch()
        self.r2_manager = R2Manager()

    @with_retry
    async def update_workflow_state(self, job_id: int, state: str, error_message: Optional[str] = None, status_override: Optional[str] = None):
        """Update job workflow state and status
        
        Args:
            job_id: The ID of the job to update
            state: The workflow state to set
            error_message: Optional error message to set
            status_override: Optional status to override the default status mapping
        """
        with self.search.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    UPDATE ingest_jobs 
                    SET workflow_state = %s,
                        detailed_workflow_state = %s,
                        error_message = COALESCE(%s, error_message),
                        status = CASE 
                            WHEN %s IS NOT NULL THEN %s
                            WHEN %s = 'failed' THEN 'failed'
                            WHEN %s = 'completed' THEN 'completed'
                            WHEN %s = 'editing_metadata' THEN 'waiting'
                            WHEN %s IN ('fetching_html', 'html_fetched',
                                      'fetching_video', 'video_fetched', 'generating_clips') THEN 'running'
                            ELSE 'pending'
                        END,
                        started_at = CASE 
                            WHEN %s IN ('fetching_html', 'html_fetched', 'editing_metadata', 
                                      'fetching_video', 'video_fetched', 'generating_clips') 
                            AND started_at IS NULL THEN CURRENT_TIMESTAMP
                            ELSE started_at
                        END,
                        completed_at = CASE 
                            WHEN %s IN ('completed', 'failed') OR %s IS NOT NULL THEN CURRENT_TIMESTAMP
                            ELSE completed_at
                        END
                    WHERE id = %s
                ''', (state, state, error_message, status_override, status_override, state, state, state, state, state, state, status_override, job_id))
                conn.commit()

    @with_retry
    def get_latest_log(self, job_id: int) -> Optional[str]:
        """Get the latest log file content for a job"""
        with self.search.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT last_log_file FROM ingest_jobs WHERE id = %s',
                    (job_id,)
                )
                result = cur.fetchone()
                return result[0] if result else None

    @with_retry
    async def update_content(self, job_id: int, content: Dict[str, Any]):
        """Update transcript content in ingest_jobs
        
        Args:
            job_id: The ID of the job to update
            content: Dictionary containing metadata and transcript text
        """
        with self.search.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get existing transcript to preserve structure
                cur.execute('SELECT transcript FROM ingest_jobs WHERE id = %s', (job_id,))
                result = cur.fetchone()
                if not result or not result[0]:
                    existing = {}
                else:
                    existing = result[0]

                # Update transcript while preserving structure
                updated = {
                    "metadata": content.get("metadata", existing.get("metadata", {})),
                    "transcript": content.get("transcript", existing.get("transcript", ""))
                }

                # Update in database
                cur.execute('''
                    UPDATE ingest_jobs 
                    SET transcript = %s::jsonb,
                        transcript_edited_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (json.dumps(updated), job_id))
                conn.commit()

    @with_retry
    async def delete_content(self, job_id: int) -> None:
        """Delete all content related to a job including cache files"""
        # Get job info
        job = self.job_manager.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        with self.search.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get job URL and youtube_id from transcript
                cur.execute('''
                    SELECT url, transcript->'metadata'->>'youtube_id' as youtube_id
                    FROM ingest_jobs 
                    WHERE id = %s
                ''', (job_id,))
                result = cur.fetchone()
                if result:
                    url, youtube_id = result
                else:
                    url, youtube_id = None, None

                if youtube_id:
                    # Delete clips from R2
                    clip_pattern = f"{youtube_id}_*.mp4"
                    self.r2_manager.delete_files_by_prefix(youtube_id)

                    # Delete database entries
                    cur.execute(
                        'DELETE FROM transcripts WHERE youtube_id = %s',
                        (youtube_id,)
                    )

                conn.commit()

        # Delete cached files
        if url:
            from backend.ingest_pg import ContentProcessor, CACHE_DIR, CLIP_DIR
            processor = ContentProcessor(CACHE_DIR, CLIP_DIR)
            html_path, json_path = processor.get_cached_url(url)
            
            # Delete HTML file if it exists
            if html_path.exists():
                html_path.unlink()
                
            # Delete JSON file if it exists    
            if json_path.exists():
                json_path.unlink()

        # Update job status to deleted
        await self.update_workflow_state(job_id, 'completed', status_override=JobStatus.DELETED)

    @with_retry
    async def delete_content_archive(self) -> None:
        """Delete all content for completed, failed, or deleted jobs"""
        with self.search.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Find all inactive jobs
                cur.execute('''
                    SELECT id FROM ingest_jobs 
                    WHERE status IN ('completed', 'failed', 'deleted')
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
    def get_job_details(self, job_id: int) -> Dict[str, Any]:
        """Get job details including transcript and workflow state information"""
        with self.search.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT 
                        transcript,
                        status,
                        workflow_state,
                        detailed_workflow_state,
                        html_fetch_success,
                        video_fetch_success,
                        error_message,
                        id
                    FROM ingest_jobs
                    WHERE id = %s
                ''', (job_id,))
                result = cur.fetchone()
                if not result:
                    raise ValueError(f"Job {job_id} not found")
                
                transcript, status, workflow_state, detailed_workflow_state, html_fetch_success, video_fetch_success, error_message, job_id = result
                
                # If transcript is None, use empty structure
                if transcript is None:
                    transcript = {
                        "metadata": {},
                        "entries": []
                    }

                # Merge transcript with job state info to maintain backward compatibility
                response = transcript if isinstance(transcript, dict) else {}
                response["job"] = {
                    "id": job_id,
                    "status": status,
                    "workflow_state": workflow_state,
                    "detailed_workflow_state": detailed_workflow_state,
                    "html_fetch_success": html_fetch_success,
                    "video_fetch_success": video_fetch_success,
                    "error_message": error_message
                }
                
                return response
