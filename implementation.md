# Database Contention Resolution Plan

## Current Issues

1. **Database Contention During Video Processing**
   - Video processing and API requests share the same database connections
   - Long-running video operations block database access
   - No proper transaction isolation levels
   - Single Uvicorn worker handling all requests

2. **Performance Impact**
   - Initial /details API call takes 11.41s after processing starts
   - Subsequent calls still experience 5s delays
   - Database reads blocked during video ingestion

## Solution Architecture

### 1. Separate Worker Process

Implement a dedicated worker process using Celery:

```python
# tasks.py
from celery import Celery
from backend.ingest.video_processor import VideoProcessor

celery = Celery('tasks', broker='redis://localhost:6379/0')

@celery.task
def process_video_task(info, job_id):
    processor = VideoProcessor(CACHE_DIR, CLIP_DIR)
    return processor.process_video(info, job_id)
```

### 2. Database Optimization

1. **Connection Pooling**:
```python
# Updated connection pool configuration
WRITE_POOL_CONFIG = {
    'minconn': 5,
    'maxconn': 20,
    'pool_timeout': 30
}

READ_POOL_CONFIG = {
    'minconn': 10,
    'maxconn': 30,
    'pool_timeout': 10
}
```

2. **Transaction Isolation**:
```python
# Set appropriate isolation levels
READ_COMMITTED = "SET TRANSACTION ISOLATION LEVEL READ COMMITTED"
REPEATABLE_READ = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
```

3. **Statement Timeouts**:
```sql
-- Add to database configuration
ALTER DATABASE your_db SET statement_timeout = '10s';
ALTER DATABASE your_db SET idle_in_transaction_session_timeout = '30s';
```

### 3. API Optimization

1. **Separate Read/Write Operations**:
```python
class WorkflowProcessor:
    @contextmanager
    def get_read_connection(self):
        conn = None
        try:
            conn = self._read_pool.getconn()
            with conn.cursor() as cur:
                cur.execute(READ_COMMITTED)
                cur.execute('SET LOCAL statement_timeout = 5000')
            yield conn
        finally:
            if conn:
                self._read_pool.putconn(conn)

    @contextmanager
    def get_write_connection(self):
        conn = None
        try:
            conn = self._write_pool.getconn()
            with conn.cursor() as cur:
                cur.execute(REPEATABLE_READ)
                cur.execute('SET LOCAL statement_timeout = 30000')
            yield conn
        finally:
            if conn:
                self._write_pool.putconn(conn)
```

2. **Async Job Status Updates**:
```python
class WorkflowProcessor:
    async def get_job_details(self, job_id: int):
        try:
            async with asyncio.timeout(5):  # 5 second timeout
                return await self._get_job_details(job_id)
        except asyncio.TimeoutError:
            return {
                "status": "loading",
                "message": "Operation in progress"
            }
```

### 4. Uvicorn Configuration

Run multiple Uvicorn workers:

```bash
uvicorn main:app --workers 4 --timeout-keep-alive 30
```

## Implementation Steps

1. **Install Dependencies**:
```bash
pip install celery redis
```

2. **Create Celery Worker**:
- Implement tasks.py with Celery configuration
- Move video processing to Celery tasks

3. **Update Database Configuration**:
- Add statement timeouts
- Configure connection pools
- Set transaction isolation levels

4. **Modify API Endpoints**:
- Update /details endpoint to use optimized queries
- Implement async status updates
- Add request timeouts

5. **Deploy Changes**:
- Start Redis server
- Run Celery worker
- Configure multiple Uvicorn workers

## Expected Results

1. **Improved Response Times**:
   - /details API call < 500ms
   - No blocking during video processing
   - Consistent performance under load

2. **Better Resource Utilization**:
   - Separate worker for video processing
   - Optimized database connections
   - Proper load distribution

3. **Enhanced Reliability**:
   - Proper error handling
   - Transaction isolation
   - Request timeouts
