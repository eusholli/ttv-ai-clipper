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
- Celery workers for video processing
- Asynchronous job management
- Task queue for scalable processing

### 4. Database Optimization
- Connection pooling
- Transaction isolation levels
- Statement timeouts (30s default)
- Performance indexes for common queries
- Separate job_transcripts table for large JSONB data
- JSONB columns for flexible metadata storage
- GiST and GIN indexes for efficient text search
- IVFFlat index for vector similarity search
- Trigger-based timestamp management
- Workflow state constraints

### 5. Authentication & Authorization
- Clerk for user authentication
- Role-based access control
- Admin-specific routes and functionality

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
