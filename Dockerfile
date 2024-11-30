# Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Final stage
FROM python:3.11-slim
WORKDIR /app

# Install Nginx
RUN apt-get update && apt-get install -y nginx && rm -rf /var/lib/apt/lists/*

# Copy frontend build
COPY --from=frontend-build /frontend/dist /app/static

# Setup backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .

# Configure Nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Script to start both services
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 80

CMD ["./start.sh"]
