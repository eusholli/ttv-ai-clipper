import re
import asyncio
import json
import os
import traceback
import backoff
import zipfile
from backend.r2_manager import R2Manager
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from backend.video_utils import get_youtube_video, generate_clips
from backend.transcript_search import extract_subject_info, TranscriptSearch
import logging
import logging.handlers
import time
import hashlib

# Constants
CACHE_DIR = Path("cache/")
CLIP_DIR = Path("clip/")
LOG_DIR = Path("logs/")
MAX_WORKERS = 4  # Adjust based on system capabilities
MIN_DURATION = 10  # Minimum duration for a clip in seconds

# Ensure directories exist
for directory in [CACHE_DIR, CLIP_DIR, LOG_DIR]:
    directory.mkdir(exist_ok=True)

# Configure logging with rotation
def setup_logging(job_id=None):
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create handlers
    handlers = []
    
    # Job-specific log file if job_id is provided
    if job_id is not None:
        job_log_file = LOG_DIR / f"job_{job_id}.log"
        job_handler = logging.handlers.RotatingFileHandler(
            job_log_file, maxBytes=10*1024*1024, backupCount=5
        )
        job_handler.setFormatter(formatter)
        handlers.append(job_handler)
    
    # General log file
    general_log_file = LOG_DIR / f"ingest_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        general_log_file, maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add new handlers
    for handler in handlers:
        root_logger.addHandler(handler)
    
    # Suppress verbose logs from other libraries
    logging.getLogger("moviepy").setLevel(logging.WARNING)
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    
    return job_log_file if job_id is not None else None

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

@dataclass
class TranscriptSegment:
    metadata: Dict[str, Optional[str]]
    text: str

@dataclass
class VideoInfo:
    metadata: Dict[str, Optional[str]]
    transcript: List[TranscriptSegment]

