import re
import hashlib
from datetime import datetime
from typing import Optional, Dict

from .models import TranscriptSegment, Transcript

def _time_to_seconds(timestamp: str) -> int:
    """Convert timestamp to seconds"""
    parts = timestamp.split(':')
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    else:
        hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds)

def _extract_speaker_info(segment: str) -> Optional[Dict[str, Optional[str]]]:
    """Extract speaker information from transcript segment"""
    pattern = r'(?:(?P<speaker>[^,(]+?)(?:,\s*(?P<company>[^(]+?))?)?\s*\((?P<timestamp>\d{2}:\d{2}:\d{2}|\d{2}:\d{2})\):'
    match = re.match(pattern, segment)
    return {key: value.strip() if value else None 
            for key, value in match.groupdict().items()} if match else None

def get_segment_hash(segment: dict, main_metadata: dict) -> str:
    """Generate hash for transcript segment"""
    hash_string = (
        f"{segment['text']}"
        f"{segment['metadata']['start_timestamp']}"
        f"{segment['metadata']['end_timestamp']}"
        f"{main_metadata.get('title', '')}"
        f"{main_metadata.get('date', '')}"
    )
    return hashlib.md5(hash_string.encode()).hexdigest()

def parse_transcript(title: str, date: str, youtube_id: str, content: str) -> dict:
    """Parse transcript content into segments with raw transcript"""
    try:
        # Validate required metadata
        if not title or not title.strip():
            return {"success": False, "error": "Title is required"}
        if not date or not date.strip():
            return {"success": False, "error": "Date is required"}
        if not youtube_id or not youtube_id.strip():
            return {"success": False, "error": "YouTube ID is required"}

        # add '\n' to the start of the content string
        # to ensure that the first segment is parsed correctly
        content = '\n' + content

        # remove all html tags
        content = re.sub(r'<.*?>', '', content)

        # Split content into segments for structure validation
        pattern = r'(\n.*?\((?:\d{2}:)?\d{2}:\d{2}\):\n)'
        segments = re.split(pattern, content)
        segments = [s.strip() for s in segments if s.strip()]

        # Validate transcript structure
        if len(segments) < 2:  # Need at least one timestamp line and one content line
            return {"success": False, "error": "Transcript must contain at least one timestamp line followed by content"}

        # Check if segments alternate between timestamp lines and content
        for i in range(0, len(segments), 2):
            # Check timestamp line
            if i >= len(segments):
                return {"success": False, "error": "Transcript structure is incomplete - missing content after timestamp"}
                
            timestamp_line = segments[i]
            if not re.match(r'.*?\((?:\d{2}:)?\d{2}:\d{2}\):', timestamp_line):
                return {"success": False, "error": f"Invalid timestamp line format: {timestamp_line}"}
            
            # Check content line
            if i + 1 >= len(segments):
                return {"success": False, "error": "Transcript structure is incomplete - missing content after timestamp"}

        parsed_segments = []
        saved_info = None

        for i, segment in enumerate(segments):
            speaker_info = _extract_speaker_info(segment)
            if speaker_info:
                if speaker_info['speaker']:
                    if saved_info:
                        text = segments[i-1] if i > 0 else ""
                        parsed_segments.append(TranscriptSegment(
                            metadata={
                                'speaker': saved_info['speaker'],
                                'company': saved_info['company'] or "Unknown",
                                'start_timestamp': _time_to_seconds(saved_info['timestamp']),
                                'end_timestamp': _time_to_seconds(speaker_info['timestamp']),
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
                                'start_timestamp': _time_to_seconds(saved_info['timestamp']),
                                'end_timestamp': _time_to_seconds(speaker_info['timestamp']),
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
                    'start_timestamp': _time_to_seconds(saved_info['timestamp']),
                    'end_timestamp': _time_to_seconds("00:00:00"),
                },
                text=text
            ))

        # Create a proper Transcript object
        transcript_obj = Transcript(
            metadata={
                "title": title.strip(),
                "date": date.strip(),
                "youtube_id": youtube_id.strip()
            },
            raw_transcript=content,
            transcript=parsed_segments
        )

        return {
            "success": True,
            "data": transcript_obj
        }
            
    except Exception as e:
        from .logging_setup import logger
        logger.error(f"Error parsing transcript: {str(e)}")
        return {"success": False, "error": f"Error parsing transcript: {str(e)}"}

def parse_raw_html(title: str, date: str, youtube_id: str, raw_transcript: str) -> dict:
    """Parse raw transcript text into structured segments"""
    try:
        # Basic cleanup
        text = raw_transcript.strip()
        
        # Replace multiple newlines/spaces with single instances
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        # Use parse_transcript to validate and parse the cleaned text
        return parse_transcript(title, date, youtube_id, text)
        
    except Exception as e:
        from .logging_setup import logger
        logger.error(f"Error in parse_raw_html: {str(e)}")
        return {"success": False, "error": f"Error cleaning raw transcript: {str(e)}"}
