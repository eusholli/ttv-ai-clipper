# Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Final stage
FROM python:3.11-slim

# Build-time arguments for versioning
ARG BUILD_VERSION="0.0.2"
ARG BUILD_DATE="2024-12-08T11:19:13Z"

# Add labels with version info
LABEL org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.title="TTV AI Clipper" \
      org.opencontainers.image.description="Frontend + Backend Application" \
      org.opencontainers.image.vendor="Hollingworth LLC"

# Set version as environment variable (accessible at runtime)
ENV APP_VERSION=${BUILD_VERSION}

WORKDIR /app

# Install Nginx, python3-venv, and debugging tools
RUN apt-get update && \
    apt-get install -y \
    nginx \
    python3-venv \
    procps \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
ENV VIRTUAL_ENV=/app/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy frontend build
COPY --from=frontend-build /frontend/dist /app/static

# Setup backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY r2_manager.py .
COPY transcript_metadata.pkl .
COPY transcript_search.index .

# Configure Nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Script to start both services
COPY start.sh .
RUN chmod +x start.sh

# Create log directories and set permissions
RUN mkdir -p /var/log/fastapi && \
    touch /var/log/fastapi/access.log && \
    touch /var/log/fastapi/error.log

EXPOSE 80

CMD ["./start.sh"]
