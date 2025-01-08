from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from pathlib import Path
from backend.ingest_pg import CACHE_DIR
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import logging
from backend.transcript_search import TranscriptSearch
from backend.ingest_pg import process_urls
from backend.models import JobStatus, WorkflowState
from backend.r2_manager import R2Manager

logger = logging.getLogger(__name__)

class Job(BaseModel):
    id: int
    url: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    user_email: EmailStr
    detailed_workflow_state: Optional[str]

class JobManager:
    def __init__(self):
        load_dotenv()
        self.search = TranscriptSearch()
        
        # Email settings
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("FROM_EMAIL")

        # Create jobs table if it doesn't exist
        self.create_schema()

    def create_schema(self):
        """Create the jobs table schema"""
        self.search.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ingest_jobs (
                id SERIAL PRIMARY KEY,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                user_email TEXT NOT NULL,
                detailed_workflow_state TEXT
            );
            
            -- Index for status queries
            CREATE INDEX IF NOT EXISTS idx_jobs_status 
            ON ingest_jobs (status);
            
            -- Index for user email queries
            CREATE INDEX IF NOT EXISTS idx_jobs_user_email 
            ON ingest_jobs (user_email);
        ''')
        self.search.conn.commit()

    async def create_job(self, url: str, user_email: str) -> Job:
        """Create a new ingest job"""
        self.search.cursor.execute('''
            INSERT INTO ingest_jobs (url, status, user_email, detailed_workflow_state)
            VALUES (%s, %s, %s, %s)
            RETURNING id, url, status, created_at, started_at, completed_at, error_message, user_email, detailed_workflow_state
        ''', (url, JobStatus.PENDING, user_email, WorkflowState.PENDING))
        
        self.search.conn.commit()
        row = self.search.cursor.fetchone()
        
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

    def get_job(self, job_id: int) -> Optional[Job]:
        """Get job by ID"""
        self.search.cursor.execute('''
            SELECT id, url, status, created_at, started_at, completed_at, error_message, user_email, detailed_workflow_state
            FROM ingest_jobs
            WHERE id = %s
        ''', (job_id,))
        
        row = self.search.cursor.fetchone()
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

    def list_jobs(self, user_email: Optional[str] = None, limit: int = 100) -> list[Job]:
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
        
        self.search.cursor.execute(query, params)
        
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
            for row in self.search.cursor.fetchall()
        ]

    async def process_job(self, job_id: int):
        """Process a job in the background"""
        from backend.ingest_pg import ContentProcessor, CACHE_DIR, CLIP_DIR
        
        job = self.get_job(job_id)
        if not job or job.status != JobStatus.PENDING:
            return

        try:
            # Initialize processor
            processor = ContentProcessor(CACHE_DIR, CLIP_DIR)
            
            # Process URL with job_id for workflow tracking
            result = await processor.process_url(job.url, job_id)
            
            if not result:
                raise Exception("Failed to process URL")

            # Send success email
            self.send_email(
                job.user_email,
                "Ingest Job Ready for Review",
                f"Your ingest job for URL {job.url} is ready for review. "
                f"You can now edit metadata and transcript before proceeding with video processing."
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Job {job_id} failed: {error_msg}")

            # Update workflow state to failed
            from backend.workflow_manager import WorkflowManager
            workflow_manager = WorkflowManager()
            await workflow_manager.update_workflow_state(job_id, 'failed', error_msg)

            # Send failure email
            self.send_email(
                job.user_email,
                "Ingest Job Failed",
                f"Your ingest job for URL {job.url} has failed.\nError: {error_msg}"
            )

    async def mark_job_deleted(self, youtube_id: str):
        """Mark all jobs associated with a YouTube ID as deleted"""
        try:
            logger.info(f"Attempting to mark jobs as deleted for YouTube ID: {youtube_id}")
            # First get the job IDs
            self.search.cursor.execute('''
                SELECT id FROM ingest_jobs
                WHERE url LIKE %s
                AND status = %s
            ''', (f'%{youtube_id}%', JobStatus.COMPLETED))
            
            job_ids = [row[0] for row in self.search.cursor.fetchall()]
            
            if job_ids:
                from backend.workflow_manager import WorkflowManager
                workflow_manager = WorkflowManager()
                
                # Update each job's workflow state to completed with deleted status
                for job_id in job_ids:
                    await workflow_manager.update_workflow_state(job_id, 'completed', status_override=JobStatus.DELETED)
                
                logger.info(f"Successfully marked {len(job_ids)} jobs as deleted for YouTube ID: {youtube_id}")
                logger.info(f"Updated job IDs: {job_ids}")
            else:
                logger.warning(f"No completed jobs found to mark as deleted for YouTube ID: {youtube_id}")
                
        except Exception as e:
            logger.error(f"Error marking jobs as deleted: {str(e)}")
            self.search.conn.rollback()
            raise

    def update_log_file(self, job_id: int, log_content: str):
        """Update the log file content for a job"""
        self.search.cursor.execute('''
            UPDATE ingest_jobs 
            SET last_log_file = %s
            WHERE id = %s
        ''', (log_content, job_id))
        self.search.conn.commit()

    def send_email(self, to_email: str, subject: str, body: str):
        """Send email notification"""
        if not all([self.smtp_server, self.smtp_username, self.smtp_password, self.from_email]):
            logger.warning("Email settings not configured, skipping notification")
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = self.from_email
            msg['To'] = to_email
            msg['Subject'] = subject

            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Sent email notification to {to_email}")

        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
