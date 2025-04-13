# System Patterns

## Architecture Patterns

### 1. Microservices Architecture
- FastAPI backend service
- React frontend service
- Celery worker service for background tasks
- Redis for job queue management
- PostgreSQL for data persistence

### 2. Cloud Storage Pattern
- R2 cloud storage for video content
- Temporary URL generation for secure access
- Efficient content delivery

### 3. Background Processing
- Celery workers for YouTube URL and video processing
- Asynchronous job management
- Task queue for scalable processing
- Separation of long-running tasks from web requests
- Consistent pattern for handling async operations
- Proper error handling and state management for background tasks
- Explicit workflow state transitions for UI synchronization
- Parameter passing between task chain components

### 4. Workflow State Management
- State-based workflow progression
- Explicit state transitions for UI feedback
- Asynchronous state updates via Celery tasks
- Auto-processing capabilities based on parsing status
- UI progress bar synchronized with backend state
- Proper error state handling and recovery

### 5. Database Optimization
- Data Access Layer (DAL) pattern for centralized database operations
- Separate read and write connection pools for reduced contention
- Optimized pool configurations (10-30 connections for reads, 5-20 for writes)
- Transaction isolation levels (READ COMMITTED for reads, REPEATABLE READ for writes)
- Configurable statement timeouts (5s for reads, 30s for writes)
- Performance indexes for common queries
- **New `transcript_chunks` table:** Stores text chunks, embeddings, timestamps, segment references (`segment_hash`), and denormalized metadata for filtering. Replaces the old `transcripts` table.
- JSONB columns for flexible metadata storage (potentially on chunks).
- GiST and GIN indexes for efficient text search (if applicable on chunks) and JSONB entity/metadata querying on chunks.
- **Vector Index (e.g., IVFFlat) on `transcript_chunks.embedding`:** For efficient similarity search between query embedding and chunk embeddings.
- Trigger-based timestamp management.
- Workflow state constraints.
- Consistent retry mechanism with exponential backoff.
- Sentiment score and label columns (potentially denormalized onto chunks).
- JSONB column for storing extracted named entities (NER) (potentially denormalized onto chunks).

### 6. Authentication & Authorization
- Clerk for user authentication
- Role-based access control
- Admin-specific routes and functionality

### 7. AI-Powered Search Pattern: Direct Semantic Search via Chunking
- **Ingestion & Chunking:**
    - Transcripts are divided into smaller, overlapping chunks (e.g., using `langchain.text_splitter.RecursiveCharacterTextSplitter` with token-based splitting, target ~256 tokens, overlap ~50 tokens).
    - Each chunk is embedded using a sentence transformer model (e.g., `sentence-transformers/paraphrase-MiniLM-L3-v2`).
    - Chunks, their embeddings, original segment references (`segment_hash`), timestamps, and potentially enriched/denormalized metadata (speaker, sentiment, entities) are stored in the `transcript_chunks` table.
- **Data Enrichment (Optional, Per Chunk):**
    - **Sentiment Analysis:** Can be run per chunk (e.g., using Hugging Face Transformers).
    - **Named Entity Recognition (NER):** Can be run per chunk (e.g., using LLM).
- **Query Understanding & Filtering:**
    - The user's full, original natural language query is embedded using the *same* sentence transformer model.
    - An LLM (e.g., Anthropic Claude 3 Haiku via standard API client) can optionally parse the query to extract structured filters (speaker, date ranges, sentiment, entities) and other metadata, separate from the core semantic search vector.
- **Retrieval Logic:**
    - **Vector Search:** A vector similarity search is performed between the *query embedding* and the *chunk embeddings* stored in `transcript_chunks`.
    - **Filtering:** Metadata filters (extracted from the query by LLM or provided via UI) are applied during or after the vector search (e.g., filtering chunks by speaker, date, sentiment score, entity presence).
    - **Mapping & Ranking:** The top N relevant *chunks* are retrieved. These chunks are mapped back to their original, full transcript segments using the `segment_hash`. Segments are ranked based on the highest similarity score achieved by any of their constituent chunks.
    - **Result:** The ranked list of original transcript segments is returned.

## Key Technical Decisions

### 1. API Design
- RESTful API architecture
- FastAPI for high performance
- OpenAPI/Swagger documentation
- Proper error handling and status codes

### 2. Frontend Architecture
- React with Vite for modern build tooling
- Component-based architecture
- Responsive design patterns
- State management with React hooks

### 3. Data Management
- PostgreSQL for structured data
- Redis for caching and job queues
- R2 for binary storage
- Efficient data retrieval patterns
- Consolidated schema management
- Version-tracked schema changes

### 4. Security Patterns
- JWT token validation
- Role-based access control
- Secure file storage and access
- Environment variable management

### 5. Deployment Strategy
- Docker containerization
- Multi-stage builds
- Cloud platform deployment (Google Cloud, Render)
- Nginx reverse proxy

## Implementation Guidelines

### 1. Code Organization
- Feature-based directory structure
- Clear separation of concerns
- Modular component design
- Consistent naming conventions

### 2. Error Handling
- Comprehensive error catching
- Proper error logging
- User-friendly error messages
- Error recovery mechanisms

### 3. Performance Optimization
- Database query optimization
- Connection pooling
- Caching strategies
- Resource efficient processing
- Statement timeout management
- Optimized index usage

### 4. Testing Strategy
- Unit testing critical components
- Integration testing for workflows
- Performance testing
- Error scenario testing

### 5. Monitoring and Logging
- Structured logging
- Performance monitoring
- Error tracking
- Usage analytics
