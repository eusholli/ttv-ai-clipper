update # TTV AI Clipper - Product Context

## Why This Project Exists

TTV AI Clipper exists to solve the challenge of managing and searching through video content from Telecom TV, making it easier for users to find, share, and utilize specific segments of video content. The project serves as a specialized video content management system that focuses on making telecom-related video content more accessible and useful.

## Problems It Solves

1. **Content Accessibility**
   - Transforms long-form video content into searchable, bite-sized clips
   - Makes it easier to find specific information within video content
   - Enables sharing of precise video segments rather than entire videos

2. **Search and Discovery**
   - Provides advanced search capabilities across video transcripts
   - Supports filtering by speaker, company, date, title, and subject
   - Implements hybrid search combining semantic and text-based approaches

3. **Content Management**
   - Automates video processing and transcription workflows
   - Handles video storage and delivery through R2 cloud storage
   - Manages user access and permissions

4. **Content Distribution**
   - Enables clip downloading and sharing
   - Provides email functionality for sharing clips
   - Generates time-limited download links

5. **Monetization**
   - Implements subscription-based access through Stripe
   - Supports different pricing tiers
   - Handles payment processing and subscription management

## How It Works

### Core Architecture

1. **Frontend (React)**
   - User interface for searching and managing clips
   - Authentication using Clerk
   - Admin interface for content management
   - Responsive design for various devices

2. **Backend (FastAPI)**
   - RESTful API for all core functionality
   - Video processing and transcription
   - Search functionality
   - User management and authentication

3. **Storage**
   - R2 cloud storage for video content
   - PostgreSQL database for metadata and transcripts
   - Redis for job queue management

### Key Workflows

1. **Content Ingestion**
   - Admin uploads URLs through the admin interface
   - System processes videos and generates transcripts
   - Content is stored and indexed for searching

2. **Search and Discovery**
   - Users can search through transcripts
   - Advanced filtering options available
   - Results show relevant clip segments

3. **Clip Management**
   - Users can select and download clips
   - Email sharing functionality
   - Temporary download links generation

4. **Access Control**
   - User authentication via Clerk
   - Role-based access control
   - Subscription management through Stripe

### Performance Optimizations

1. **Database**
   - Connection pooling for better resource utilization
   - Proper transaction isolation levels
   - Statement timeouts for query management

2. **Processing**
   - Celery workers for background tasks
   - Multiple Uvicorn workers for API handling
   - Efficient resource utilization

3. **Caching**
   - Implements caching mechanisms
   - Optimized search queries
   - Efficient data retrieval patterns

This system provides a comprehensive solution for managing, searching, and sharing video content, with a focus on performance, scalability, and user experience.
