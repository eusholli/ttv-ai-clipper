import logging
import sys
from typing import Optional
from .db_logging_handler import DatabaseLogHandler

# Create logger
logger = logging.getLogger('content_processor')
logger.setLevel(logging.INFO)

# Add stderr handler by default
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stderr_handler.setFormatter(formatter)
logger.addHandler(stderr_handler)

def setup_logging(job_id: Optional[int] = None) -> Optional[DatabaseLogHandler]:
    """Setup logging with optional database handler for job"""
    if job_id:
        # Create and add database handler
        db_handler = DatabaseLogHandler(job_id)
        db_handler.setLevel(logging.INFO)
        logger.addHandler(db_handler)
        
        # Log initial message
        logger.info(f"Starting job {job_id}")
        
        return db_handler
    return None

def cleanup_logging(db_handler: Optional[DatabaseLogHandler] = None):
    """Clean up logging handlers"""
    if db_handler:
        logger.removeHandler(db_handler)
