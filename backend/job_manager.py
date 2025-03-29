from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, EmailStr, Field
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import logging
from backend.database.manager import DatabaseManager
from backend.models import JobStatus

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
        self.dal = DatabaseManager()
        
        # Email settings
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("FROM_EMAIL")

    async def create_job(self, url: str, user_email: str) -> Job:
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

    def get_job(self, job_id: int) -> Optional[Job]:
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

    def list_jobs(self, user_email: Optional[str] = None, limit: int = 100) -> List[Job]:
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

    async def update_job_status(self, job_id: int, status: JobStatus, error_message: Optional[str] = None):
        """Update job status and timestamps"""
        self.dal.update_job_status_db(job_id, status, error_message)

    def get_job_log(self, job_id: int) -> str:
        """Get the log file content for a job"""
        return self.dal.get_job_log_db(job_id)

    def update_log_file(self, job_id: int, log_content: str):
        """Update the log file content for a job"""
        self.dal.update_log_file_db(job_id, log_content)

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
