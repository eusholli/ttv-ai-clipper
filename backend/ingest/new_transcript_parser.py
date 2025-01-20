import re
import logging
from typing import List, Dict, Optional
from .models import TranscriptSegment


def _time_to_seconds(timestamp: str) -> int:
    """Convert timestamp to seconds"""
    parts = timestamp.split(':')
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    else:
        hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds)


class TranscriptParser:
    """Parser for interview transcripts"""
    
    def __init__(self):
        """Initialize parser with transcript content"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def extract_speaker_info(self, segment: str) -> Optional[Dict[str, Optional[str]]]:
        """Extract speaker information from transcript segment"""
        pattern = r'(?:(?P<speaker>[^,(]+?)(?:,\s*(?P<company>[^(]+?))?)?\s*\((?P<timestamp>\d{2}:\d{2}:\d{2}|\d{2}:\d{2})\):'
        match = re.match(pattern, segment)
        return {key: value.strip() if value else None 
                for key, value in match.groupdict().items()} if match else None

    def parse_transcript(self, title: str, date: str, youtube_id: str, content: str) -> List[TranscriptSegment]:
        """Parse transcript content into segments"""
        parsed_segments = []
        saved_info = None

        # add '\n' to the start of the content string
        # to ensure that the first segment is parsed correctly
        content = '\n' + content

        # remove all html tags
        content = re.sub(r'<.*?>', '', content)

        segments = [segment.strip() for segment in re.split(
            r'(\n.*?\((?:\d{2}:)?\d{2}:\d{2}\):\n)',
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

        return {
                "metadata": {
                    "title": title,
                    "date": date,  # Keep original format
                    "youtube_id": youtube_id
                },
                "transcript": parsed_segments
            }


def parse_transcript(title: str, date: str, youtube_id: str, raw_transcript: str) -> dict:
    """
    Parse a raw transcript string into structured JSON format with metadata
    
    Args:
        title: Video title
        date: Video publish date
        youtube_id: YouTube video ID
        raw_transcript: Raw transcript text to parse
        
    Returns:
        Dictionary containing transcript data in JSON format
    """
    try:
        # Initialize parser with raw transcript
        parser = TranscriptParser()

        results = parser.parse_transcript(title, date, youtube_id, raw_transcript)
        return results
        
    except Exception as e:
        logging.error(f"Error parsing transcript: {str(e)}")
        raise


def parse_raw_html(title: str, date: str, youtube_id: str, raw_transcript: str) -> dict:
    """
    Clean and format raw transcript text into HTML for display
    
    Args:
        title: Video title
        date: Video publish date
        youtube_id: YouTube video ID
        raw_transcript: Raw transcript text to clean and format
        
    Returns:
        Dictionary containing metadata and cleaned HTML-formatted transcript text
    """
    try:
        # Basic cleanup
        text = raw_transcript.strip()
        
        # Replace multiple newlines/spaces with single instances
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        
        # Split into segments
        segments = text.split('\n\n')
        html_parts = []
        
        for segment in segments:
            if not segment.strip():
                continue
                
            # Try to identify speaker/timestamp patterns
            # Pattern: "Name, Company (MM:SS):" or similar
            speaker_match = re.match(r"(.*?), (.*?)\((.*?)\):(.*)", segment)
            
            if speaker_match:
                # If we recognize the format, structure it nicely
                speaker, company, timestamp, content = speaker_match.groups()
                html_parts.append(
                    f'<p class="transcript-segment">'
                    f'<span class="speaker-info">'
                    f'<span class="speaker">{speaker.strip()}</span>, '
                    f'<span class="company">{company.strip()}</span> '
                    f'<span class="timestamp">({timestamp.strip()})</span>: '
                    f'</span>'
                    f'{content.strip()}'
                    f'</p>'
                )
            else:
                # If we don't recognize the format, just wrap in paragraph tags
                # and preserve any existing formatting
                html_parts.append(f'<p>{segment.strip()}</p>')
        
        # Join segments with newlines
        html_transcript = '\n'.join(html_parts)
        
        # Return JSON with metadata and HTML transcript
        return {
            "metadata": {
                "title": title,
                "date": date,
                "youtube_id": youtube_id
            },
            "transcript": html_transcript
        }
        
    except Exception as e:
        logging.error(f"Error cleaning transcript for HTML: {str(e)}")
        # On any error, return minimally formatted text
        return {
            "metadata": {
                "title": title,
                "date": date,
                "youtube_id": youtube_id
            },
            "transcript": f"<p>{raw_transcript}</p>"
        }
