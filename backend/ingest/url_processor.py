import json
import traceback
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Removed unused imports: List, Dict, Any, TranscriptSegment, parse_transcript, parse_raw_html
from .logging_setup import logger
from .models import Transcript
from .html_extractor import HtmlExtractor
from backend.transcript_search import TranscriptSearch
from backend.database.manager import DatabaseManager
from backend.video_utils import is_youtube_url, extract_youtube_id
from backend.youtube_transcript_maker import get_youtube_transcript

class UrlProcessor:
    """Handles URL processing and transcript extraction"""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.html_extractor = HtmlExtractor()
        self.search = TranscriptSearch()
        self.db_manager = DatabaseManager()

    def get_cached_url(self, url: str) -> Tuple[Path, Path]:
        """Get paths for cached files"""
        base_name = url.replace('://', '_').replace('/', '_')
        return (
            self.cache_dir / f"{base_name}.html",
            self.cache_dir / f"{base_name}.json",
        )

    async def process_url(self, url: str, job_id: Optional[int] = None) -> Optional[Transcript]:
        """
        Process URL and extract transcript information.
        Processes YouTube URLs to extract metadata and raw transcript.
        """
        start_time = datetime.now()
        db_handler = None
        workflow_processor = None # Initialize workflow_processor

        try:
            # Import at runtime to avoid circular dependency
            from backend.workflow_processor import WorkflowProcessor
            workflow_processor = WorkflowProcessor()

            # Setup job-specific logging if job_id is provided
            if job_id is not None:
                from .logging_setup import setup_logging
                db_handler = setup_logging(job_id)
                logger.info(f"Starting URL processing for job {job_id}")
                logger.info(f"Target URL: {url}")

            # --- Start of Added Validation ---
            if not is_youtube_url(url):
                error_msg = f"Invalid URL: Only YouTube URLs are supported. Received: {url}"
                logger.error(error_msg)
                if job_id and workflow_processor:
                    await workflow_processor.update_workflow_state(job_id, 'failed', error_msg)
                return None # Or raise an exception

            youtube_id = extract_youtube_id(url)
            if not youtube_id:
                error_msg = f"Failed to extract YouTube ID from URL: {url}"
                logger.error(error_msg)
                if job_id and workflow_processor:
                    await workflow_processor.update_workflow_state(job_id, 'failed', error_msg)
                return None
            # --- End of Added Validation ---

            logger.info(f"Detected YouTube URL: {url}")
            logger.info(f"Extracted YouTube ID: {youtube_id}")

            # Update workflow state if job_id is provided (moved after validation)
            if job_id:
                # State update moved here, ensures it happens only for valid YT URLs
                await workflow_processor.update_workflow_state(job_id, 'fetching_html')
                logger.info("Beginning YouTube transcript fetch phase")

            # Directly call the YouTube processing method
            return await self._process_youtube_url(url, youtube_id, job_id, workflow_processor)

        except Exception as e:
            error_msg = f"Error processing URL {url}: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            # Ensure workflow_processor is available for state update
            if job_id and workflow_processor:
                await workflow_processor.update_workflow_state(job_id, 'failed', error_msg)
            return None
        finally:
            # Clean up logging
            if db_handler:
                from .logging_setup import cleanup_logging
                cleanup_logging(db_handler)

    async def _process_youtube_url(self, url: str, youtube_id: str, job_id: Optional[int], workflow_processor) -> Optional[Transcript]:
        """Process a YouTube URL using direct transcript fetching"""
        # Removed redundant state update from here, it's now in process_url
        try:
            # Fetch HTML content for metadata (title, date)
            html_fetch_start = datetime.now()
            logger.info(f"Fetching HTML to extract metadata from {url}")
            html_content = await self.html_extractor.fetch_html(url)
            html_fetch_duration = (datetime.now() - html_fetch_start).total_seconds()
            logger.info(f"HTML fetch completed in {html_fetch_duration:.2f} seconds")
            
            # Update database
            if job_id:
                with self.db_manager.get_write_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute('''
                            UPDATE ingest_jobs 
                            SET html_fetched_at = CURRENT_TIMESTAMP,
                                html_fetch_success = true
                            WHERE id = %s
                        ''', (job_id,))
                        conn.commit()
                await workflow_processor.update_workflow_state(job_id, 'html_fetched')
                logger.info("HTML fetch phase completed successfully")
            
            # Extract metadata from HTML
            logger.info("Extracting metadata from YouTube page")
            title, date, _ = self.html_extractor.extract_metadata(html_content, url)
            
            # Use title from YouTube if available, otherwise use a default
            if not title:
                title = f"YouTube Video {youtube_id}"
                logger.info(f"Using default title: {title}")
            else:
                logger.info(f"Using title from YouTube page: {title}")
            
            # Use current date if not available
            if not date:
                date = datetime.now().strftime("%Y-%m-%d")
                logger.info(f"Using current date: {date}")
            else:
                logger.info(f"Using date from YouTube page: {date}")
            
            # Fetch transcript directly from YouTube
            logger.info(f"Fetching transcript for YouTube ID: {youtube_id}")
            transcript_start = datetime.now()
            transcript_text = get_youtube_transcript(str(self.cache_dir), youtube_id)
            
            if not transcript_text:
                logger.error("Failed to fetch YouTube transcript")
                transcript_text = ""
            else:
                transcript_lines = len(transcript_text.split('\n'))
                transcript_chars = len(transcript_text)
                logger.info(f"Successfully fetched YouTube transcript: {transcript_lines} lines, {transcript_chars} characters")
            
            transcript_duration = (datetime.now() - transcript_start).total_seconds()
            logger.info(f"YouTube transcript fetch completed in {transcript_duration:.2f} seconds")
                      
            # Create transcript object
            transcript_obj = Transcript(
                metadata={
                    "title": title,
                    "date": date,
                    "youtube_id": youtube_id,
                    "source_url": url
                },
                raw_transcript=transcript_text,
                transcript=[]
            )
            
            # Store in database
            if job_id:
                logger.info("Storing YouTube transcript in database")
                store_start = datetime.now()
                parsing_status = {"success": True, "error": ""}
                
                with self.db_manager.get_write_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute('''
                            UPDATE ingest_jobs 
                            SET raw_transcript = %s,
                                metadata = %s,
                                parsing_status = %s
                            WHERE id = %s
                        ''', (transcript_obj.raw_transcript, json.dumps(transcript_obj.metadata), json.dumps(parsing_status), job_id))
                        conn.commit()
                store_duration = (datetime.now() - store_start).total_seconds()
                logger.info(f"Database storage completed in {store_duration:.2f} seconds")
            
            # Note: We intentionally avoid setting the state to editing_metadata here
            # to prevent the UI from stopping progress updates when auto_approve is enabled.
            # State transitions are centrally managed in tasks.py instead.

            return transcript_obj

        except Exception as e:
            error_msg = f"Error processing YouTube URL {url}: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            if job_id and workflow_processor: # Check if workflow_processor exists
                await workflow_processor.update_workflow_state(job_id, 'failed', error_msg)
            return None

    # --- _process_regular_url method removed ---
