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
- **PostgreSQL**: Primary database
- **R2**: Cloud storage for video content
- **Nginx**: Reverse proxy server

### Development Tools
- **Docker**: Containerization
- **Git**: Version control
- **VSCode**: Recommended IDE
- **Python**: Backend language
- **Node.js**: Frontend build environment

## Development Setup

### Environment Requirements
- Python 3.11+
- Node.js 16+
- Docker
- PostgreSQL 13+
- Redis

### Environment Variables
1. Frontend (.env and .env.production):
   - VITE_CLERK_PUBLISHABLE_KEY
   - Other authentication settings
   - API endpoints

2. Backend (.env):
   - Database connection strings
   - R2 storage credentials
   - API keys and secrets
   - SMTP configuration
   - Stripe configuration

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
- API response time < 500ms
- Video processing in background
- Efficient search queries
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
- API rate limiting
- Processing resource constraints

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