class ContentProcessor:
    """Handles content processing with caching and error recovery"""
    def __init__(self, cache_dir: Path, clip_dir: Path):
        self.cache_dir = cache_dir
        self.clip_dir = clip_dir
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.r2_manager = R2Manager()
        self.search = TranscriptSearch()
        from backend.job_manager import JobManager
        self.job_manager = JobManager()
        self.cleanup_partial_files()

    def _time_to_seconds(self, time_str: str) -> int:
        """Convert time string (MM:SS or HH:MM:SS) to integer seconds."""
        try:
            parts = time_str.split(':')
            if len(parts) == 2:  # MM:SS
                minutes, seconds = map(int, parts)
                return minutes * 60 + seconds
            elif len(parts) == 3:  # HH:MM:SS
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
            else:
                logger.warning(f"Invalid time format: {time_str}, using 0")
                return 0
        except (ValueError, AttributeError):
            logger.warning(f"Invalid time format: {time_str}, using 0")
            return 0

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
                self.search.cursor.execute('DELETE FROM transcripts WHERE youtube_id = %s', (youtube_id,))
                self.search.conn.commit()
                
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
                    # If we hit duplicates, rollback the failed transaction and fall back to individual inserts
                    self.search.conn.rollback()
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
                                # Rollback the current transaction before raising
                                self.search.conn.rollback()
                                raise e2
                else:
                    # Rollback the current transaction before raising
                    self.search.conn.rollback()
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

    def extract_text_with_br(self, element):
        """Extract text content preserving line breaks"""
        result = ['<br><br>']
        for child in element.descendants:
            if isinstance(child, NavigableString):
                result.append(child.strip())
            elif child.name == 'br':
                result.append('<br>')
        return ''.join(result).strip()

    def extract_info(self, html_content: str) -> Optional[VideoInfo]:
        """Extract video information from HTML content"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract metadata
            title = soup.title.string.strip() if soup.title else None
            date_elem = soup.find('p', class_='content-date')
            date = date_elem.find('span', class_='ng-binding').text.strip() if date_elem else None
            
            # Extract YouTube information
            youtube_iframe = soup.find('iframe', src=lambda x: x and 'youtube' in x)
            youtube_url = youtube_iframe['src'] if youtube_iframe else None
            youtube_id = re.search(r'youtube.*\.com/embed/([^?]+)', youtube_url).group(1) if youtube_url else None
            
            if not youtube_id:
                logger.warning("No YouTube ID found in content")
                return None
            
            # Extract transcript
            transcript_elem = soup.find(id='transcript0')
            if not transcript_elem:
                logger.warning("No transcript element found")
                return None
                
            transcript = self.extract_text_with_br(transcript_elem)
            
            return VideoInfo(
                metadata={'title': title, 'date': date, 'youtube_id': youtube_id},
                transcript=self.parse_transcript(transcript)
            )
        except Exception as e:
            logger.error(f"Error extracting information: {str(e)}")
            return None

    def extract_speaker_info(self, segment: str) -> Optional[Dict[str, Optional[str]]]:
        """Extract speaker information from transcript segment"""
        pattern = r'<br><br>(?:(?P<speaker>[^,(]+?)(?:,\s*(?P<company>[^(]+?))?)?\s*\((?P<timestamp>\d{2}:\d{2}:\d{2}|\d{2}:\d{2})\):<br>'
        match = re.match(pattern, segment)
        return {key: value.strip() if value else None 
                for key, value in match.groupdict().items()} if match else None

    def parse_transcript(self, content: str) -> List[TranscriptSegment]:
        """Parse transcript content into segments"""
        parsed_segments = []
        saved_info = None

        segments = [segment.strip() for segment in re.split(
            r'(<br><br>.*?\((?:\d{2}:)?\d{2}:\d{2}\):<br>)',
            content
        ) if segment.strip()]

        for i, segment in enumerate(segments):
            speaker_info = self.extract_speaker_info(segment)
            if speaker_info:
                if speaker_info['speaker']:
                    if saved_info:
                        text = segments[i-1] if i > 0 else ""
                        parsed_segments.append(TranscriptSegment(
                            metadata={
                                'speaker': saved_info['speaker'],
                                'company': saved_info['company'] or "Unknown",
                                'start_timestamp': self._time_to_seconds(saved_info['timestamp']),
                                'end_timestamp': self._time_to_seconds(speaker_info['timestamp']),
                                'subjects': extract_subject_info(text, self.search.nlp)
                            },
                            text=text
                        ))
                    saved_info = speaker_info
                else:
                    if saved_info:
                        text = segments[i-1] if i > 0 else ""
                        parsed_segments.append(TranscriptSegment(
                            metadata={
                                'speaker': saved_info['speaker'],
                                'company': saved_info['company'] or "Unknown",
                                'start_timestamp': self._time_to_seconds(saved_info['timestamp']),
                                'end_timestamp': self._time_to_seconds(speaker_info['timestamp']),
                                'subjects': extract_subject_info(text, self.search.nlp)
                            },
                            text=text
                        ))
                        saved_info['timestamp'] = speaker_info['timestamp']

        if saved_info:
            text = segments[-1]
            parsed_segments.append(TranscriptSegment(
                metadata={
                    'speaker': saved_info['speaker'],
                    'company': saved_info['company'] or "Unknown",
                    'start_timestamp': self._time_to_seconds(saved_info['timestamp']),
                    'end_timestamp': self._time_to_seconds("00:00:00"),
                    'subjects': extract_subject_info(text, self.search.nlp)
                },
                text=text
            ))

        return parsed_segments

    async def process_url(self, url: str, job_id: Optional[int] = None) -> Optional[VideoInfo]:
        # Setup job-specific logging if job_id is provided
        job_log_file = None
        if job_id is not None:
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
                self.search.cursor.execute('''
                    UPDATE ingest_jobs 
                    SET html_fetched_at = CURRENT_TIMESTAMP,
                        html_fetch_success = true
                    WHERE id = %s
                ''', (job_id,))
                self.search.conn.commit()
                
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
                        self.search.cursor.execute('''
                            UPDATE ingest_jobs 
                            SET html_fetched_at = CURRENT_TIMESTAMP,
                                html_fetch_success = true
                            WHERE id = %s
                        ''', (job_id,))
                        self.search.conn.commit()
                        
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
            info = self.extract_info(content)
            if not info:
                raise Exception("Failed to extract information from content")

            if job_id:
                from backend.workflow_manager import WorkflowManager
                workflow_manager = WorkflowManager()
                await workflow_manager.update_workflow_state(job_id, 'editing_metadata')

            # Check for edited metadata
            if job_id:
                self.search.cursor.execute('''
                    SELECT title, date, youtube_id, source
                    FROM edited_metadata
                    WHERE job_id = %s
                ''', (job_id,))
                edited_metadata = self.search.cursor.fetchone()
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
                        self.search.cursor.execute('''
                            UPDATE ingest_jobs 
                            SET video_fetched_at = CURRENT_TIMESTAMP,
                                video_fetch_success = true
                            WHERE id = %s
                        ''', (job_id,))
                        self.search.conn.commit()
                        
                        from backend.workflow_manager import WorkflowManager
                        workflow_manager = WorkflowManager()
                        await workflow_manager.update_workflow_state(job_id, 'video_fetched')
                else:
                    logger.info(f"Video {youtube_id} already cached at {video_path}")

                # Check for edited transcript
                if job_id:
                    self.search.cursor.execute('''
                        SELECT segment_hash, text, speaker, company, 
                               start_time, end_time, subjects
                        FROM edited_transcripts
                        WHERE job_id = %s
                        ORDER BY start_time
                    ''', (job_id,))
                    edited_segments = self.search.cursor.fetchall()
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
                    self.search.cursor.execute('''
                        UPDATE ingest_jobs 
                        SET last_log_file = %s
                        WHERE id = %s
                    ''', (log_content, job_id))
                    self.search.conn.commit()
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
                        self.search.cursor.execute('''
                            UPDATE ingest_jobs 
                            SET last_log_file = %s
                            WHERE id = %s
                        ''', (log_content, job_id))
                        self.search.conn.commit()
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

async def process_urls(urls: List[str], batch_size: int = 3, max_retries: int = 3):
    """Process URLs in batches with concurrent execution"""
    processor = ContentProcessor(CACHE_DIR, CLIP_DIR)
    total_urls = len(urls)
    failed_urls = []
    
    for i in range(0, total_urls, batch_size):
        batch = urls[i:i + batch_size]
        batch_num = i//batch_size + 1
        total_batches = (total_urls + batch_size - 1)//batch_size
        logger.info(f"Processing batch {batch_num}/{total_batches}")
        
        start_time = time.time()
        tasks = [processor.process_url(url) for url in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for url, result in zip(batch, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to process {url}: {result}")
                failed_urls.append(url)
            elif result is None:
                logger.warning(f"No results for {url}")
                failed_urls.append(url)
            else:
                logger.info(f"Successfully processed {url}")
        
        batch_time = time.time() - start_time
        logger.info(f"Batch {batch_num}/{total_batches} completed in {batch_time:.2f}s")
        
        # Add a small delay between batches to prevent rate limiting
        if i + batch_size < total_urls:
            await asyncio.sleep(1)
    
    # Retry failed URLs
    if failed_urls:
        logger.info(f"Retrying {len(failed_urls)} failed URLs")
        retry_count = 0
        while failed_urls and retry_count < max_retries:
            retry_count += 1
            logger.info(f"Retry attempt {retry_count}/{max_retries}")
            
            retry_batch = failed_urls.copy()
            failed_urls.clear()
            
            tasks = [processor.process_url(url) for url in retry_batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for url, result in zip(retry_batch, results):
                if isinstance(result, Exception) or result is None:
                    failed_urls.append(url)
                else:
                    logger.info(f"Successfully processed {url} on retry {retry_count}")
            
            if failed_urls:
                logger.warning(f"{len(failed_urls)} URLs still failed after retry {retry_count}")
                await asyncio.sleep(5)  # Longer delay between retries
        
        if failed_urls:
            logger.error(f"Failed to process {len(failed_urls)} URLs after {max_retries} retries")
            for url in failed_urls:
                logger.error(f"Failed URL: {url}")

async def process_zip_file(zip_path: Path) -> None:
    """Process JSON files from a zip archive"""
    import tempfile
    import shutil
    
    # Ensure CACHE_DIR exists
    CACHE_DIR.mkdir(exist_ok=True)
    
    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp())
    logger.info(f"Created temporary directory: {temp_dir}")
    
    try:
        # Extract zip contents
        logger.info(f"Extracting {zip_path} to temporary directory")
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(temp_dir)
        
        # Process each JSON file
        json_files = list(temp_dir.glob('*.json'))
        logger.info(f"Found {len(json_files)} JSON files to process")
        
        processor = ContentProcessor(CACHE_DIR, CLIP_DIR)
        for json_file in json_files:
            try:
                logger.info(f"Processing {json_file.name}")
                with open(json_file, 'r') as f:
                    json_data = json.load(f)
                processor.process_transcript(json_data, filename=json_file.name)
                logger.info(f"Successfully processed {json_file.name}")
                
                # Copy processed JSON file to CACHE_DIR
                shutil.copy2(json_file, CACHE_DIR / json_file.name)
                logger.info(f"Copied {json_file.name} to cache directory")
            except Exception as e:
                logger.error(f"Error processing {json_file.name}: {str(e)}")
                continue
    
    except Exception as e:
        logger.error(f"Error processing zip file: {str(e)}")
        raise
    
    finally:
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_dir)
            logger.info("Cleaned up temporary directory")
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory: {str(e)}")

async def main():
    """Main entry point"""
    import sys
    
    # Check if zip file argument is provided
    if len(sys.argv) > 1 and sys.argv[1].endswith('.zip'):
        zip_path = Path(sys.argv[1])
        if not zip_path.exists():
            logger.error(f"Error: Zip file {zip_path} not found.")
            return
        
        logger.info(f"Processing zip file: {zip_path}")
        try:
            await process_zip_file(zip_path)
            logger.info("Zip file processing complete")
            return
        except Exception as e:
            logger.error(f"Failed to process zip file: {str(e)}")
            return
    
    # Default behavior - process URLs from file
    url_file = Path("dsp-urls-one.txt")
    if not url_file.exists():
        logger.error(f"Error: {url_file} not found.")
        return

    urls = url_file.read_text().strip().split('\n')
    if not urls:
        logger.error("No URLs found in input file.")
        return

    start_time = time.time()
    total_urls = len(urls)
    logger.info(f"Starting processing of {total_urls} URLs")
    
    try:
        await process_urls(urls)
    except Exception as e:
        logger.error(f"Fatal error during processing: {e}\n{traceback.format_exc()}")
    finally:
        total_time = time.time() - start_time
        logger.info(f"Processing complete in {total_time:.2f}s. Check logs for details.")
        
        # Create zip file of cache json files
        import zipfile
        with zipfile.ZipFile('urls.zip', 'w') as zipf:
            for json_file in CACHE_DIR.glob('*.json'):
                zipf.write(json_file, json_file.name)
        logger.info("Created urls.zip with all cache JSON files")
        
        # Print summary
        processor = ContentProcessor(CACHE_DIR, CLIP_DIR)
        successful = sum(1 for url in urls if (processor.get_cached_url(url)[1]).exists())
        failed = total_urls - successful
        logger.info(f"Summary:")
        logger.info(f"- Total URLs: {total_urls}")
        logger.info(f"- Successfully processed: {successful}")
        logger.info(f"- Failed: {failed}")
        logger.info(f"- Success rate: {(successful/total_urls)*100:.1f}%")
        logger.info(f"- Average time per URL: {total_time/total_urls:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
