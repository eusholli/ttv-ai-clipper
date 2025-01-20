from .processor import process_urls, process_zip_file
from .models import TranscriptSegment, VideoInfo
from .constants import CACHE_DIR, CLIP_DIR, MAX_WORKERS, MIN_DURATION

def get_content_processor():
    """Get ContentProcessor class, import at runtime to avoid circular dependency"""
    from .content_processor import ContentProcessor
    return ContentProcessor

__all__ = [
    'process_urls',
    'process_zip_file',
    'get_content_processor',
    'TranscriptSegment',
    'VideoInfo',
    'CACHE_DIR',
    'CLIP_DIR',
    'MAX_WORKERS',
    'MIN_DURATION'
]
