"""
This module is now a thin wrapper around the backend.ingest package.
All functionality has been moved to the package for better organization.
"""

from backend.ingest import (
    process_urls,
    process_zip_file,
    ContentProcessor,
    TranscriptSegment,
    VideoInfo,
    CACHE_DIR,
    CLIP_DIR,
    MAX_WORKERS,
    MIN_DURATION
)

# Re-export everything from the ingest package
__all__ = [
    'process_urls',
    'process_zip_file',
    'ContentProcessor',
    'TranscriptSegment',
    'VideoInfo',
    'CACHE_DIR',
    'CLIP_DIR',
    'MAX_WORKERS',
    'MIN_DURATION'
]

if __name__ == "__main__":
    import asyncio
    from pathlib import Path
    import sys
    
    async def main():
        """Main entry point"""
        # Check if zip file argument is provided
        if len(sys.argv) > 1 and sys.argv[1].endswith('.zip'):
            zip_path = Path(sys.argv[1])
            await process_zip_file(zip_path)
        else:
            # Default behavior - process URLs from file
            url_file = Path("dsp-urls-one.txt")
            if url_file.exists():
                urls = url_file.read_text().strip().split('\n')
                if urls:
                    await process_urls(urls)
    
    asyncio.run(main())
