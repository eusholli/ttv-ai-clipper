import asyncio
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .constants import MAX_WORKERS
from .logging_setup import logger
from .models import Transcript, TranscriptSegment
from backend.r2_manager import R2Manager
from backend.video_utils import get_youtube_video, generate_clips

class VideoProcessor:
    """Handles video processing and clip generation"""

    def __init__(self, cache_dir: Path, clip_dir: Path):
        self.cache_dir = cache_dir
        self.clip_dir = clip_dir
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.r2_manager = R2Manager()
        self.workflow_processor = None  # Will be set by WorkflowProcessor

    def get_cached_video(self, youtube_id: str) -> Path:
        """Get path for cached video file"""
        return self.cache_dir / f"{youtube_id}.mp4"

    async def process_video(self, info: dict, job_id: Optional[int] = None) -> Transcript:
        """Process video for a given transcript info dictionary or Transcript object"""
        start_time = datetime.now()

        try:
            # Setup job-specific logging if job_id is provided
            db_handler = None
            if job_id is not None:
                from .logging_setup import setup_logging, cleanup_logging
                db_handler = setup_logging(job_id)

            # Convert dict to Transcript object if needed
            if isinstance(info, dict):
                info = Transcript.model_validate(info)
            
            youtube_id = info.metadata.get('youtube_id', 'Unknown youtube_id')
            title = info.metadata.get('title', 'Unknown Title')
            
            logger.info(f"Starting video processing for '{title}' (ID: {youtube_id})")
            logger.info(f"Job configuration: cache_dir={self.cache_dir}, clip_dir={self.clip_dir}")
            
            # Download video with progress tracking
            logger.info(f"Attempting to download video {youtube_id} from YouTube")
            download_start = datetime.now()
            if not get_youtube_video(str(self.clip_dir), youtube_id):
                raise Exception(f"Failed to download video {youtube_id}")
            download_duration = (datetime.now() - download_start).total_seconds()
            logger.info(f"Video download completed in {download_duration:.2f} seconds")
            
            if job_id:
                # Use the workflow processor's connection pool
                with self.workflow_processor.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute('''
                            UPDATE ingest_jobs 
                            SET video_fetched_at = CURRENT_TIMESTAMP,
                                video_fetch_success = true
                            WHERE id = %s
                        ''', (job_id,))
                        conn.commit()   
                await self.workflow_processor.update_workflow_state(job_id, 'video_fetched')
                logger.info("Video fetch phase completed successfully")

            if job_id:
                await self.workflow_processor.update_workflow_state(job_id, 'generating_clips')
                logger.info("Beginning clip generation phase")

            # Generate and upload clips
            if info.transcript:
                clip_start = datetime.now()
                total_segments = len(info.transcript)
                logger.info(f"Generating {total_segments} clips for video '{title}' ({youtube_id})")
                info_dict = info.model_dump()
                logger.info("Starting clip generation")
                clip_gen_start = datetime.now()
                # Run generate_clips in the same event loop
                info_dict['transcript'] = await asyncio.get_event_loop().run_in_executor(
                    None, generate_clips, str(self.clip_dir), info_dict
                )
                clip_gen_duration = (datetime.now() - clip_gen_start).total_seconds()
                logger.info(f"Clip generation completed in {clip_gen_duration:.2f} seconds")
                info = Transcript.model_validate(info_dict)
                
                # Upload clips to R2
                logger.info("Beginning R2 upload phase")
                upload_start = datetime.now()
                clip_pattern = f"{youtube_id}_*.mp4"
                new_clips = list(self.clip_dir.glob(clip_pattern))
                total_clips = len(new_clips)
                logger.info(f"Found {total_clips} clips to upload")
                
                upload_success = True
                uploaded_count = 0
                for clip in new_clips:
                    logger.info(f"Uploading clip {uploaded_count + 1}/{total_clips}: {clip.name}")
                    if not self.r2_manager.upload_file(str(clip), clip.name):
                        upload_success = False
                        logger.error(f"Failed to upload clip {clip.name} to R2")
                        break
                    uploaded_count += 1
                    logger.info(f"Upload progress: {uploaded_count}/{total_clips} clips")
                
                if not upload_success:
                    logger.error("Failed to upload clips to R2 storage")
                    raise Exception("Failed to upload clips to R2 storage")
                
                upload_duration = (datetime.now() - upload_start).total_seconds()
                logger.info(f"R2 upload phase completed in {upload_duration:.2f} seconds")

            if job_id:
                total_duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"Video processing completed successfully in {total_duration:.2f} seconds")
                await self.workflow_processor.update_workflow_state(job_id, 'completed')
                
                # Clean up logging
                if db_handler:
                    cleanup_logging(db_handler)
            
            return info

        except Exception as e:
            error_msg = f"Error processing video {youtube_id}: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            if job_id:
                await self.workflow_processor.update_workflow_state(job_id, 'failed', error_msg)
                
                # Clean up logging
                if db_handler:
                    cleanup_logging(db_handler)
            raise
