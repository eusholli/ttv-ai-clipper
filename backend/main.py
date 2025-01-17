# backend/main.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, HTTPException, Header, Depends, Request, BackgroundTasks, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from dotenv import load_dotenv
from backend.r2_manager import R2Manager
import stripe
from typing import Optional
from backend.transcript_search import TranscriptSearch
from backend.job_manager import JobManager, Job
from backend.workflow_manager import WorkflowManager
from backend.models import JobStatus, WorkflowState
from typing import List, Optional, Dict, Any
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Email configuration
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL")

# Check each SMTP variable individually
if not SMTP_SERVER:
    logger.warning("SMTP_SERVER not configured. Email functionality will be disabled.")
if not SMTP_USERNAME:
    logger.warning("SMTP_USERNAME not configured. Email functionality will be disabled.")
if not SMTP_PASSWORD:
    logger.warning("SMTP_PASSWORD not configured. Email functionality will be disabled.")
if not FROM_EMAIL:
    logger.warning("FROM_EMAIL not configured. Email functionality will be disabled.")

if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL]):
    logger.warning("Some email configuration variables are missing. Email functionality will be disabled.")

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
if not stripe.api_key:
    raise ValueError("STRIPE_SECRET_KEY environment variable is required")
if not STRIPE_WEBHOOK_SECRET:
    raise ValueError("STRIPE_WEBHOOK_SECRET environment variable is required")

# Initialize managers
app = FastAPI()
job_manager = JobManager()
workflow_manager = WorkflowManager()

