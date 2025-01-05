# TTV AI Clipper Implementation Design

## Architecture Overview

TTV AI Clipper is a full-stack application designed to process and manage video content. The application follows a microservices architecture pattern with the following main components:

- Frontend: React-based SPA using Vite
- Backend API: Python FastAPI service
- Storage: PostgreSQL database and R2 object storage
- Authentication: User management system
- Containerization: Docker for consistent deployment

## Frontend Implementation

### Technology Stack
- React with Vite for build tooling
- Clerk for authentication management
- Axios for API requests
- React Router for navigation
- Environment-based configuration (.env files)

### Core Components

1. **Authentication Module** (`/frontend/src/components/auth/`)
   - SignIn.jsx: Handles user login with Clerk integration
   - SignUp.jsx: New user registration flow
   - UserProfile.jsx: User profile and subscription management
   - Navigation.jsx: Authentication-aware navigation with protected routes

2. **Pricing Module** (`/frontend/src/components/pricing/`)
   - Pricing.jsx: Subscription plans and pricing display
   - Custom styling in Pricing.css
   - Integration with Stripe for payment processing

3. **Main Application Components**
   - Search Interface:
     * Advanced search with multiple filters
     * Real-time results display
     * Support for speaker, date, title, company, and subject filtering
   - Video Player:
     * YouTube video embedding
     * Custom time range playback
     * Clip download functionality
   - Download Management:
     * Subscription-based access control
     * Progress tracking
     * Error handling

### State Management
- Local state management using React hooks
- Session storage for search state persistence
- Authentication state through Clerk
- Download state tracking per clip

### Environment Configuration
The frontend uses different environment files for development and production:
- `.env`: Development configuration with variables:
  * VITE_BACKEND_URL
  * VITE_CLERK_PUBLISHABLE_KEY
- `.env.production`: Production settings

## Backend Implementation

### Core Services

1. **Main API Service** (`backend/main.py`)
   - FastAPI application with CORS middleware
   - Health check and database test endpoints
   - Comprehensive error handling and logging
   - Environment variable validation

2. **API Endpoints**
   - Search Endpoints:
     * POST `/api/search`: Advanced search with filters
     * GET `/api/filters`: Available filter options
     * GET `/api/clip/{segment_hash}`: Clip metadata
   - Video Endpoints:
     * GET `/api/download/{segment_hash}`: Clip download
   - Subscription Endpoints:
     * POST `/api/create-checkout-session`: Stripe checkout
     * POST `/api/create-portal-session`: Customer portal
     * GET `/api/subscription-status`: Subscription check
     * POST `/api/webhook`: Stripe webhook handler
   - System Endpoints:
     * GET `/api/health`: Health check
     * GET `/api/db-test`: Database connection test
     * GET `/api/version`: Version information

3. **Video Processing** (`backend/video_utils.py`)
   - Video content processing and optimization
   - Format conversion and validation
   - Clip extraction and processing

4. **Storage Management** (`backend/r2_manager.py`)
   - R2 object storage integration
   - Video file upload/download handling
   - URL generation and content delivery

5. **Data Management**
   - Data Ingestion (`backend/ingest_pg.py`):
     * PostgreSQL data ingestion pipeline
     * Data transformation and validation
   - Search Implementation (`backend/transcript_search.py`):
     * Hybrid search with semantic and text matching
     * Filter management and optimization
     * Metadata retrieval and caching

### Dependencies and Requirements
- Core requirements in `requirements.txt`:
  * FastAPI for API framework
  * Stripe for payment processing
  * PostgreSQL drivers
  * Cloud storage SDKs
- Extended dependencies in `requirements-slow.txt`

## Database and Storage

### PostgreSQL Database
- Primary data store for application
- Managed through Python scripts
- Initialization via `bin/init_remote_db.sh`

### R2 Object Storage
- Used for large file storage (videos, assets)
- Managed through r2_manager.py
- Configured via environment variables

## Authentication System

The authentication system is implemented using Clerk with Stripe integration:

### Frontend Auth Flow
1. User Registration:
   - SignUp component handles new user registration
   - Automatic Stripe customer creation
   - Metadata synchronization between Clerk and Stripe

2. User Authentication:
   - SignIn component manages login process
   - JWT token management
   - Session persistence
   - Protected route handling via ProtectedRoute component

