import asyncio
import json
import os
import traceback
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Dict, Tuple
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import backoff
from bs4 import BeautifulSoup

from .constants import MAX_WORKERS, MIN_DURATION
from .logging_setup import logger
from .models import VideoInfo, TranscriptSegment
from .new_transcript_parser import parse_raw_html
from backend.r2_manager import R2Manager
from backend.video_utils import get_youtube_video, generate_clips
from backend.transcript_search import TranscriptSearch


class ContentProcessor:
    """Handles content processing with error recovery"""
    def __init__(self, cache_dir: Path, clip_dir: Path):
        self.cache_dir = cache_dir
        self.clip_dir = clip_dir
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.r2_manager = R2Manager()
        self.search = TranscriptSearch()
        from backend.job_manager import JobManager
        self.job_manager = JobManager()

    @backoff.on_exception(
        backoff.expo,
        (PlaywrightTimeoutError, Exception),
        max_tries=3
    )
    async def fetch_html(self, url: str) -> Optional[str]:
        """Fetch HTML content from URL using Playwright"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until='networkidle')
                await page.wait_for_timeout(2000)
                return await page.content()
            except Exception as e:
                logger.error(f"Error fetching {url}: {str(e)}")
                raise
            finally:
                await browser.close()

    def extract_metadata(self, html_content: str) -> Tuple[str, str, str]:
        """Extract title, date and youtube_id from HTML content"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract title from meta tags or h1
            title = None
            meta_title = soup.find('meta', property='og:title')
            if meta_title:
                title = meta_title.get('content')
            if not title:
                h1 = soup.find('h1')
                if h1:
                    title = h1.text.strip()
            
            # Extract date - look for common date patterns
            date = None
            date_meta = soup.find('meta', property=['article:published_time', 'datePublished'])
            if date_meta:
                date = date_meta.get('content', '').split('T')[0]  # Get just the date part
            
            # Extract YouTube ID from meta tags or URL in content
            youtube_id = None
            yt_meta = soup.find('meta', property='og:video')
            if yt_meta:
                url = yt_meta.get('content', '')
                if 'youtube.com' in url or 'youtu.be' in url:
                    # Extract ID from URL
                    if 'v=' in url:
                        youtube_id = url.split('v=')[1].split('&')[0]
                    else:
                        youtube_id = url.split('/')[-1]
            
            return title, date, youtube_id
            
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            raise

    def extract_transcript(self, html_content: str) -> str:
        """Extract raw transcript text from HTML content using pattern matching"""
        import re
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # First try to find any div that contains text matching our transcript pattern
            # More flexible pattern that handles variations in spacing and punctuation
            transcript_pattern = re.compile(r'[A-Za-z\s]+\s*,\s*[A-Za-z\s]+\s*\(\s*\d{2}\s*:\s*\d{2}\s*\)\s*:')
            
            # Convert HTML to text while preserving some structure
            text_content = soup.get_text('\n', strip=True)
            
            # Split into lines and look for the transcript pattern
            lines = text_content.split('\n')
            for i, line in enumerate(lines):
                if transcript_pattern.match(line):
                    # Found the start of transcript, join remaining lines
                    transcript_text = '\n'.join(lines[i:])
                    
                    # Clean up the transcript text
                    # Remove any content after a clear ending pattern (if exists)
                    end_patterns = [
                        'video transcripts are provided for reference only',
                        'Related content',
                        'Share this video',
                        'Comments',
                        'Additional resources',
                        'About the author',
                        'Read more',
                        'Subscribe',
                        'Follow us',
                        'More from',
                        'Tags:',
                        'Categories:',
                        'Share this:',
                        'Like this:'
                    ]
                    for pattern in end_patterns:
                        if pattern in transcript_text:
                            transcript_text = transcript_text.split(pattern)[0]
                    
                    return transcript_text.strip()
            
            # If pattern not found in plain text, try searching in HTML
            # This handles cases where the text might be split across elements
            all_text = []
            for element in soup.find_all(['div', 'p', 'span', 'article', 'section']):
                text = element.get_text(strip=True)
                if transcript_pattern.search(text):
                    # Found an element containing the pattern
                    # First try to get text from the element itself
                    transcript_element = element
                    
                    # If the text is too short, try parent elements
                    while transcript_element and len(transcript_element.get_text()) < 500:
                        transcript_element = transcript_element.parent
                        if not transcript_element:
                            break
                    
                    if transcript_element:
                        # Get text from the transcript element and its siblings
                        current = transcript_element
                        while current and len(all_text) < 100:
                            # Get text from current element
                            current_text = current.get_text(strip=True)
                            if current_text:
                                all_text.append(current_text)
                            
                            # Also check children if this is a container
                            for child in current.find_all(['div', 'p', 'span'], recursive=False):
                                child_text = child.get_text(strip=True)
                                if child_text and child_text not in all_text:
                                    all_text.append(child_text)
                            
                            # Move to next sibling
                            current = current.find_next_sibling()
                            
                            # Stop if we hit an element that likely indicates the end
                            if current and any(p.lower() in current.get_text().lower() for p in end_patterns):
                                break
                    break
            
            if all_text:
                combined_text = '\n'.join(all_text)
                # Clean up the combined text
                for pattern in end_patterns:
                    if pattern in combined_text:
                        combined_text = combined_text.split(pattern)[0]
                return combined_text.strip()
            
            raise Exception("Could not find transcript content matching expected pattern")
            
        except Exception as e:
            logger.error(f"Error extracting transcript: {str(e)}")
            raise

    def process_transcript(self, json_data: dict) -> None:
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
            
            logger.info(f"Added {new_count} new transcript segments")
            logger.info(f"Skipped {skipped} existing segments")
            
        except Exception as e:
            logger.error(f"Error processing transcript: {str(e)}")
            raise

    def get_segment_hash(self, segment: dict, main_metadata: dict) -> str:
        """Generate hash for transcript segment"""
        hash_string = (
            f"{segment['text']}"
            f"{segment['metadata']['start_timestamp']}"
            f"{segment['metadata']['end_timestamp']}"
            f"{main_metadata.get('title', '')}"
            f"{main_metadata.get('date', '')}"
        )
        return hashlib.md5(hash_string.encode()).hexdigest()

    async def process_video(self, info: VideoInfo, job_id: Optional[int] = None) -> VideoInfo:
        """Process video for a given VideoInfo object"""

        try:
             # Setup job-specific logging if job_id is provided
            db_handler = None
            if job_id is not None:
                from .logging_setup import setup_logging, cleanup_logging
                db_handler = setup_logging(job_id)

            # Import at runtime to avoid circular dependency
            from backend.workflow_manager import WorkflowManager
            workflow_manager = WorkflowManager()

            youtube_id = info.metadata['youtube_id']
            
            if job_id:
                await workflow_manager.update_workflow_state(job_id, 'fetching_video')
            
            # Download video
            logger.info(f"Downloading video {youtube_id}")
            if not get_youtube_video(str(self.clip_dir), youtube_id):
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
                await workflow_manager.update_workflow_state(job_id, 'video_fetched')

            if job_id:
                await workflow_manager.update_workflow_state(job_id, 'generating_clips')

            # Generate and upload clips
            if info.transcript:
                logger.info(f"Generating clips for {youtube_id}")
                info_dict = asdict(info)
                info_dict['transcript'] = await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    generate_clips,
                    str(self.clip_dir),
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
                    logger.error("Failed to upload clips to R2 storage")
                    raise Exception("Failed to upload clips to R2 storage")
            
            if job_id:
                await workflow_manager.update_workflow_state(job_id, 'completed')
                
                # Clean up logging
                if db_handler:
                    cleanup_logging(db_handler)
            
            return info
        except Exception as e:
            error_msg = f"Error processing video {youtube_id}: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            if job_id:
                # Import at runtime to avoid circular dependency
                from backend.workflow_manager import WorkflowManager
                workflow_manager = WorkflowManager()
                await workflow_manager.update_workflow_state(job_id, 'failed', error_msg)
                
                # Clean up logging
                if db_handler:
                    cleanup_logging(db_handler)
            

    async def process_url(self, url: str, job_id: Optional[int] = None) -> Optional[VideoInfo]:
        """Process URL and extract transcript information"""
        try:
            # Import at runtime to avoid circular dependency
            from backend.workflow_manager import WorkflowManager
            workflow_manager = WorkflowManager()
            
            # Setup job-specific logging if job_id is provided
            db_handler = None
            if job_id is not None:
                from .logging_setup import setup_logging, cleanup_logging
                db_handler = setup_logging(job_id)

            # Update workflow state if job_id is provided
            if job_id:
                await workflow_manager.update_workflow_state(job_id, 'fetching_html')

            # 1. Fetch HTML content
            logger.info(f"Fetching content for {url}")
            html_content = await self.fetch_html(url)
            if not html_content:
                logger.error("Failed to fetch HTML content")
                html_content = ""

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
                await workflow_manager.update_workflow_state(job_id, 'html_fetched')

            # 2. Extract metadata from HTML
            title, date, youtube_id = self.extract_metadata(html_content)
            if not title or not youtube_id:
                logger.error("Failed to extract required metadata")
                title = title or "Unknown"
                youtube_id = youtube_id or "Unknown"

            # 3. Extract transcript text
            transcript_text = self.extract_transcript(html_content)
            if not transcript_text:
                logger.error("Failed to extract transcript text")
                transcript_text = ""

            # 4. Parse transcript using parse_raw_html
            json_data = parse_raw_html(title, date, youtube_id, transcript_text)
            if not json_data:
                logger.error("Failed to parse transcript")
                json_data = {
                    "metadata": {
                        "title": title,
                        "date": date,
                        "youtube_id": youtube_id
                    },
                    "transcript": []
                }

            # Store transcript JSON in database
            if job_id:
                with self.search.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute('''
                            UPDATE ingest_jobs 
                            SET transcript = %s
                            WHERE id = %s
                        ''', (json.dumps(json_data), job_id))
                        conn.commit()

                # After metadata and transcript are found, transition to editing metadata state
                await workflow_manager.update_workflow_state(job_id, 'editing_metadata')

            # Clean up logging on success
            if db_handler:
                cleanup_logging(db_handler)
            
            return True # info

        except Exception as e:
            error_msg = f"Error processing {url}: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            if job_id:
                # Import at runtime to avoid circular dependency
                from backend.workflow_manager import WorkflowManager
                workflow_manager = WorkflowManager()
                await workflow_manager.update_workflow_state(job_id, 'failed', error_msg)
                
                # Clean up logging
                if db_handler:
                    cleanup_logging(db_handler)
            
            return None
