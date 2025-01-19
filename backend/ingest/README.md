# Ingest Package

This package handles the ingestion of video transcripts and related content processing.

## Structure

- `constants.py`: Configuration constants and directory setup
- `logging_setup.py`: Logging configuration and setup
- `models.py`: Data models for transcripts and video info
- `transcript_parser.py`: Handles parsing and extraction of transcript content
- `content_processor.py`: Core content processing functionality
- `processor.py`: Batch processing of URLs and zip files
- `__init__.py`: Package exports

## Usage

The package can be used to process either URLs or zip files containing JSON data:

```python
from backend.ingest import process_urls, process_zip_file

# Process URLs
urls = ["url1", "url2", "url3"]
await process_urls(urls)

# Process zip file
from pathlib import Path
zip_path = Path("data.zip")
await process_zip_file(zip_path)
```

## Components

### ContentProcessor

The main class that handles content processing with features like:
- Caching and error recovery
- Video downloading and processing
- Transcript extraction and parsing
- Database integration
- R2 storage integration

### TranscriptParser

Handles the parsing of transcript content with:
- Speaker information extraction
- Timestamp processing
- Subject extraction
- HTML content parsing

### Models

Data classes for structured data handling:
- TranscriptSegment: Individual transcript segments
- VideoInfo: Complete video information including metadata

## Configuration

Key configuration options in constants.py:
- CACHE_DIR: Directory for cached files
- CLIP_DIR: Directory for video clips
- MAX_WORKERS: Maximum concurrent workers
- MIN_DURATION: Minimum duration for clips
