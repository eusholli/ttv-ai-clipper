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
- Separate job_transcripts table for large JSONB data
- JSONB columns for flexible metadata storage
- GiST and GIN indexes for efficient text search and JSONB entity querying
- IVFFlat index for vector similarity search
- Trigger-based timestamp management
- Workflow state constraints
- Consistent retry mechanism with exponential backoff
- Sentiment score and label columns for sentiment filtering
- JSONB column for storing extracted named entities (NER)

### 6. Authentication & Authorization
- Clerk for user authentication
- Role-based access control
- Admin-specific routes and functionality

### 7. AI-Powered Search Pattern
- **Query Understanding:** LLM (Anthropic Claude 3 Haiku via API) parses natural language queries into structured `ParsedQuery` objects (concepts, sentiment, entities, filters, relationships) using the `instructor` library. Abstraction layer (`QueryParser`) allows for future model changes.
- **Data Enrichment (Ingestion):**
    - **Sentiment Analysis:** Hugging Face Transformers (`cardiffnlp/twitter-roberta-base-sentiment-latest`) calculates sentiment scores/labels for each transcript segment.
    - **Named Entity Recognition (NER):** LLM (Anthropic Claude 3 Haiku via API) extracts entities (PERSON, ORG, etc.) from each segment.
- **Hybrid Search Logic:** Database query combines semantic search (vector similarity on concepts), full-text search (on original query), sentiment filtering (on scores), entity filtering (JSONB containment), and standard metadata filtering based on the `ParsedQuery`.

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
