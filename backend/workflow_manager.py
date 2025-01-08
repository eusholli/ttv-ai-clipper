from datetime import datetime
from typing import Optional, List, Dict, Any
from backend.models import JobStatus, WorkflowState
from backend.transcript_search import TranscriptSearch
from backend.r2_manager import R2Manager
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)

# Import JobManager at runtime to avoid circular import
from backend.job_manager import JobManager

class WorkflowManager:
    def __init__(self):
        self.job_manager = JobManager()
        self.search = TranscriptSearch()
        self.r2_manager = R2Manager()

    async def update_workflow_state(self, job_id: int, state: str, error_message: Optional[str] = None, status_override: Optional[str] = None):
        """Update job workflow state and status
        
        Args:
            job_id: The ID of the job to update
            state: The workflow state to set
            error_message: Optional error message to set
            status_override: Optional status to override the default status mapping
        """
        self.search.cursor.execute('''
            UPDATE ingest_jobs 
            SET workflow_state = %s,
                detailed_workflow_state = %s,
                error_message = COALESCE(%s, error_message),
                status = CASE 
                    WHEN %s IS NOT NULL THEN %s
                    WHEN %s = 'failed' THEN 'failed'
                    WHEN %s = 'completed' THEN 'completed'
                    WHEN %s IN ('fetching_html', 'html_fetched', 'editing_metadata', 
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
        ''', (state, state, error_message, status_override, status_override, state, state, state, state, state, status_override, job_id))
        self.search.conn.commit()

    def get_latest_log(self, job_id: int) -> Optional[str]:
        """Get the latest log file content for a job"""
        self.search.cursor.execute(
            'SELECT last_log_file FROM ingest_jobs WHERE id = %s',
            (job_id,)
        )
        result = self.search.cursor.fetchone()
        return result[0] if result else None

    async def update_metadata(self, job_id: int, metadata: Dict[str, Any]):
        """Update edited metadata for a job"""
        self.search.cursor.execute('''
            INSERT INTO edited_metadata (job_id, title, date, youtube_id, source)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (job_id) 
            DO UPDATE SET
                title = EXCLUDED.title,
                date = EXCLUDED.date,
                youtube_id = EXCLUDED.youtube_id,
                source = EXCLUDED.source,
                created_at = CURRENT_TIMESTAMP
        ''', (job_id, metadata.get('title'), metadata.get('date'),
              metadata.get('youtube_id'), metadata.get('source')))
        
        self.search.cursor.execute('''
            UPDATE ingest_jobs 
            SET metadata_edited_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (job_id,))
        
        self.search.conn.commit()

    async def update_transcript(self, job_id: int, segments: List[Dict[str, Any]]):
        """Update edited transcript segments for a job"""
        # First delete existing segments for this job
        self.search.cursor.execute(
            'DELETE FROM edited_transcripts WHERE job_id = %s',
            (job_id,)
        )
        
        # Insert new segments
        for segment in segments:
            self.search.cursor.execute('''
                INSERT INTO edited_transcripts 
                (job_id, segment_hash, text, speaker, company, 
                 start_time, end_time, subjects)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (job_id, segment['segment_hash'], segment['text'],
                  segment['speaker'], segment['company'],
                  segment['start_time'], segment['end_time'],
                  segment['subjects']))

        self.search.cursor.execute('''
            UPDATE ingest_jobs 
            SET transcript_edited_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (job_id,))
        
        self.search.conn.commit()

    async def delete_content(self, job_id: int) -> None:
        """Delete all content related to a job including cache files"""
        # Get job info
        job = self.job_manager.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get metadata to find youtube_id and url
        self.search.cursor.execute(
            'SELECT youtube_id FROM edited_metadata WHERE job_id = %s',
            (job_id,)
        )
        result = self.search.cursor.fetchone()
        youtube_id = result[0] if result else None

        # Get job URL
        self.search.cursor.execute(
            'SELECT url FROM ingest_jobs WHERE id = %s',
            (job_id,)
        )
        result = self.search.cursor.fetchone()
        url = result[0] if result else None

        if youtube_id:
            # Delete clips from R2
            clip_pattern = f"{youtube_id}_*.mp4"
            self.r2_manager.delete_files_by_prefix(youtube_id)

            # Delete database entries
            self.search.cursor.execute(
                'DELETE FROM transcripts WHERE youtube_id = %s',
                (youtube_id,)
            )

        # Delete edited content
        self.search.cursor.execute(
            'DELETE FROM edited_transcripts WHERE job_id = %s',
            (job_id,)
        )
        self.search.cursor.execute(
            'DELETE FROM edited_metadata WHERE job_id = %s',
            (job_id,)
        )

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

    async def delete_content_archive(self) -> None:
        """Delete all content for completed, failed, or deleted jobs"""
        # Find all inactive jobs
        self.search.cursor.execute('''
            SELECT id FROM ingest_jobs 
            WHERE status IN ('completed', 'failed', 'deleted')
        ''')
        inactive_jobs = self.search.cursor.fetchall()
        
        # Delete content for each inactive job
        for (job_id,) in inactive_jobs:
            try:
                await self.delete_content(job_id)
            except Exception as e:
                logger.error(f"Failed to delete content for job {job_id}: {str(e)}")
        
        # Delete all deleted jobs
        self.search.cursor.execute(
            'DELETE FROM ingest_jobs WHERE status = %s', [JobStatus.DELETED]
        )
        self.search.conn.commit()


    def get_job_details(self, job_id: int) -> Dict[str, Any]:
        """Get detailed job information including metadata and transcript"""
        job = self.job_manager.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get edited metadata
        self.search.cursor.execute(
            'SELECT * FROM edited_metadata WHERE job_id = %s',
            (job_id,)
        )
        metadata = dict(zip(
            ['id', 'job_id', 'title', 'date', 'youtube_id', 'source', 'created_at'],
            self.search.cursor.fetchone() or [None] * 7
        ))

        # Get edited transcript
        self.search.cursor.execute(
            'SELECT * FROM edited_transcripts WHERE job_id = %s ORDER BY start_time',
            (job_id,)
        )
        transcript = [dict(zip(
            ['id', 'job_id', 'segment_hash', 'text', 'speaker', 'company',
             'start_time', 'end_time', 'subjects', 'created_at'],
            row
        )) for row in self.search.cursor.fetchall()]

        return {
            'job': job,
            'metadata': metadata,
            'transcript': transcript,
            'latest_log': self.get_latest_log(job_id)
        }