async def verify_clerk_token(authorization: Optional[str] = Header(None)):
    """Verify Clerk JWT token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization.split(" ")[1]
    
    # Get Clerk public key from environment
    clerk_jwt_key = os.getenv("CLERK_JWT_KEY")
    if not clerk_jwt_key:
        raise HTTPException(status_code=500, detail="Clerk JWT key not configured")
        
    try:
        # Verify token using Clerk's public key
        import jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        
        try:
            # Format the key string with proper PEM structure
            key_lines = [
                "-----BEGIN PUBLIC KEY-----",
                clerk_jwt_key.strip(),  # Remove any whitespace
                "-----END PUBLIC KEY-----"
            ]
            formatted_key = "\n".join(key_lines)
            
            # Load the public key
            public_key = serialization.load_pem_public_key(
                formatted_key.encode(),
                backend=default_backend()
            )
        except ValueError as e:
            logger.error(f"Failed to load public key: {str(e)}")
            raise HTTPException(status_code=500, detail="Invalid public key format")
            
        try:
            # Verify and decode the token
            decoded = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"]
            )
            return decoded
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
            
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        raise HTTPException(status_code=500, detail="Token verification failed")

# Job management request models
class CreateJobRequest(BaseModel):
    url: str
    user_email: EmailStr

# Job management endpoints
@app.post("/api/admin/jobs", response_model=Job)
async def create_job(
    request: CreateJobRequest,
    background_tasks: BackgroundTasks,
    token: str = Depends(verify_clerk_token)
):
    """Create a new ingest job"""
    job = await job_manager.create_job(request.url, request.user_email)
    background_tasks.add_task(job_manager.process_job, job.id)
    return job

@app.get("/api/admin/jobs/{job_id}", response_model=Job)
async def get_job(
    job_id: int,
    token: str = Depends(verify_clerk_token)
):
    """Get job status by ID"""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.get("/api/admin/jobs", response_model=List[Job])
def list_jobs(
    user_email: Optional[str] = None,
    limit: int = 100,
    token: str = Depends(verify_clerk_token)
):
    """List all jobs with optional filtering"""
    return job_manager.list_jobs(user_email, limit)

# New workflow management endpoints
@app.get("/api/admin/jobs/{job_id}/details")
async def get_job_details(
    job_id: int,
    token: str = Depends(verify_clerk_token)
):
    """Get detailed job information including metadata and transcript"""
    try:
        return workflow_manager.get_job_details(job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

class MetadataUpdate(BaseModel):
    title: Optional[str]
    date: Optional[str]
    youtube_id: Optional[str]
    source: Optional[str]

@app.put("/api/admin/jobs/{job_id}/metadata")
async def update_metadata(
    job_id: int,
    metadata: MetadataUpdate,
    token: str = Depends(verify_clerk_token)
):
    """Update job metadata"""
    try:
        await workflow_manager.update_metadata(job_id, metadata.dict())
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class TranscriptSegment(BaseModel):
    segment_hash: str
    text: str
    speaker: Optional[str]
    company: Optional[str]
    start_time: int
    end_time: int
    subjects: List[str]

@app.put("/api/admin/jobs/{job_id}/transcript")
async def update_transcript(
    job_id: int,
    segments: List[TranscriptSegment],
    token: str = Depends(verify_clerk_token)
):
    """Update job transcript segments"""
    try:
        await workflow_manager.update_transcript(job_id, [s.dict() for s in segments])
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/admin/jobs/{job_id}/content")
async def delete_job_content(
    job_id: int,
    token: str = Depends(verify_clerk_token)
):
    """Delete all content related to a job including cache files"""
    try:
        await workflow_manager.delete_content(job_id)            
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/admin/jobs/archive")
async def delete_archive(
    token: str = Depends(verify_clerk_token)
):
    """Delete all archived jobs (completed, failed, deleted) and their associated content"""
    try:
        await workflow_manager.delete_content_archive()
        return {
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error deleting archive: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/jobs/{job_id}/log")
async def get_job_log(
    job_id: int,
    token: str = Depends(verify_clerk_token)
):
    """Get the latest log file for a job"""
    log_content = workflow_manager.get_latest_log(job_id)
    if not log_content:
        raise HTTPException(status_code=404, detail="No log file found")
    return {"log": log_content}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize R2Manager
try:
    r2_manager = R2Manager()
except Exception as e:
    logger.error(f"Failed to initialize R2Manager: {e}")
    # Continue without r2_manager functionality
    r2_manager = None

async def verify_clerk_token(authorization: Optional[str] = Header(None)):
    """Verify Clerk JWT token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization.split(" ")[1]
    
    # Get Clerk public key from environment
    clerk_jwt_key = os.getenv("CLERK_JWT_KEY")
    if not clerk_jwt_key:
        raise HTTPException(status_code=500, detail="Clerk JWT key not configured")
        
    try:
        # Verify token using Clerk's public key
        import jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        
        try:
            # Format the key string with proper PEM structure
            key_lines = [
                "-----BEGIN PUBLIC KEY-----",
                clerk_jwt_key.strip(),  # Remove any whitespace
                "-----END PUBLIC KEY-----"
            ]
            formatted_key = "\n".join(key_lines)
            
            # Load the public key
            public_key = serialization.load_pem_public_key(
                formatted_key.encode(),
                backend=default_backend()
            )
        except ValueError as e:
            logger.error(f"Failed to load public key: {str(e)}")
            raise HTTPException(status_code=500, detail="Invalid public key format")
            
        try:
            # Verify and decode the token
            decoded = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"]
            )
            return decoded

        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
            
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        raise HTTPException(status_code=500, detail="Token verification failed")
            
class SubscriptionRequest(BaseModel):
    priceId: str
    customerId: Optional[str] = None
    returnUrl: str  # Base URL for success/cancel redirects

# Initialize search systems
try:
    transcript_search = TranscriptSearch()
except Exception as e:
    logger.error(f"Failed to initialize TranscriptSearch: {e}")
    # Continue without search functionality
    transcript_search = None

