# Technical Context

## Technologies Used

### Frontend
- **React**: Main frontend framework
- **Vite**: Build tool and development server
- **Clerk**: Authentication and user management
- **Stripe**: Payment processing and subscription management
- **CSS**: Custom styling

### Backend
- **FastAPI**: Python web framework
- **Celery**: Distributed task queue
- **Redis**: Message broker and caching
- **PostgreSQL**: Primary database (with pgvector extension)
- **R2**: Cloud storage for video content
- **Nginx**: Reverse proxy server
- **Anthropic API (Claude 3 Haiku)**: Used for LLM-based query parsing and NER during ingestion (via standard client).
- **Hugging Face Transformers**: Used for sentiment analysis during ingestion (`cardiffnlp/twitter-roberta-base-sentiment-latest`).
- **Sentence Transformers**: Used for generating text embeddings (`paraphrase-MiniLM-L3-v2`) for transcript *chunks* and user queries.
- **Langchain**: Used for text splitting (chunking) utilities (`RecursiveCharacterTextSplitter`).
- **Tiktoken**: Used by Langchain for token counting during chunking.

### Development Tools
- **Docker**: Containerization
- **Git**: Version control
- **VSCode**: Recommended IDE
- **Python**: Backend language
- **Node.js**: Frontend build environment
- **Langchain**: Text splitting framework
- **Tiktoken**: Tokenizer library

## Development Setup

### Environment Requirements
- Python 3.11+
- Node.js 16+
- Docker
- PostgreSQL 13+ (with pgvector extension installed)
- Redis
- Required Python packages (including `langchain`, `tiktoken`, `sentence-transformers`, `anthropic`, etc. - see `requirements.txt`)

### Environment Variables
1. Frontend (.env and .env.production):
   - VITE_CLERK_PUBLISHABLE_KEY
   - Other authentication settings
   - API endpoints

2. Backend (.env):
   - Database connection strings
   - R2 storage credentials
   - Database connection strings
   - R2 storage credentials
   - API keys and secrets (including `ANTHROPIC_API_KEY`)
   - SMTP configuration
   - Stripe configuration
   - `QUERY_PARSER_TYPE` (e.g., "anthropic")
   - (Optional) `SENTIMENT_MODEL_NAME`, `NER_MODEL_NAME`

### Local Development
1. Frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

2. Backend:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```

3. Database:
   ```bash
   ./bin/init_db.sh
   ```

## Technical Constraints

### Performance Requirements
- API response time < 500ms (Search latency depends on vector index performance and filtering complexity)
- Video processing (including transcript chunking and embedding generation) in background
- Efficient search queries (vector search on `transcript_chunks` + metadata filtering)
- Data Access Layer (DAL) with separate read/write connection pools
- Optimized connection pool configurations
- Transaction isolation levels for different operations
- Standardized retry mechanism for database operations

### Security Requirements
- JWT token validation
- Role-based access
- Secure file storage
- Environment variable protection

### Scalability Considerations
- Horizontal scaling capability
- Database connection management
- Background task distribution
- Resource utilization optimization

### Browser Support
- Modern browsers (Chrome, Firefox, Safari, Edge)
- Mobile responsiveness
- Progressive enhancement

### Infrastructure Limits
- R2 storage quotas
- Database connection limits
- API rate limiting (including Anthropic API for optional filter extraction/NER)
- Processing resource constraints (including chunking, embedding model execution, optional sentiment/NER model execution)
- LLM API costs and latency (if used for filters/NER)
- Vector database indexing and query performance

## Deployment

### Docker Configuration
- Multi-stage builds
- Optimized image sizes
- Environment configuration
- Volume management

### Cloud Platforms
1. Google Cloud:
   - Cloud Build integration
   - Container deployment
   - Database management
   - Storage configuration
   - Environment variable management (including `ANTHROPIC_API_KEY`)
   - Network egress configuration (for accessing Anthropic API)

2. Render:
   - Web service deployment
   - Database provisioning
   - Environment configuration
   - Build automation

### Monitoring
- Error tracking
- Performance monitoring
- Resource usage tracking
- Log management
