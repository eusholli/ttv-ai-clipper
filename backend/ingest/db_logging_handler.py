import logging
from typing import Optional
from backend.transcript_search import TranscriptSearch

class DatabaseLogHandler(logging.Handler):
    """Custom logging handler that writes logs directly to database"""
    
    def __init__(self, job_id: Optional[int] = None):
        super().__init__()
        self.job_id = job_id
        self.search = TranscriptSearch()
        
        # Set a default format
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.setFormatter(formatter)
        
    def emit(self, record):
        """Write log record to database"""
        if not self.job_id:
            return
            
        try:
            # Format the log message
            msg = self.format(record)
            
            with self.search.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # First get existing log
                    cur.execute('SELECT last_log_file FROM ingest_jobs WHERE id = %s', (self.job_id,))
                    result = cur.fetchone()
                    existing_log = result[0] if result and result[0] else ""
                    
                    # Append new log
                    combined_log = f"{existing_log}\n{msg}" if existing_log else msg
                    
                    # Update with combined log
                    cur.execute('''
                        UPDATE ingest_jobs 
                        SET last_log_file = %s
                        WHERE id = %s
                    ''', (combined_log, self.job_id))
                    conn.commit()
                    
        except Exception as e:
            # If we can't log to DB, fall back to stderr
            import sys
            print(f"Error writing to log DB: {str(e)}", file=sys.stderr)