3. Session Management:
   - UserProfile component for profile management
   - Subscription status monitoring
   - Payment method management
   - Account settings control

4. Navigation Control:
   - Authentication-aware navigation
   - Route protection
   - Redirect handling for unauthenticated users

### Backend Auth Flow
1. Token Validation:
   - JWT verification using Clerk
   - Token extraction from Authorization header
   - Error handling for invalid tokens

2. Session Management:
   - Stateless session handling
   - Token-based authentication
   - Session expiration handling

3. Access Control:
   - Role-based access control
   - Subscription status verification
   - Resource access management
   - Rate limiting and throttling

## Deployment Process

### Docker Configuration
- Base image: `Dockerfile.base`
- Application image: `Dockerfile`
- Build scripts in `/bin/`
  - `build-base.sh`: Base image construction
  - `build.sh`: Application image building

### Cloud Deployment
- Google Cloud Build configuration in `cloudbuild.yaml`
- Render deployment setup in `render.yaml`
- Nginx configuration in `nginx.conf`

### Utility Scripts
- `run_docker.py`: Local Docker management
- `bin/start.sh`: Application startup
- `bin/stop.sh`: Graceful shutdown
- `bin/delete_run_logs.sh`: Log management
- `bin/update_gcloud_secrets.sh`: Cloud secrets management

## Development Setup

### Prerequisites
1. Node.js and npm for frontend
2. Python 3.x for backend
3. Docker for containerization
4. PostgreSQL database
5. Clerk account for authentication
6. Stripe account for payments
7. R2 compatible storage account

### Environment Setup
1. Clone repository
2. Configure environment variables:
   ```bash
   # Copy environment templates
   cp .env.example .env
   cp frontend/.env.example frontend/.env
   ```
3. Required environment variables:
   ```
   # Backend
   STRIPE_SECRET_KEY=sk_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   R2_ACCOUNT_ID=...
   R2_ACCESS_KEY_ID=...
   R2_SECRET_ACCESS_KEY=...
   POSTGRES_CONNECTION_STRING=...

   # Frontend
   VITE_CLERK_PUBLISHABLE_KEY=pk_...
   VITE_BACKEND_URL=http://localhost:8000
   ```

### Local Development Steps
1. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Install backend dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. Initialize database:
   ```bash
   ./bin/init_remote_db.sh
   ```

4. Start development servers:
   - Frontend: `npm run dev` (Vite dev server)
   - Backend: `python main.py` (FastAPI server)
   - Optional: `docker-compose up` (Full stack)

5. Development URLs:
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Testing
- Backend tests in `test_postgresql.py`
- Frontend testing setup through Vite

## Caching Strategy

Cache management is implemented in the `/cache/` directory, handling:
- API response caching
- Asset caching
- Search result optimization

## Contributing Guidelines

1. Fork the repository
2. Create feature branch
3. Follow existing code structure
4. Ensure all tests pass
5. Submit pull request

## Security Considerations

1. Authentication and Authorization:
   - JWT token validation through Clerk
   - Role-based access control for resources
   - Session management and timeout handling
   - Rate limiting for API endpoints

2. Data Security:
   - Environment-based secrets management
   - Encrypted storage of sensitive data
   - Secure communication over HTTPS
   - Data encryption in transit and at rest

3. API Security:
   - CORS configuration with allowed origins
   - Input validation and sanitization
   - Request rate limiting
   - Error handling without sensitive data exposure

4. Payment Security:
   - Stripe integration for secure payments
   - PCI compliance through Stripe
   - Secure webhook handling
   - Customer data protection

5. Infrastructure Security:
   - Docker container security
   - Network access controls
   - Regular security updates
   - Secure cloud configuration

## Monitoring and Logging

1. Application Logging:
   - Structured logging configuration in `backend/logging.conf`
   - Different log levels (INFO, ERROR, DEBUG)
   - Request/response logging
   - Error and exception tracking

2. Performance Monitoring:
   - API endpoint response times
   - Database query performance
   - Resource utilization metrics
   - Cache hit/miss rates

3. Error Tracking:
   - Comprehensive error logging
   - Stack trace collection
   - Error notification system
   - Error rate monitoring

4. System Health:
   - Health check endpoints
   - Database connection monitoring
   - External service dependency checks
   - Resource usage tracking

This implementation design serves as a living document and should be updated as the application evolves. Developers should refer to specific component documentation for detailed implementation details.
