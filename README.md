# TTV AI Clipper

A full-stack application with a React frontend and Python FastAPI backend for processing and searching Telecom TV clips. Features include user authentication, clip transcription search, and cloud storage integration.

## Features

- User authentication (sign up, sign in, profile management)
- Clip transcription and search functionality
- Cloud storage integration with R2
- Subscription-based pricing tiers
- PostgreSQL database for data persistence
- Cloud deployment support (Google Cloud, Render)

## Repository Structure

```
.
├── frontend/                 # React frontend (Vite)
│   ├── src/                 # Frontend source code
│   │   ├── components/      # React components
│   │   │   ├── auth/       # Authentication components
│   │   │   └── pricing/    # Pricing components
│   │   ├── App.jsx         # Main application component
│   │   └── main.jsx        # Application entry point
│   ├── .env                # Development environment variables
│   ├── .env.production     # Production environment variables
│   └── package.json        # Frontend dependencies
├── backend/                 # Python FastAPI backend
│   ├── main.py             # Main backend application
│   ├── r2_manager.py       # R2 storage integration
│   ├── transcript_search.py # Clip transcription search
│   ├── video_utils.py      # Video processing utilities
│   └── requirements.txt     # Python dependencies
├── bin/                     # Shell scripts
│   ├── build.sh            # Build script for Docker image
│   ├── start.sh            # Container startup script
│   ├── stop.sh             # Container shutdown script
│   └── init_remote_db.sh   # Database initialization
├── Dockerfile              # Multi-stage Docker build configuration
├── Dockerfile.base         # Base image configuration
├── nginx.conf              # Nginx reverse proxy configuration
├── cloudbuild.yaml         # Google Cloud Build configuration
└── render.yaml            # Render deployment configuration
```

## Environment Setup

### Environment Variables

The application uses several environment variables for configuration:

1. Frontend (.env and .env.production):
   - Authentication settings
   - API endpoints
   - Environment-specific configurations

2. Backend (.env.example):
   - Database connection strings
   - R2 storage credentials
   - API keys and secrets

Copy `.env.example` to `.env` and configure the variables according to your environment.

## Development Setup

For local development:

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Building the Docker Image

The repository includes a `bin/build.sh` script that automates the Docker image building process:

```bash
# Run the build script
./bin/build.sh
```

This creates two Docker images:
- `ttv-ai-clipper:latest` - Latest version
- `ttv-ai-clipper:<version>` - Specific version (e.g., 1.0.2)

## Running the Docker Container

After building the image:

```bash
# Run the container
docker run -p 80:80 ttv-ai-clipper:latest
```

The application will be available at:
- Frontend: http://localhost
- Backend API: http://localhost/api

## Container Architecture

The Docker container:
- Uses a multi-stage build process
- Builds the React frontend with Node.js
- Sets up a Python environment with FastAPI
- Configures Nginx as a reverse proxy
- Runs both frontend and backend services
- Exposes port 80 for web access

### Services:
- Nginx: Serves static frontend files and proxies API requests
- FastAPI: Runs on port 8000 internally
- Frontend: Built static files served by Nginx

## Cloud Deployment

### Google Cloud Build
The application includes configuration for automated builds on Google Cloud Platform using Cloud Build (`cloudbuild.yaml`).

### Render
Deployment configuration for Render platform is provided in `render.yaml`, supporting both frontend and backend services.

## Database Management

PostgreSQL database initialization and management:
```bash
# Initialize remote database
./bin/init_remote_db.sh

# Run database tests
python backend/test_postgresql.py
```

## Version Information

The Docker image includes version information accessible via:
- Runtime environment variable: `APP_VERSION`
- Docker labels:
  - `org.opencontainers.image.version`
  - `org.opencontainers.image.created`
  - `org.opencontainers.image.revision`
