import logging
from typing import Optional, List
from backend.database.manager import DatabaseManager

class DatabaseLogHandler(logging.Handler):
    """Custom logging handler that buffers logs and writes them to database in batches"""
    
    # Maximum number of messages to buffer before auto-flushing
    MAX_BUFFER_SIZE = 100
    
    def __init__(self, job_id: Optional[int] = None):
        super().__init__()
        self.job_id = job_id
        self.db_manager = DatabaseManager()
        self.buffer: List[str] = []
        
        # Set a detailed format with milliseconds and thread info
        formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d - %(levelname)s - [Job %(job_id)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.setFormatter(formatter)
    
    def flush_buffer(self):
        """Write all buffered messages to database"""
        if not self.buffer or not self.job_id:
            return
            
        try:
            with self.db_manager.get_write_conn() as conn:
                with conn.cursor() as cur:
                    # Get existing log once
                    cur.execute('SELECT last_log_file FROM ingest_jobs WHERE id = %s', (self.job_id,))
                    result = cur.fetchone()
                    existing_log = result[0] if result and result[0] else ""
                    
                    # Combine all buffered messages
                    new_content = "\n".join(self.buffer)
                    combined_log = f"{existing_log}\n{new_content}" if existing_log else new_content
                    
                    # Update with combined log in single transaction
                    cur.execute('''
                        UPDATE ingest_jobs 
                        SET last_log_file = %s
                        WHERE id = %s
                    ''', (combined_log, self.job_id))
                    conn.commit()
                    
            # Clear buffer after successful write
            self.buffer = []
                    
        except Exception as e:
            # If we can't log to DB, fall back to stderr
            import sys
            print(f"Error writing to log DB: {str(e)}", file=sys.stderr)
    
    def emit(self, record):
        """Buffer log record and flush if needed"""
        if not self.job_id:
            return
            
        try:
            # Add job_id to record for formatter
            record.job_id = self.job_id
            
            # Format the log message
            msg = self.format(record)
            
            # Add visual separator for state transitions
            if "workflow state to" in record.msg:
                msg = f"\n{'='*50}\n{msg}\n{'='*50}"
                # Force flush on state transitions
                self.buffer.append(msg)
                self.flush_buffer()
                return
            
            # Add to buffer
            self.buffer.append(msg)
            
            # Auto-flush if buffer is full
            if len(self.buffer) >= self.MAX_BUFFER_SIZE:
                self.flush_buffer()
                
        except Exception as e:
            # If we can't log to DB, fall back to stderr
            import sys
            print(f"Error writing to log DB: {str(e)}", file=sys.stderr)
    
    def close(self):
        """Flush any remaining messages and close the handler"""
        self.flush_buffer()
        super().close()
