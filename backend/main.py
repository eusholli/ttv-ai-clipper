# backend/main.py
import os
from fastapi import FastAPI, HTTPException
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

# Load environment variables
load_dotenv()

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

@app.get("/api/version")
async def get_version():
    return {
        "version": os.getenv("APP_VERSION", "unknown"),
        "api": "FastAPI Backend"
    }
