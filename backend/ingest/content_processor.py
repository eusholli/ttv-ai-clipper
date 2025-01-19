import asyncio
import json
import hashlib
import time
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Tuple, Dict
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import backoff

from .constants import CACHE_DIR, CLIP_DIR, MAX_WORKERS, MIN_DURATION
from .logging_setup import logger
from .models import VideoInfo, TranscriptSegment
from .transcript_parser import TranscriptParser
from backend.r2_manager import R2Manager
from backend.video_utils import get_youtube_video, generate_clips
from backend.transcript_search import TranscriptSearch

class ContentProcessor:
    """Handles content processing with caching and error recovery"""
    def __init__(self, cache_dir: Path, clip_dir: Path):
        self.cache_dir = cache_dir
        self.clip_dir = clip_dir
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.r2_manager = R2Manager()
        self.search = TranscriptSearch()
        self.transcript_parser = TranscriptParser(self.search.nlp)
        from backend.job_manager import JobManager
        self.job_manager = JobManager()
        self.cleanup_partial_files()

    def get_segment_hash(self, segment: dict, main_metadata: dict) -> str:
        hash_string = (
            f"{segment['text']}"
            f"{segment['metadata']['start_timestamp']}"
            f"{segment['metadata']['end_timestamp']}"
            f"{main_metadata.get('title', '')}"
            f"{main_metadata.get('date', '')}"
        )
        return hashlib.md5(hash_string.encode()).hexdigest()

    def process_transcript(self, json_data: dict, filename: Optional[str] = None) -> None:
        try:
            transcript = json_data['transcript']
            main_metadata = json_data.get('metadata', {})
            youtube_id = main_metadata.get('youtube_id')
            
            if youtube_id:
                logger.info(f"Deleting existing entries for YouTube ID: {youtube_id}")
                with self.search.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute('DELETE FROM transcripts WHERE youtube_id = %s', (youtube_id,))
                        conn.commit()
                
                # Mark associated jobs as deleted
                logger.info(f"Marking jobs as deleted for YouTube ID: {youtube_id}")
                self.job_manager.mark_job_deleted(youtube_id)
            
            new_count = 0
            skipped = 0
            
            logger.info(f"Processing transcript with {len(transcript)} segments...")
            
            # Parse date string to datetime object if exists
            date_str = main_metadata.get('date', '')
            date = None
            if date_str:
                try:
                    # Try different date formats
                    date_formats = ['%Y-%m-%d', '%b %d, %Y']
                    for fmt in date_formats:
                        try:
                            date = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                    if date is None:
                        logger.warning(f"Could not parse date: {date_str}")
                except Exception as e:
                    logger.warning(f"Error parsing date '{date_str}': {str(e)}")

            # Prepare batch data
            batch_data = []
            
            for segment in transcript:
                segment_hash = self.get_segment_hash(segment, main_metadata)
                start_time = int(segment['metadata']['start_timestamp'])
                end_time = int(segment['metadata']['end_timestamp'])
                duration = end_time - start_time
                
                # Skip segments less than MIN_DURATION seconds
                if duration < MIN_DURATION:
                    logger.info(f"Skipping segment \"{segment['text']}\"; shorter than {MIN_DURATION} seconds (duration: {duration}s)")
                    continue
                
                batch_data.append({
                    'segment_hash': segment_hash,
                    'text': segment['text'],
                    'title': main_metadata.get('title', ''),
                    'date': date,
                    'youtube_id': main_metadata.get('youtube_id', ''),
                    'source': main_metadata.get('source', ''),
                    'speaker': segment['metadata']['speaker'],
                    'company': segment['metadata']['company'],
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': end_time - start_time,
                    'subjects': segment['metadata']['subjects'],
                    'download': segment['metadata']['download']
                })
            
            try:
                self.search.add_transcripts_batch(batch_data)
                new_count = len(batch_data)
            except Exception as e:
                if "duplicate key value" in str(e):
                    # If we hit duplicates, fall back to individual inserts
                    new_count = 0
                    skipped = 0
                    for data in batch_data:
                        try:
                            self.search.add_transcript(**data)
                            new_count += 1
                        except Exception as e2:
                            if "duplicate key value" in str(e2):
                                skipped += 1
                                logger.info(f"Skipping duplicate segment: {data['segment_hash']}")
                            else:
                                raise e2
                else:
                    raise e
            
            # Store JSON file in database after successful ingestion
            if filename:
                try:
                    self.search.add_json_file(filename, json.dumps(json_data, ensure_ascii=False))
                    logger.info(f"Stored JSON file {filename} in database")
                except Exception as e:
                    logger.error(f"Failed to store JSON file {filename} in database: {str(e)}")

            logger.info(f"Added {new_count} new transcript segments")
            logger.info(f"Skipped {skipped} existing segments")
            
        except Exception as e:
            logger.error(f"Error processing transcript: {str(e)}")
            raise

    def cleanup_partial_files(self):
        """Clean up any partial downloads or failed processing artifacts"""
        try:
            # Clean up partial HTML files (0 bytes)
            for file in self.cache_dir.glob("*.html"):
                if file.stat().st_size == 0:
                    logger.info(f"Removing empty HTML file: {file}")
                    file.unlink()

            # Clean up partial video files (less than 1MB)
            for pattern in ["*_video.mp4", "*.mp4"]:
                for file in self.cache_dir.glob(pattern):
                    if file.stat().st_size < 1_000_000:  # 1MB
                        logger.info(f"Removing partial video file: {file}")
                        file.unlink()

            # Clean up empty JSON files
            for file in self.cache_dir.glob("*.json"):
                if file.stat().st_size == 0:
                    logger.info(f"Removing empty JSON file: {file}")
                    file.unlink()

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_cached_url(self, url: str) -> Tuple[Path, Path]:
        """Get paths for cached files"""
        base_name = url.replace('://', '_').replace('/', '_')
        return (
            self.cache_dir / f"{base_name}.html",
            self.cache_dir / f"{base_name}.json",
        )

    def get_cached_video(self, youtube_id: str) -> Path:
        """Get paths for cached files"""
        return (
            self.cache_dir / f"{youtube_id}.mp4" 
        )

    @backoff.on_exception(
        backoff.expo,
        (PlaywrightTimeoutError, Exception),
        max_tries=3
    )
    async def fetch_url(self, page, url: str) -> Optional[str]:
        """Fetch URL content with retry logic"""
        try:
            await page.goto(url, wait_until='networkidle')
            await page.wait_for_timeout(2000)
            return await page.content()
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            raise

    async def get_client_rendered_content(self, url: str) -> Optional[str]:
        """Get client-rendered content using Playwright"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                return await self.fetch_url(page, url)
            finally:
                await browser.close()

    async def process_url(self, url: str, job_id: Optional[int] = None) -> Optional[VideoInfo]:
        # Setup job-specific logging if job_id is provided
        job_log_file = None
        if job_id is not None:
            from .logging_setup import setup_logging
            job_log_file = setup_logging(job_id)

        """Process URL with caching and error recovery"""
        html_path, json_path = self.get_cached_url(url)

        # Update workflow state if job_id is provided
        if job_id:
            from backend.workflow_manager import WorkflowManager
            workflow_manager = WorkflowManager()
            await workflow_manager.update_workflow_state(job_id, 'fetching_html')

        # Check if HTML already fetched successfully
        if html_path.exists() and html_path.stat().st_size > 0:
            logger.info(f"HTML for {url} already fetched successfully")
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
                
                from backend.workflow_manager import WorkflowManager
                workflow_manager = WorkflowManager()
                await workflow_manager.update_workflow_state(job_id, 'html_fetched')
        else:
            try:
                # Fetch and cache HTML
                logger.info(f"Fetching content for {url}")
                content = await self.get_client_rendered_content(url)
                if content:
                    html_path.write_text(content, encoding='utf-8')
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
                        
                        from backend.workflow_manager import WorkflowManager
                        workflow_manager = WorkflowManager()
                        await workflow_manager.update_workflow_state(job_id, 'html_fetched')
                else:
                    raise Exception("Failed to fetch HTML content")
            except Exception as e:
                if job_id:
                    from backend.workflow_manager import WorkflowManager
                    workflow_manager = WorkflowManager()
                    await workflow_manager.update_workflow_state(job_id, 'failed', str(e))
                raise

        try:
            # Extract information from HTML
            content = html_path.read_text(encoding='utf-8')
            info = self.transcript_parser.extract_info(content)
            if not info:
                raise Exception("Failed to extract information from content")

            if job_id:
                from backend.workflow_manager import WorkflowManager
                workflow_manager = WorkflowManager()
                await workflow_manager.update_workflow_state(job_id, 'editing_metadata')

            # Check for edited metadata
            if job_id:
                with self.search.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute('''
                            SELECT title, date, youtube_id, source
                            FROM edited_metadata
                            WHERE job_id = %s
                        ''', (job_id,))
                        edited_metadata = cur.fetchone()
                        if edited_metadata:
                            info.metadata.update({
                                'title': edited_metadata[0],
                                'date': edited_metadata[1],
                                'youtube_id': edited_metadata[2],
                                'source': edited_metadata[3]
                            })

            # Process video if needed
            if info.metadata.get('youtube_id'):
                youtube_id = info.metadata['youtube_id']
                video_path = self.get_cached_video(youtube_id)

                if job_id:
                    from backend.workflow_manager import WorkflowManager
                    workflow_manager = WorkflowManager()
                    await workflow_manager.update_workflow_state(job_id, 'fetching_video')
                
                # Check if video needs to be downloaded
                if not video_path.exists() or video_path.stat().st_size == 0:
                    logger.info(f"Downloading video {youtube_id}")
                    if not get_youtube_video(str(self.cache_dir), youtube_id):
                        raise Exception(f"Failed to download video {youtube_id}")
                    
                    if job_id:
                        with self.search.get_db_connection() as conn:
                            with conn.cursor() as cur:
                                cur.execute('''
                                    UPDATE ingest_jobs 
                                    SET video_fetched_at = CURRENT_TIMESTAMP,
                                        video_fetch_success = true
                                    WHERE id = %s
                                ''', (job_id,))
                                conn.commit()
                        
                        from backend.workflow_manager import WorkflowManager
                        workflow_manager = WorkflowManager()
                        await workflow_manager.update_workflow_state(job_id, 'video_fetched')
                else:
                    logger.info(f"Video {youtube_id} already cached at {video_path}")

                # Check for edited transcript
                if job_id:
                    with self.search.get_db_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute('''
                                SELECT segment_hash, text, speaker, company, 
                                       start_time, end_time, subjects
                                FROM edited_transcripts
                                WHERE job_id = %s
                                ORDER BY start_time
                            ''', (job_id,))
                            edited_segments = cur.fetchall()
                            if edited_segments:
                                info.transcript = [
                                    TranscriptSegment(
                                        metadata={
                                            'segment_hash': seg[0],
                                            'speaker': seg[2],
                                            'company': seg[3],
                                            'start_timestamp': seg[4],
                                            'end_timestamp': seg[5],
                                            'subjects': seg[6]
                                        },
                                        text=seg[1]
                                    ) for seg in edited_segments
                                ]

                if job_id:
                    from backend.workflow_manager import WorkflowManager
                    workflow_manager = WorkflowManager()
                    await workflow_manager.update_workflow_state(job_id, 'generating_clips')

                # Generate and upload clips
                if info.transcript:
                    logger.info(f"Generating clips for {youtube_id}")
                    info_dict = asdict(info)
                    info_dict['transcript'] = await asyncio.get_event_loop().run_in_executor(
                        self.executor,
                        generate_clips,
                        str(self.cache_dir),
                        info_dict
                    )
                    info = VideoInfo(
                        metadata=info_dict['metadata'],
                        transcript=[TranscriptSegment(**segment) for segment in info_dict['transcript']]
                    )
                    
                    # Upload clips to R2
                    clip_pattern = f"{youtube_id}_*.mp4"
                    new_clips = list(self.clip_dir.glob(clip_pattern))
                    upload_success = True
                    for clip in new_clips:
                        if not self.r2_manager.upload_file(str(clip), clip.name):
                            upload_success = False
                            logger.error(f"Failed to upload clip {clip.name} to R2")
                            break
                    
                    if not upload_success:
                        raise Exception("Failed to upload clips to R2 storage")

            # Save results
            json_path.write_text(
                json.dumps(asdict(info), ensure_ascii=False, indent=2),
                encoding='utf-8'
            )

            # Process transcript
            try:
                logger.info("Processing transcript...")
                with open(json_path, 'r') as f:
                    json_data = json.load(f)
                self.process_transcript(json_data, filename=json_path.name)
                logger.info("Successfully processed transcript")

                if job_id:
                    from backend.workflow_manager import WorkflowManager
                    workflow_manager = WorkflowManager()
                    await workflow_manager.update_workflow_state(job_id, 'completed')

            except Exception as e:
                logger.error(f"Error processing transcript: {str(e)}")
                if job_id:
                    from backend.workflow_manager import WorkflowManager
                    workflow_manager = WorkflowManager()
                    await workflow_manager.update_workflow_state(job_id, 'failed', str(e))
                raise

            # Update job log in database if job_id is provided
            if job_id and job_log_file:
                try:
                    with open(job_log_file, 'r') as f:
                        log_content = f.read()
                    with self.search.get_db_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute('''
                                UPDATE ingest_jobs 
                                SET last_log_file = %s
                                WHERE id = %s
                            ''', (log_content, job_id))
                            conn.commit()
                except Exception as log_e:
                    logger.error(f"Failed to update job log in database: {str(log_e)}")
            
            return info

        except Exception as e:
            error_msg = f"Error processing {url}: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            if job_id:
                from backend.workflow_manager import WorkflowManager
                workflow_manager = WorkflowManager()
                await workflow_manager.update_workflow_state(job_id, 'failed', error_msg)
                
                # Update job log in database even on failure
                if job_log_file:
                    try:
                        with open(job_log_file, 'r') as f:
                            log_content = f.read()
                        with self.search.get_db_connection() as conn:
                            with conn.cursor() as cur:
                                cur.execute('''
                                    UPDATE ingest_jobs 
                                    SET last_log_file = %s
                                    WHERE id = %s
                                ''', (log_content, job_id))
                                conn.commit()
                    except Exception as log_e:
                        logger.error(f"Failed to update job log in database: {str(log_e)}")
            
            return None

    def load_cached_result(self, url: str) -> Optional[VideoInfo]:
        """Load cached processing result"""
        _, json_path= self.get_cached_url(url)
        try:
            if json_path.exists():
                data = json.loads(json_path.read_text(encoding='utf-8'))
                return VideoInfo(
                    metadata=data['metadata'],
                    transcript=[TranscriptSegment(**segment) for segment in data['transcript']]
                )
        except Exception as e:
            logger.error(f"Error loading cached result for {url}: {e}")
        return None
