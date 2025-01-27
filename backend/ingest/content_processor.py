from pathlib import Path
from typing import Optional

from .models import Transcript, TranscriptSegment
from .transcript_parser import parse_transcript, parse_raw_html
from .html_extractor import HtmlExtractor
from .video_processor import VideoProcessor
from .transcript_db_manager import TranscriptDbManager
from .url_processor import UrlProcessor

class ContentProcessor:
    """Main orchestrator for content processing with error recovery"""

    def __init__(self, cache_dir: Path, clip_dir: Path):
        self.cache_dir = cache_dir
        self.clip_dir = clip_dir
        
        # Initialize component processors
        self.html_extractor = HtmlExtractor()
        self.video_processor = VideoProcessor(cache_dir, clip_dir)
        self.transcript_db_manager = TranscriptDbManager()
        self.url_processor = UrlProcessor(cache_dir)
        self._workflow_processor = None

    @property
    def workflow_processor(self):
        return self._workflow_processor

    @workflow_processor.setter
    def workflow_processor(self, processor):
        self._workflow_processor = processor
        # Pass the workflow processor to video_processor
        self.video_processor.workflow_processor = processor

    async def process_url(self, url: str, job_id: Optional[int] = None) -> Optional[Transcript]:
        """Process URL and extract transcript information"""
        return await self.url_processor.process_url(url, job_id)

    async def process_video(self, info: Transcript, job_id: Optional[int] = None) -> Transcript:
        """Process video for a given Transcript object"""
        # Process video and generate clips
        info = await self.video_processor.process_video(info, job_id)
        
        # Update transcripts in database
        if info and info.transcript:
            await self.transcript_db_manager.update_transcripts(info)
        
        return info

    def process_transcript(self, json_data: dict) -> None:
        """Process and store transcript data"""
        # Create Transcript object from json_data
        transcript_obj = Transcript(
            metadata={
                'title': json_data.get('metadata', {}).get('title'),
                'date': json_data.get('metadata', {}).get('date'),
                'youtube_id': json_data.get('metadata', {}).get('youtube_id'),
                'source': json_data.get('metadata', {}).get('source')
            },
            raw_transcript='\n'.join(
                segment['text'] for segment in json_data.get('transcript', [])
            ),
            transcript=[
                TranscriptSegment(
                    metadata=segment.get('metadata', {}),
                    text=segment.get('text', '')
                )
                for segment in json_data.get('transcript', [])
            ]
        )
        self.transcript_db_manager.process_transcript(transcript_obj)
