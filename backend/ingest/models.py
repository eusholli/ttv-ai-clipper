from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field

class TranscriptSegment(BaseModel):
    metadata: Dict[str, Optional[Union[str, int]]] = Field(default_factory=dict)
    text: str

class Transcript(BaseModel):
    metadata: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Contains title, date, youtube_id"
    )
    raw_transcript: str = ""
    transcript: List[TranscriptSegment] = Field(default_factory=list)

    def model_post_init(self, _):
        # Ensure required metadata fields exist
        required_fields = ['title', 'date', 'youtube_id']
        for field in required_fields:
            if field not in self.metadata:
                self.metadata[field] = None
