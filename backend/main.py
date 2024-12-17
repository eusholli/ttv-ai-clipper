# backend/main.py
import os
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sentence_transformers import SentenceTransformer
import faiss
import pickle
import numpy as np
from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime
import re
from dotenv import load_dotenv
from r2_manager import R2Manager
import stripe
from typing import Optional
import json

# Load environment variables
load_dotenv()

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
if not stripe.api_key:
    raise ValueError("STRIPE_SECRET_KEY environment variable is required")
if not STRIPE_WEBHOOK_SECRET:
    raise ValueError("STRIPE_WEBHOOK_SECRET environment variable is required")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize R2Manager
r2_manager = R2Manager()

async def verify_clerk_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    return authorization.split(" ")[1]

class SubscriptionRequest(BaseModel):
    priceId: str
    customerId: Optional[str] = None

class TranscriptSearchSystem:
    def __init__(self, index_path='transcript_search.index', metadata_path='transcript_metadata.pkl'):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.dimension = 384
        self.load_or_create_index()

    def load_or_create_index(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                self.index = faiss.read_index(self.index_path)
                with open(self.metadata_path, 'rb') as f:
                    self.metadata, self.processed_hashes = pickle.load(f)
            except Exception as e:
                print(f"Error loading index: {str(e)}")
                self.create_new_index()
        else:
            self.create_new_index()

    def create_new_index(self):
        self.index = faiss.IndexFlatL2(self.dimension)
        self.metadata = []
        self.processed_hashes = set()

    def search(self, query: str, top_k: int = 5, selected_speaker: List[str] = None, 
              selected_date: List[str] = None, selected_title: List[str] = None,
              selected_company: List[str] = None) -> List[Dict]:
        if not self.metadata:
            return []
        
        # Get initial embeddings for all entries that match the filters
        filtered_indices = []
        filtered_metadata = []
        
        for idx, meta in enumerate(self.metadata):
            # Apply filters
            if selected_speaker and meta['speaker'] not in selected_speaker:
                continue
            if selected_date and meta['date'] not in selected_date:
                continue
            if selected_title and meta['title'] not in selected_title:
                continue
            if selected_company and meta['company'] not in selected_company:
                continue
            
            filtered_indices.append(idx)
            filtered_metadata.append(meta)
        
        if not filtered_indices:
            return []
        
        # Create a temporary index with only the filtered entries
        temp_index = faiss.IndexFlatL2(self.dimension)
        temp_vectors = [self.index.reconstruct(i) for i in filtered_indices]
        temp_index.add(np.array(temp_vectors).astype('float32'))
        
        # Perform search on filtered index
        query_vector = self.model.encode([query])[0]
        distances, indices = temp_index.search(
            np.array([query_vector]).astype('float32'), 
            min(top_k, len(filtered_metadata))
        )
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0:
                result = filtered_metadata[idx].copy()
                result['score'] = float(1 / (1 + distances[0][i]))  # Convert numpy float to Python float
                results.append(result)
                
        return sorted(results, key=lambda x: x['score'], reverse=True)

    def get_metadata_by_hash(self, segment_hash: str) -> Optional[Dict]:
        for meta in self.metadata:
            if meta['segment_hash'] == segment_hash:
                return meta
        return None

    def get_available_filters(self) -> Dict[str, List[str]]:
        if not self.metadata:
            return {
                "speakers": [],
                "dates": [],
                "titles": [],
                "companies": []
            }

        # Get unique values for each filter
        speakers = sorted(list(set(m['speaker'] for m in self.metadata)))
        dates = list(set(m['date'] for m in self.metadata))
        dates.sort(key=lambda x: datetime.strptime(x, "%b %d, %Y"), reverse=True)
        titles = sorted(list(set(m['title'] for m in self.metadata)))
        companies = sorted(list(set(m['company'] for m in self.metadata)))

        return {
            "speakers": speakers,
            "dates": dates,
            "titles": titles,
            "companies": companies
        }

# Initialize search system at startup
search_system = TranscriptSearchSystem()

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    selected_speaker: Optional[List[str]] = None
    selected_date: Optional[List[str]] = None
    selected_title: Optional[List[str]] = None
    selected_company: Optional[List[str]] = None

@app.get("/api/filters")
async def get_filters():
    """Get available filter options for the search interface"""
    return search_system.get_available_filters()

@app.post("/api/search")
async def search(request: SearchRequest):
    """Perform a search with the given parameters"""
    results = search_system.search(
        query=request.query,
        top_k=request.top_k,
        selected_speaker=request.selected_speaker,
        selected_date=request.selected_date,
        selected_title=request.selected_title,
        selected_company=request.selected_company
    )
    return {
        "results": results,
        "total_results": len(results)
    }

@app.get("/api/clip/{segment_hash}")
async def get_clip(segment_hash: str):
    """Get metadata for a specific clip by its hash"""
    clip = search_system.get_metadata_by_hash(segment_hash)
    if clip:
        return clip
    return {"error": "Clip not found"}

@app.get("/api/download/{segment_hash}")
async def download_clip(segment_hash: str):
    """Download a clip by its hash using R2 storage"""
    clip = search_system.get_metadata_by_hash(segment_hash)
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
                print(f"Created new Stripe customer: {customer_id}")
            except stripe.error.StripeError as e:
                print(f"Error creating Stripe customer: {str(e)}")
                raise HTTPException(status_code=400, detail="Failed to create Stripe customer")
        else:
            customer_id = request.customerId
            print(f"Using existing Stripe customer: {customer_id}")

        # Get the domain from environment variable
        domain = os.getenv("FRONTEND_URL", "http://localhost:5173")

        try:
            # Create Stripe Checkout Session
            checkout_session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=['card'],
                line_items=[{
                    'price': request.priceId,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=f'{domain}/user-profile?success=true',
                cancel_url=f'{domain}/user-profile?canceled=true',
                allow_promotion_codes=True,
            )
            print(f"Created checkout session for customer {customer_id}")
            
            return {
                "url": checkout_session.url,
                "customerId": customer_id
            }
        except stripe.error.StripeError as e:
            print(f"Error creating checkout session: {str(e)}")
            raise HTTPException(status_code=400, detail="Failed to create checkout session")
            
    except Exception as e:
        print(f"Unexpected error in create_checkout_session: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/create-portal-session")
async def create_portal_session(
    customer_id: str,
    token: str = Depends(verify_clerk_token)
):
    """Create a Stripe Customer Portal session"""
    try:
        if not customer_id:
            raise HTTPException(status_code=400, detail="Customer ID is required")
            
        print(f"Creating portal session for customer: {customer_id}")
        
        # Get the domain from environment variable
        domain = os.getenv("FRONTEND_URL", "http://localhost:5173")
        
        try:
            # Create the portal session
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=f'{domain}/user-profile'
            )
            print(f"Created portal session for customer {customer_id}")
            
            return {"url": session.url}
        except stripe.error.StripeError as e:
            print(f"Error creating portal session: {str(e)}")
            raise HTTPException(status_code=400, detail="Failed to create portal session")
            
    except Exception as e:
        print(f"Unexpected error in create_portal_session: {str(e)}")
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
            
        print(f"Checking subscription status for customer: {customer_id}")
        
        try:
            subscriptions = stripe.Subscription.list(
                customer=customer_id,
                status='active',
                limit=1
            )
            
            if not subscriptions.data:
                print(f"No active subscription found for customer {customer_id}")
                return {"status": "inactive"}
                
            subscription = subscriptions.data[0]
            print(f"Found active subscription for customer {customer_id}")
            
            return {
                "status": "active",
                "subscriptionId": subscription.id,
                "currentPeriodEnd": subscription.current_period_end,
                "cancelAtPeriodEnd": subscription.cancel_at_period_end
            }
        except stripe.error.StripeError as e:
            print(f"Error checking subscription status: {str(e)}")
            raise HTTPException(status_code=400, detail="Failed to check subscription status")
            
    except Exception as e:
        print(f"Unexpected error in get_subscription_status: {str(e)}")
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
            print("Error parsing webhook payload")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            print("Error verifying webhook signature")
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
                    print(f"New subscription created for customer {customer_id}")
                elif event['type'] == 'customer.subscription.updated':
                    print(f"Subscription updated for customer {customer_id}")
                elif event['type'] == 'customer.subscription.deleted':
                    print(f"Subscription cancelled for customer {customer_id}")

            except stripe.error.StripeError as e:
                print(f"Error processing subscription event: {str(e)}")
                return {"status": "error", "message": str(e)}

        return {"status": "success"}
        
    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/version")
async def get_version():
    return {
        "version": os.getenv("APP_VERSION", "unknown"),
        "api": "FastAPI Backend"
    }
