from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class TranscriptSegment:
    metadata: Dict[str, Optional[str]]
    text: str

@dataclass
class VideoInfo:
    metadata: Dict[str, Optional[str]]
    transcript: List[TranscriptSegment]
