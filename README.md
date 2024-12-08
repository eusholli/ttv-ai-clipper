# TTV AI Clipper

A full-stack application with a React frontend and Python FastAPI backend, containerized with Docker.

## Repository Structure

```
.
├── frontend/               # React frontend (Vite)
│   ├── src/               # Frontend source code
│   └── package.json       # Frontend dependencies
├── backend/               # Python FastAPI backend
│   ├── main.py           # Main backend application
│   └── requirements.txt   # Python dependencies
├── build.sh              # Build script for Docker image
├── Dockerfile            # Multi-stage Docker build configuration
├── nginx.conf            # Nginx reverse proxy configuration
└── start.sh             # Container startup script
```

## Building the Docker Image

The repository includes a `build.sh` script that automates the Docker image building process. The script:

1. Sets version and build metadata
2. Creates a backup of the Dockerfile
3. Injects build-time variables
4. Builds the Docker image with proper tags

To build the Docker image:

```bash
# Make the build script executable
chmod +x build.sh

# Run the build script
./build.sh
```

This will create two Docker images:
- `ttv-ai-clipper:latest` - Latest version
- `ttv-ai-clipper:<version>` - Specific version (e.g., 1.0.2)

## Running the Docker Container

After building the image, run the container:

```bash
# Run the container
docker run -p 80:80 ttv-ai-clipper:latest
```

The application will be available at:
- Frontend: http://localhost
- Backend API: http://localhost/api

## Container Details

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

## Version Information

The Docker image includes version information accessible via:
- Runtime environment variable: `APP_VERSION`
- Docker labels:
  - `org.opencontainers.image.version`
  - `org.opencontainers.image.created`
  - `org.opencontainers.image.revision`
