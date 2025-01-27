import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from .logging_setup import logger
from .models import Transcript, TranscriptSegment
from .html_extractor import HtmlExtractor
from .transcript_parser import parse_transcript, parse_raw_html
from backend.transcript_search import TranscriptSearch

class UrlProcessor:
    """Handles URL processing and transcript extraction"""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.html_extractor = HtmlExtractor()
        self.search = TranscriptSearch()

    def get_cached_url(self, url: str) -> Tuple[Path, Path]:
        """Get paths for cached files"""
        base_name = url.replace('://', '_').replace('/', '_')
        return (
            self.cache_dir / f"{base_name}.html",
            self.cache_dir / f"{base_name}.json",
        )

    async def process_url(self, url: str, job_id: Optional[int] = None) -> Optional[Transcript]:
        """Process URL and extract transcript information"""
        start_time = datetime.now()
        try:
            # Import at runtime to avoid circular dependency
            from backend.workflow_processor import WorkflowProcessor
            workflow_processor = WorkflowProcessor()
            
            # Setup job-specific logging if job_id is provided
            db_handler = None
            if job_id is not None:
                from .logging_setup import setup_logging, cleanup_logging
                db_handler = setup_logging(job_id)
                logger.info(f"Starting URL processing for job {job_id}")
                logger.info(f"Target URL: {url}")

            # Update workflow state if job_id is provided
            if job_id:
                await workflow_processor.update_workflow_state(job_id, 'fetching_html')
                logger.info("Beginning HTML fetch phase")

            # 1. Fetch HTML content
            html_fetch_start = datetime.now()
            logger.info(f"Initiating HTML content fetch from {url}")
            html_content = await self.html_extractor.fetch_html(url)
            if not html_content:
                logger.error("Failed to fetch HTML content")
                html_content = ""
            html_fetch_duration = (datetime.now() - html_fetch_start).total_seconds()
            logger.info(f"HTML fetch completed in {html_fetch_duration:.2f} seconds")
            logger.info(f"Retrieved {len(html_content)} bytes of HTML content")

            if job_id:
                with self.search.get_db_connection() as conn:
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

            # 2. Extract metadata from HTML
            logger.info("Beginning metadata extraction phase")
            metadata_start = datetime.now()
            title, date, youtube_id = self.html_extractor.extract_metadata(html_content)
            if not title or not youtube_id:
                logger.error("Failed to extract required metadata")
                logger.info(f"Extracted metadata: title='{title or 'Unknown'}', date='{date or 'Unknown'}', youtube_id='{youtube_id or 'Unknown'}'")
                title = title or "Unknown"
                youtube_id = youtube_id or "Unknown"
            else:
                logger.info(f"Successfully extracted metadata: title='{title}', date='{date}', youtube_id='{youtube_id}'")
            metadata_duration = (datetime.now() - metadata_start).total_seconds()
            logger.info(f"Metadata extraction completed in {metadata_duration:.2f} seconds")

            # 3. Extract transcript text
            logger.info("Beginning transcript extraction phase")
            transcript_start = datetime.now()
            transcript_text = self.html_extractor.extract_transcript(html_content)
            if not transcript_text:
                logger.error("Failed to extract transcript text")
                transcript_text = ""
            else:
                transcript_lines = len(transcript_text.split('\n'))
                transcript_chars = len(transcript_text)
                logger.info(f"Successfully extracted transcript: {transcript_lines} lines, {transcript_chars} characters")
            transcript_duration = (datetime.now() - transcript_start).total_seconds()
            logger.info(f"Transcript extraction completed in {transcript_duration:.2f} seconds")

            # 4. Parse transcript using parse_raw_html
            logger.info("Beginning transcript parsing phase")
            parse_start = datetime.now()
            parse_result = parse_raw_html(title, date, youtube_id, transcript_text)
            if not parse_result["success"]:
                logger.error(f"Failed to parse transcript: {parse_result['error']}")
                transcript_obj = Transcript(
                    metadata={
                        "title": title,
                        "date": date,
                        "youtube_id": youtube_id
                    },
                    raw_transcript=transcript_text,
                    transcript=[]
                )
            else:
                transcript_obj = parse_result["data"]
                segments = len(transcript_obj.transcript)
                logger.info(f"Successfully parsed transcript into {segments} segments")
            parse_duration = (datetime.now() - parse_start).total_seconds()
            logger.info(f"Transcript parsing completed in {parse_duration:.2f} seconds")

            # Create Transcript object and store in database
            if job_id:
                logger.info("Creating Transcript object and storing in database")
                store_start = datetime.now()
                parsing_status = {
                    "success": parse_result["success"],
                    "error": parse_result.get("error", "")
                }
                
                # Store in database
                with self.search.get_db_connection() as conn:
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

                # After metadata and transcript are found, transition to editing metadata state
                await workflow_processor.update_workflow_state(job_id, 'editing_metadata')
                logger.info("Transitioned to metadata editing state")

            # Log overall completion
            total_duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"URL processing completed successfully in {total_duration:.2f} seconds")

            # Clean up logging on success
            if db_handler:
                cleanup_logging(db_handler)
            
            # Return the Transcript object directly
            return transcript_obj

        except Exception as e:
            error_msg = f"Error processing {url}: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            if job_id:
                # Import at runtime to avoid circular dependency
                from backend.workflow_processor import WorkflowProcessor
                workflow_processor = WorkflowProcessor()
                await workflow_processor.update_workflow_state(job_id, 'failed', error_msg)
                
                # Clean up logging
                if db_handler:
                    cleanup_logging(db_handler)
            
            return None
