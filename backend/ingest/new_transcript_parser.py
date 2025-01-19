import pysrt
import re
import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union, Tuple
from bs4 import BeautifulSoup
import logging

class TranscriptParser:
    """
    Parser for interview transcripts that handles multiple formats:
    - Raw text with timestamps
    - HTML formatted text
    - JSON structured data
    """
    
    def __init__(self, content: Union[str, dict]):
        """
        Initialize parser with transcript content
        
        Args:
            content: Either raw text, HTML string, or parsed JSON dict
        """
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        try:
            if isinstance(content, dict):
                self.raw_text = self._convert_json_to_text(content)
            else:
                # Clean HTML if present
                self.raw_text = self._clean_html(content)
                
            # Standardize format
            self.raw_text = self._standardize_format(self.raw_text)
            self.srt_text = self._convert_to_srt(self.raw_text)
            self.subtitles = pysrt.from_string(self.srt_text)
            self.speakers = self._identify_speakers()
            
        except Exception as e:
            self.logger.error(f"Error initializing transcript parser: {str(e)}")
            raise

    def _clean_html(self, text: str) -> str:
        """
        Convert HTML formatted transcript to plain text
        
        Args:
            text: HTML formatted text
            
        Returns:
            Clean plain text
        """
        try:
            if '<br>' in text or '<p>' in text:
                soup = BeautifulSoup(text, 'html.parser')
                # Replace <br> and </p> with newlines
                for br in soup.find_all(['br', 'p']):
                    br.replace_with('\n')
                return soup.get_text()
            return text
        except Exception as e:
            self.logger.error(f"Error cleaning HTML: {str(e)}")
            return text

    def _convert_json_to_text(self, json_content: dict) -> str:
        """
        Convert JSON transcript format to text format
        
        Args:
            json_content: Dictionary containing transcript data
            
        Returns:
            Formatted text version of transcript
        """
        try:
            text_parts = []
            for segment in json_content.get('transcript', []):
                metadata = segment['metadata']
                # Convert timestamp to MM:SS format
                timestamp = f"{int(metadata['start_timestamp'] // 60):02d}:{int(metadata['start_timestamp'] % 60):02d}"
                text_parts.append(
                    f"{metadata['speaker']}, {metadata['company']} ({timestamp}):\n{segment['text']}"
                )
            return '\n\n'.join(text_parts)
        except Exception as e:
            self.logger.error(f"Error converting JSON to text: {str(e)}")
            raise

    def to_json(self, title: str = None, date: str = None, youtube_id: str = None) -> dict:
        """
        Convert transcript to JSON format with metadata and segments
        
        Args:
            title: Video title
            date: Video publish date
            youtube_id: YouTube video ID
            
        Returns:
            Dictionary containing transcript data in JSON format
        """
        try:
            json_data = {
                "metadata": {
                    "title": title,
                    "date": date,  # Keep original format
                    "youtube_id": youtube_id
                },
                "transcript": []
            }

            for sub in self.subtitles:
                # Extract speaker and company from text
                speaker_match = re.match(r"(.*?), (.*?):", sub.text)
                if speaker_match:
                    speaker, company = speaker_match.groups()
                    # Clean and escape text
                    text = sub.text.split(":", 1)[1].strip()
                    text = text.replace('"', '\\"')  # Escape quotes
                    
                    # Convert timestamps to seconds
                    start_time = sub.start.hours * 3600 + sub.start.minutes * 60 + sub.start.seconds
                    end_time = sub.end.hours * 3600 + sub.end.minutes * 60 + sub.end.seconds

                    # Generate clip download link
                    clip_name = f"clip/{youtube_id}-{start_time}-{end_time}.mp4"

                    # Create segment with cleaned text
                    segment = {
                        "metadata": {
                            "speaker": speaker,
                            "company": company,
                            "start_timestamp": start_time,
                            "end_timestamp": end_time,
                            "subjects": [],
                            "download": clip_name
                        },
                        "text": text
                    }
                    json_data["transcript"].append(segment)

            return json_data

        except Exception as e:
            self.logger.error(f"Error converting to JSON: {str(e)}")
            raise

    def _standardize_format(self, text: str) -> str:
        """
        Standardize line endings and remove extra spaces
        
        Args:
            text: Input text to standardize
            
        Returns:
            Standardized text
        """
        try:
            # Replace multiple newlines with double newline
            text = re.sub(r'\n\s*\n', '\n\n', text)
            # Remove extra spaces
            text = re.sub(r' +', ' ', text)
            # Clean up any extra whitespace around timestamps
            text = re.sub(r'\(\s*(\d+:\d+)\s*\)', r'(\1)', text)
            return text.strip()
        except Exception as e:
            self.logger.error(f"Error standardizing format: {str(e)}")
            return text

    def _convert_timestamp(self, timestamp_str: str) -> str:
        """
        Convert MM:SS timestamp to SRT format (HH:MM:SS,mmm)
        
        Args:
            timestamp_str: Timestamp in MM:SS format
            
        Returns:
            SRT formatted timestamp
        """
        try:
            time = datetime.strptime(timestamp_str.strip("()"), "%M:%S")
            return f"00:{time.strftime('%M:%S')},000"
        except ValueError as e:
            self.logger.warning(f"Error converting timestamp {timestamp_str}: {str(e)}")
            return "00:00:00,000"

    def _convert_to_srt(self, transcript_text: str) -> str:
        """
        Convert transcript text to SRT format
        
        Args:
            transcript_text: Raw transcript text
            
        Returns:
            SRT formatted text
        """
        try:
            srt_entries = []
            segments = transcript_text.split("\n\n")
            
            for i, segment in enumerate(segments, 1):
                if not segment.strip():
                    continue
                    
                match = re.match(r"(.*?)\((.*?)\):(.*)", segment, re.DOTALL)
                if match:
                    speaker, timestamp, text = match.groups()
                    start_time = self._convert_timestamp(timestamp)
                    
                    # Calculate end time (estimate 5 seconds duration)
                    mins, secs = map(int, timestamp.strip("()").split(":"))
                    end_secs = mins * 60 + secs + 5
                    end_time = f"00:{end_secs//60:02d}:{end_secs%60:02d},000"
                    
                    srt_entry = (
                        f"{i}\n"
                        f"{start_time} --> {end_time}\n"
                        f"{speaker.strip()}: {text.strip()}\n"
                    )
                    srt_entries.append(srt_entry)
                    
            return "\n".join(srt_entries)
        except Exception as e:
            self.logger.error(f"Error converting to SRT: {str(e)}")
            raise

    def _identify_speakers(self) -> Dict[str, List[Dict]]:
        """
        Create an index of all speakers and their segments
        
        Returns:
            Dictionary mapping speakers to their segments
        """
        try:
            speakers = {}
            
            for sub in self.subtitles:
                # Extract speaker name from text
                speaker_match = re.match(r"(.*?), (.*?):", sub.text)
                if speaker_match:
                    name, company = speaker_match.groups()
                    if name not in speakers:
                        speakers[name] = []
                        
                    speakers[name].append({
                        'company': company,
                        'start_time': sub.start,
                        'end_time': sub.end,
                        'text': sub.text.split(":", 1)[1].strip(),
                        'index': sub.index
                    })
                    
            return speakers
        except Exception as e:
            self.logger.error(f"Error identifying speakers: {str(e)}")
            return {}

    def get_speaker_segments(self, speaker_name: str) -> List[Dict]:
        """
        Get all segments for a specific speaker
        
        Args:
            speaker_name: Name of the speaker
            
        Returns:
            List of speaker's segments
        """
        return self.speakers.get(speaker_name, [])

    def get_all_speakers(self) -> List[Tuple[str, str]]:
        """
        Get list of all speakers and their companies
        
        Returns:
            List of (speaker, company) tuples
        """
        return [(name, segments[0]['company']) 
                for name, segments in self.speakers.items()]

    def extract_timerange(self, start_time: str, end_time: str) -> List[Dict]:
        """
        Extract segments within a specific time range
        
        Args:
            start_time: Start time in MM:SS format
            end_time: End time in MM:SS format
            
        Returns:
            List of segments within the time range
        """
        try:
            start = datetime.strptime(start_time, "%M:%S")
            end = datetime.strptime(end_time, "%M:%S")
            
            start_srt = pysrt.SubRipTime(
                hours=0,
                minutes=start.minute,
                seconds=start.second
            )
            end_srt = pysrt.SubRipTime(
                hours=0,
                minutes=end.minute,
                seconds=end.second
            )
            
            segments = []
            for sub in self.subtitles.slice(starts_after=start_srt, ends_before=end_srt):
                speaker_match = re.match(r"(.*?), (.*?):", sub.text)
                if speaker_match:
                    name, company = speaker_match.groups()
                    segments.append({
                        'speaker': name,
                        'company': company,
                        'start_time': sub.start,
                        'end_time': sub.end,
                        'text': sub.text.split(":", 1)[1].strip()
                    })
                    
            return segments
        except Exception as e:
            self.logger.error(f"Error extracting timerange: {str(e)}")
            return []

    def get_text_by_speaker(self, speaker_name: str, include_timestamps: bool = False) -> str:
        """
        Get all text from a specific speaker as a continuous string
        
        Args:
            speaker_name: Name of the speaker
            include_timestamps: Whether to include timestamps in output
            
        Returns:
            Concatenated text of all speaker's segments
        """
        try:
            segments = self.get_speaker_segments(speaker_name)
            if include_timestamps:
                return '\n\n'.join(f"({seg['start_time']}) {seg['text']}" for seg in segments)
            return '\n\n'.join(seg['text'] for seg in segments)
        except Exception as e:
            self.logger.error(f"Error getting text by speaker: {str(e)}")
            return ""

def main():
    """Example usage of TranscriptParser"""
    
    if len(sys.argv) > 1:
        # Use file provided as argument
        try:
            with open(sys.argv[1], 'r') as file:
                content = file.read()
            parser = TranscriptParser(content)
            
            # Extract metadata from HTML file if available
            title = "Why Telenor is building a sovereign cloud with AWS"
            date = "Jun 27, 2024"
            youtube_id = "hVQIddeOSg8"
            
            # Convert to JSON format
            json_output = parser.to_json(title, date, youtube_id)
            
            # Format and validate JSON
            try:
                # First convert to string with compact formatting
                json_str = json.dumps(json_output, separators=(',', ':'))
                # Then parse and re-format with pretty printing
                parsed = json.loads(json_str)
                print(json.dumps(parsed, indent=2))
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON generated - {str(e)}")
                return
                
        except FileNotFoundError:
            print(f"Error: File '{sys.argv[1]}' not found")
            return
        except Exception as e:
            print(f"Error processing file: {str(e)}")
            return
    else:
        print("Please provide a transcript file as argument")
        return

if __name__ == "__main__":
    main()
