# backend/workflow_processor.py
from datetime import datetime
from typing import Optional, List, Dict, Any
from backend.models import JobStatus, WorkflowState
from backend.ingest.models import Transcript
from backend.ingest.transcript_parser import parse_transcript
from backend.ingest.content_processor import ContentProcessor
from backend.ingest.constants import CACHE_DIR, CLIP_DIR
from pathlib import Path
import json
import os
import traceback
from backend.database.manager import DatabaseManager
from backend.r2_manager import R2Manager
from backend.job_manager import JobManager
from backend.ingest.logging_setup import setup_logging, cleanup_logging, logger
import psycopg2

class WorkflowProcessor:
    def __init__(self):
        self.job_manager = JobManager()
        self.r2_manager = R2Manager()
        self.dal = DatabaseManager()

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

    async def update_content(self, job_id: int, content: Dict[str, Any]):
        """Update transcript content in ingest_jobs and job_transcripts"""
        try:
            # Use DAL to update content
            updated_transcript = self.dal.update_content_db(job_id, content)
            
            # Parse the transcript
            metadata = updated_transcript["metadata"]
            result = parse_transcript(
                metadata.get('title', ''),
                metadata.get('date', ''),
                metadata.get('youtube_id', ''),
                updated_transcript["raw_transcript"]
            )
            
            # Store parsing status in database
            parsing_status = {
                "success": result["success"],
                "error": result.get("error", "")
            }
            
            self.dal.validate_transcript_db(job_id, parsing_status)
            
            return parsing_status
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error updating content: {error_msg}")
            return {"success": False, "error": error_msg}

    async def delete_content(self, job_id: int) -> None:
        """Delete all content related to a job including cache files and database entries"""
        # Get job info
        job = self.job_manager.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Setup job-specific logging
        db_handler = setup_logging(job_id)
        start_time = datetime.now()

        try:
            logger.info(f"Starting content deletion for job {job_id}")
            logger.info(f"Job details: ID={job_id}, URL={job.url}, user={job.user_email}")
            
            # Get job details to retrieve youtube_id
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
            error_msg = f"Failed to delete content: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            raise
        finally:
            if db_handler:
                cleanup_logging(db_handler)

    async def delete_content_archive(self) -> Dict[str, int]:
        """
        Delete all content (R2 files and DB records) for jobs with status 
        'completed', 'failed', or 'deleted'.
        """
        logger.info("Starting content archive deletion process...")
        start_time = datetime.now()
        
        jobs_to_delete = []
        try:
            # 1. Fetch target jobs from DB
            jobs_to_delete = self.dal.get_archivable_jobs_db()
            if not jobs_to_delete:
                logger.info("No jobs found in 'completed', 'failed', or 'deleted' state. Archive process finished.")
                return {"processed_jobs": 0, "r2_deleted_count": 0, "db_deleted_count": 0, "r2_errors": 0, "db_errors": 0}
            
            logger.info(f"Found {len(jobs_to_delete)} jobs to archive.")
            
        except Exception as e:
            logger.error(f"Failed to fetch archivable jobs: {str(e)}\n{traceback.format_exc()}")
            # If we can't fetch jobs, we can't proceed
            return {"processed_jobs": 0, "r2_deleted_count": 0, "db_deleted_count": 0, "r2_errors": 1, "db_errors": 0} # Indicate error fetching

        # Initialize counters
        processed_count = 0
        total_r2_deleted = 0
        total_db_deleted = 0
        r2_errors = 0
        db_errors = 0

        # 2. Iterate and delete content for each job
        for job_id, youtube_id in jobs_to_delete:
            processed_count += 1
            logger.info(f"Processing job {job_id} (YouTube ID: {youtube_id or 'N/A'}) for archival...")
            
            # 2a. Delete R2 Files (if youtube_id exists)
            r2_deleted_count = 0
            if youtube_id:
                try:
                    logger.info(f"Attempting R2 deletion for prefix: {youtube_id}")
                    r2_deleted_count = self.r2_manager.delete_files_by_prefix(youtube_id)
                    total_r2_deleted += r2_deleted_count
                    logger.info(f"R2 deletion for job {job_id} successful: {r2_deleted_count} files deleted.")
                except Exception as e:
                    r2_errors += 1
                    logger.error(f"R2 deletion failed for job {job_id} (prefix: {youtube_id}): {str(e)}\n{traceback.format_exc()}")
                    # Continue to DB deletion even if R2 fails
            else:
                logger.warning(f"Skipping R2 deletion for job {job_id}: No YouTube ID found.")

            # 2b. Delete Database Records
            try:
                logger.info(f"Attempting database deletion for job {job_id}")
                # Use the modified delete_job_content_db which now deletes the ingest_jobs row too
                db_result = self.dal.delete_job_content_db(job_id, youtube_id) 
                total_db_deleted += db_result.get("deleted_ingest_job_rows", 0) # Count based on ingest_jobs deletion
                logger.info(f"Database deletion for job {job_id} successful. Rows affected: {db_result}")
            except Exception as e:
                db_errors += 1
                logger.error(f"Database deletion failed for job {job_id}: {str(e)}\n{traceback.format_exc()}")
                # Log error but continue processing other jobs

        # 3. Log Summary
        total_duration = (datetime.now() - start_time).total_seconds()
        summary_message = (
            f"Content archive deletion process completed in {total_duration:.2f} seconds.\n"
            f"  - Jobs processed: {processed_count}/{len(jobs_to_delete)}\n"
            f"  - Total R2 files deleted: {total_r2_deleted}\n"
            f"  - Total DB job records deleted: {total_db_deleted}\n"
            f"  - R2 deletion errors: {r2_errors}\n"
            f"  - DB deletion errors: {db_errors}"
        )
        logger.info(summary_message)

        return {
            "processed_jobs": processed_count,
            "r2_deleted_count": total_r2_deleted,
            "db_deleted_count": total_db_deleted,
            "r2_errors": r2_errors,
            "db_errors": db_errors
        }

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
            parsing_status = {
                "success": result["success"],
                "error": result.get("error", "")
            }
            
            self.dal.validate_transcript_db(job_id, parsing_status)

            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error validating content: {error_msg}")
            
            # Store error status in database
            parsing_status = {
                "success": False,
                "error": error_msg
            }
            self.dal.validate_transcript_db(job_id, parsing_status)
            
            return {"success": False, "error": error_msg}

    async def process_transcript(self, job_id: int):
        """Background task for video processing using Celery"""
        try:
            # Get job details from DAL
            job_details = self.dal.get_job_details_db(job_id)
            metadata = job_details.get("metadata", {})
            title = metadata.get('title')
            date = metadata.get('date')
            youtube_id = metadata.get('youtube_id')
            transcript_text = job_details.get("raw_transcript")
            
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
            return self.dal.get_job_details_db(job_id)
        except psycopg2.OperationalError as e:
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
