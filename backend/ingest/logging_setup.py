import logging
import logging.handlers
import os
from datetime import datetime
from .constants import LOG_DIR

def setup_logging(job_id=None):
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create handlers
    handlers = []
    
    # Job-specific log file if job_id is provided
    if job_id is not None:
        job_log_file = LOG_DIR / f"job_{job_id}.log"
        job_handler = logging.handlers.RotatingFileHandler(
            job_log_file, maxBytes=10*1024*1024, backupCount=5
        )
        job_handler.setFormatter(formatter)
        handlers.append(job_handler)
    
    # General log file
    general_log_file = LOG_DIR / f"ingest_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        general_log_file, maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add new handlers
    for handler in handlers:
        root_logger.addHandler(handler)
    
    # Suppress verbose logs from other libraries
    logging.getLogger("moviepy").setLevel(logging.WARNING)
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    
    return job_log_file if job_id is not None else None

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)
