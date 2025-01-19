import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup, NavigableString
from .models import TranscriptSegment, VideoInfo
from .logging_setup import logger
from backend.transcript_search import extract_subject_info

class TranscriptParser:
    def __init__(self, nlp):
        self.nlp = nlp

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
                                'subjects': extract_subject_info(text, self.nlp)
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
                                'subjects': extract_subject_info(text, self.nlp)
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
                    'subjects': extract_subject_info(text, self.nlp)
                },
                text=text
            ))

        return parsed_segments
