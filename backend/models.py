from enum import Enum

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"

class WorkflowState:
    PENDING = "pending"
    FETCHING_HTML = "fetching_html"
    HTML_FETCHED = "html_fetched"
    EDITING_METADATA = "editing_metadata"
    FETCHING_VIDEO = "fetching_video"
    VIDEO_FETCHED = "video_fetched"
    GENERATING_CLIPS = "generating_clips"
    COMPLETED = "completed"
    FAILED = "failed"
