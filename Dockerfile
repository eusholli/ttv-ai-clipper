# Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/.env.production .env
COPY frontend/ .
RUN npm run build

# Final stage
FROM python:3.11-slim

# Build-time arguments for versioning
ARG BUILD_VERSION="0.0.6"
ARG BUILD_DATE="2025-01-02T17:41:47Z"

# Add labels with version info
LABEL org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.title="TTV AI Clipper" \
      org.opencontainers.image.description="Frontend + Backend Application" \
      org.opencontainers.image.vendor="Hollingworth LLC"

# Set version as environment variable
ENV APP_VERSION=${BUILD_VERSION}

# Final stage
FROM eusholli/ttv-ai-clipper-base:latest

WORKDIR /app

# Setup Python environment
ENV VIRTUAL_ENV=/app/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install remaining requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

    # Create required directories with proper permissions
RUN mkdir -p /var/log/nginx /var/log/fastapi /var/log/postgresql && \
    touch /var/log/fastapi/access.log /var/log/fastapi/error.log && \
    chown -R www-data:www-data /var/log/nginx /var/log/fastapi /var/log/postgresql

# Copy frontend build
COPY --from=frontend-build /frontend/dist /app/static

# Create backend package directory and copy files
RUN mkdir -p /app/backend
COPY backend/ /app/backend/
COPY urls.zip /app/
ENV PYTHONPATH=/app

# Configure Nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Copy startup and shutdown scripts
COPY bin/start.sh bin/stop.sh ./
RUN chmod +x start.sh stop.sh

# logging config
COPY backend/logging.conf .
RUN mkdir -p /var/log/fastapi && \
    chown -R www-data:www-data /var/log/fastapi

# Create directories for temporary files and Cloud SQL socket
RUN mkdir -p /tmp/app && chmod 777 /tmp/app && \
    mkdir -p /cloudsql && chmod 777 /cloudsql

EXPOSE 80

# Use modified entrypoint script
CMD ["./start.sh"]
