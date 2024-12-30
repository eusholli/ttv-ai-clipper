# Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/.env .
COPY frontend/ .
RUN npm run build

# Final stage
FROM python:3.11-slim

# Build-time arguments for versioning
ARG BUILD_VERSION="0.0.5"
ARG BUILD_DATE="2024-12-29T23:18:12Z"

# Add labels with version info
LABEL org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.title="TTV AI Clipper" \
      org.opencontainers.image.description="Frontend + Backend Application" \
      org.opencontainers.image.vendor="Hollingworth LLC"

# Set version as environment variable
ENV APP_VERSION=${BUILD_VERSION}

WORKDIR /app

# Set noninteractive frontend
ENV DEBIAN_FRONTEND=noninteractive

# Install PostgreSQL and other dependencies in a single layer
RUN apt-get update && \
    apt-get install -y vim curl gnupg2 lsb-release && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/postgresql-keyring.gpg] http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/postgresql.list && \
    apt-get update && \
    apt-get install -y \
        nginx \
        postgresql-16 \
        postgresql-client-16 \
        postgresql-16-pgvector \
        python3-venv \
        procps \
        build-essential \
        gcc \
        g++ \
        && rm -rf /var/lib/apt/lists/*

# Setup Python environment
ENV VIRTUAL_ENV=/app/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Setup backend
# Install slow packages first - this layer will be cached
COPY backend/requirements-slow.txt .
RUN pip install --no-cache-dir -r requirements-slow.txt && \
    python -m spacy download en_core_web_sm

# Install remaining requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

    # Create required directories with proper permissions
RUN mkdir -p /var/run/postgresql /var/log/postgresql /var/log/nginx /var/log/fastapi && \
    chown -R postgres:postgres /var/run/postgresql /var/log/postgresql && \
    touch /var/log/fastapi/access.log /var/log/fastapi/error.log && \
    chown -R www-data:www-data /var/log/nginx /var/log/fastapi

# Initialize PostgreSQL database
RUN mkdir -p /var/lib/postgresql/data && \
    chown -R postgres:postgres /var/lib/postgresql/data && \
    su postgres -c "/usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/data" && \
    echo "host all all 0.0.0.0/0 md5" >> /var/lib/postgresql/data/pg_hba.conf && \
    echo "listen_addresses='*'" >> /var/lib/postgresql/data/postgresql.conf && \
    # Add optimized PostgreSQL configuration
    echo "max_connections = 100" >> /var/lib/postgresql/data/postgresql.conf && \
    echo "shared_buffers = 128MB" >> /var/lib/postgresql/data/postgresql.conf && \
    echo "work_mem = 4MB" >> /var/lib/postgresql/data/postgresql.conf && \
    echo "maintenance_work_mem = 64MB" >> /var/lib/postgresql/data/postgresql.conf && \
    echo "effective_cache_size = 384MB" >> /var/lib/postgresql/data/postgresql.conf

# Copy frontend build
COPY --from=frontend-build /frontend/dist /app/static

COPY backend/ .
COPY urls.zip .

# Configure Nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Copy startup script
COPY start.sh .
COPY stop.sh .
RUN chmod +x start.sh stop.sh

# logging config
COPY backend/logging.conf .
RUN mkdir -p /var/log/fastapi /var/log/postgresql && \
    chown -R www-data:www-data /var/log/fastapi && \
    chown -R postgres:postgres /var/log/postgresql

# Create a directory for any temporary files
RUN mkdir -p /tmp/app && chmod 777 /tmp/app

EXPOSE 80

# Use modified entrypoint script
CMD ["./start.sh"]