# transcript_search = TranscriptSearch()

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    selected_speaker: Optional[List[str]] = None
    selected_date: Optional[List[str]] = None
    selected_title: Optional[List[str]] = None
    selected_company: Optional[List[str]] = None
    selected_subject: Optional[List[str]] = None

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/db-test")
async def test_db():
    try:
        transcript_search.cursor.execute('SELECT 1')
        return {"status": "connected"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/filters")
async def get_filters():
    """Get available filter options for the search interface"""
    return transcript_search.get_available_filters()

@app.post("/api/search")
async def search(request: SearchRequest):
    """Perform a search with the given parameters"""
    # Map request parameters to hybrid_search filters
    filters = {}
    if request.selected_speaker:
        filters['speakers'] = request.selected_speaker
    if request.selected_company:
        filters['companies'] = request.selected_company
    if request.selected_title:
        filters['title'] = request.selected_title[0] if request.selected_title else None
    if request.selected_date:
        # Convert date strings to datetime objects for date range
        dates = [datetime.strptime(d, "%b %d, %Y") for d in request.selected_date]
        if dates:
            filters['date_range'] = (min(dates), max(dates))
    if request.selected_subject:
        filters['subjects'] = request.selected_subject

    results = transcript_search.hybrid_search(
        search_text=request.query,
        filters=filters,
        semantic_weight=0.7,  # Default to balanced semantic/text search
        limit=request.top_k
    )

    # Map similarity score to score for backwards compatibility
    for result in results:
        result['score'] = result.pop('similarity')

    return {
        "results": results,
        "total_results": len(results)
    }

@app.get("/api/clip/{segment_hash}")
async def get_clip(segment_hash: str):
    """Get metadata for a specific clip by its hash"""
    clip = transcript_search.get_metadata_by_hash(segment_hash)
    if clip:
        return clip
    return {"error": "Clip not found"}

@app.get("/api/download/{segment_hash}")
async def download_clip(segment_hash: str):
    """Download a clip by its hash using R2 storage"""
    clip = transcript_search.get_metadata_by_hash(segment_hash)
    if not clip or 'download' not in clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    
    # Get the filename from the download path
    filename = os.path.basename(clip['download'])
    
    # Get the video content from R2
    url, content = r2_manager.get_video_url_and_content(filename)
    if not content:
        raise HTTPException(status_code=404, detail="Clip file not found in storage")
    
    return Response(
        content=content,
        media_type='video/mp4',
        headers={
            'Content-Disposition': f'attachment; filename=clip-{segment_hash}.mp4'
        }
    )

@app.post("/api/create-checkout-session")
async def create_checkout_session(
    request: SubscriptionRequest,
    token: str = Depends(verify_clerk_token)
):
    """Create a Stripe Checkout session for subscription"""
    try:
        # If no customer ID provided, create a new customer
        if not request.customerId:
            try:
                customer = stripe.Customer.create()
                customer_id = customer.id
                logger.info(f"Created new Stripe customer: {customer_id}")
            except stripe.error.StripeError as e:
                logger.error(f"Error creating Stripe customer: {str(e)}")
                raise HTTPException(status_code=400, detail="Failed to create Stripe customer")
        else:
            customer_id = request.customerId
            logger.info(f"Using existing Stripe customer: {customer_id}")

        try:
            # Create Stripe Checkout Session with provided return URL
            checkout_session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=['card'],
                line_items=[{
                    'price': request.priceId,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=f'{request.returnUrl}/user-profile?success=true',
                cancel_url=f'{request.returnUrl}/user-profile?canceled=true',
                allow_promotion_codes=True,
            )
            logger.info(f"Created checkout session for customer {customer_id}")
            
            return {
                "url": checkout_session.url,
                "customerId": customer_id
            }
        except stripe.error.StripeError as e:
            logger.error(f"Error creating checkout session: {str(e)}")
            raise HTTPException(status_code=400, detail="Failed to create checkout session")
            
    except Exception as e:
        logger.error(f"Unexpected error in create_checkout_session: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

class PortalRequest(BaseModel):
    customerId: str
    returnUrl: str  # Base URL for portal return

@app.post("/api/create-portal-session")
async def create_portal_session(
    request: PortalRequest,
    token: str = Depends(verify_clerk_token)
):
    """Create a Stripe Customer Portal session"""
    try:
        if not request.customerId:
            raise HTTPException(status_code=400, detail="Customer ID is required")
            
        logger.info(f"Creating portal session for customer: {request.customerId}")
        
        try:
            # Create the portal session with provided return URL
            session = stripe.billing_portal.Session.create(
                customer=request.customerId,
                return_url=f'{request.returnUrl}/user-profile'
            )
            logger.info(f"Created portal session for customer {request.customerId}")
            
            return {"url": session.url}
        except stripe.error.StripeError as e:
            logger.error(f"Error creating portal session: {str(e)}")
            raise HTTPException(status_code=400, detail="Failed to create portal session")
            
    except Exception as e:
        logger.error(f"Unexpected error in create_portal_session: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/subscription-status")
async def get_subscription_status(
    customer_id: str,
    token: str = Depends(verify_clerk_token)
):
    """Get a customer's subscription status"""
    try:
        if not customer_id:
            raise HTTPException(status_code=400, detail="Customer ID is required")
            
        logger.info(f"Checking subscription status for customer: {customer_id}")
        
        try:
            subscriptions = stripe.Subscription.list(
                customer=customer_id,
                status='active',
                limit=1
            )
            
            if not subscriptions.data:
                logger.info(f"No active subscription found for customer {customer_id}")
                return {"status": "inactive"}
                
            subscription = subscriptions.data[0]
            logger.info(f"Found active subscription for customer {customer_id}")
            
            return {
                "status": "active",
                "subscriptionId": subscription.id,
                "currentPeriodEnd": subscription.current_period_end,
                "cancelAtPeriodEnd": subscription.cancel_at_period_end
            }
        except stripe.error.StripeError as e:
            logger.error(f"Error checking subscription status: {str(e)}")
            raise HTTPException(status_code=400, detail="Failed to check subscription status")
            
    except Exception as e:
        logger.error(f"Unexpected error in get_subscription_status: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    try:
        # Get the raw body
        body = await request.body()
        # Get the Stripe signature from headers
        sig_header = request.headers.get('stripe-signature')
        
        try:
            # Verify the event
            event = stripe.Webhook.construct_event(
                body,
                sig_header,
                STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            logger.error("Error parsing webhook payload")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            logger.error("Error verifying webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")

        # Handle the event
        if event['type'].startswith('customer.subscription.'):
            subscription = event['data']['object']
            customer_id = subscription['customer']
            
            try:
                # Get the customer
                customer = stripe.Customer.retrieve(customer_id)
                
                # Handle different subscription events
                if event['type'] == 'customer.subscription.created':
                    logger.info(f"New subscription created for customer {customer_id}")
                elif event['type'] == 'customer.subscription.updated':
                    logger.info(f"Subscription updated for customer {customer_id}")
                elif event['type'] == 'customer.subscription.deleted':
                    logger.info(f"Subscription cancelled for customer {customer_id}")

            except stripe.error.StripeError as e:
                logger.error(f"Error processing subscription event: {str(e)}")
                return {"status": "error", "message": str(e)}

        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

class BatchEmailRequest(BaseModel):
    segment_hashes: List[str]

@app.post("/api/email-clips")
async def email_clips(
    request: BatchEmailRequest,
    token: str = Depends(verify_clerk_token)
):
    """Email multiple clips to the user's verified email address"""
    try:
        if not all([SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL]):
            raise HTTPException(status_code=503, detail="Email service not configured")

        # Get user's email from Clerk token
        user_email = token.get('email_address')
        if not user_email:
            logger.error(f"No email_address found in token: {token}")
            raise HTTPException(status_code=400, detail="No email address found in token")

        # Create email message
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = user_email
        msg['Subject'] = f"Your Requested Clips ({len(request.segment_hashes)} clips)"

        # Build email body with all clips
        body = "Here are your requested clips:\n\n"
        
        for segment_hash in request.segment_hashes:
            # Get clip metadata
            clip = transcript_search.get_metadata_by_hash(segment_hash)
            if not clip or 'download' not in clip:
                logger.warning(f"Clip not found: {segment_hash}")
                continue

            # Get the video URL from R2
            url, _ = r2_manager.get_video_url_and_content(os.path.basename(clip['download']))
            if not url:
                logger.warning(f"Clip URL not found: {segment_hash}")
                continue

            # Format start and end times as HH:MM:SS
            start_seconds = int(clip.get('start_time', 0))
            end_seconds = int(clip.get('end_time', 0))
            start_time = f"{start_seconds//3600:02d}:{(start_seconds%3600)//60:02d}:{start_seconds%60:02d}"
            end_time = f"{end_seconds//3600:02d}:{(end_seconds%3600)//60:02d}:{end_seconds%60:02d}"

            # Add clip details to body
            body += f"""
Clip: {clip.get('title', 'Untitled')}
Speaker: {clip.get('speaker', 'Unknown')}
Company: {clip.get('company', 'Unknown')}
Time: {start_time} - {end_time}
Quote: "{clip.get('text', 'No Transcript Available')}"
Download Link: {url}

"""

        body += "\nThese links will expire in 24 hours."
        msg.attach(MIMEText(body, 'plain'))

        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        return {"status": "success", "message": f"Email sent to {user_email}"}

    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@app.get("/api/version")
async def get_version():
    return {
        "version": os.getenv("APP_VERSION", "unknown"),
        "api": "FastAPI Backend"
    }
