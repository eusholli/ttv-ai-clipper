import yt_dlp
import time
import sys
import os
import json
import torch
import faster_whisper
from pyannote.audio import Pipeline
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv

# Add a comment explaining the implementation
"""
This script uses YouTubeTranscriptApi to fetch transcripts directly from YouTube with speaker diarization.
It combines the accuracy of YouTube's official transcripts with PyAnnote's speaker diarization capabilities.
If YouTube transcripts are not available, it falls back to Whisper-Turbo for transcription.

Key advantages of this implementation:
1. Fast and accurate transcription using YouTube's official transcripts
2. Fallback to Whisper-Turbo when YouTube transcripts are unavailable
3. State-of-the-art speaker diarization with PyAnnote
4. Precise time-based alignment between transcript segments and speakers
5. Efficient processing of consecutive segments from the same speaker
6. Efficient GPU acceleration when using Whisper-Turbo fallback
"""

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    raise ValueError("HF_TOKEN environment variable is required")

def download_youtube_video(video_id):
    """
    Download a YouTube video if it doesn't already exist locally.
    
    Args:
        video_id (str): YouTube video ID
        
    Returns:
        str: Path to the downloaded video file
    """
    # Check if the audio file already exists
    if os.path.exists(f"{video_id}.wav"):
        print(f"Audio file {video_id}.wav already exists. Skipping download.")
        return f"{video_id}.wav"
        
    # Check if any video file already exists for this ID
    video_extensions = ['.mp4', '.webm', '.mkv']
    for ext in video_extensions:
        if os.path.exists(f"{video_id}{ext}"):
            print(f"Video file {video_id}{ext} already exists. Skipping download.")
            return f"{video_id}{ext}"
    
    # Download the video
    print(f"Downloading video {video_id}...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{video_id}.%(ext)s',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f'https://www.youtube.com/watch?v={video_id}'])
    
    # Find the downloaded file
    for ext in video_extensions:
        if os.path.exists(f"{video_id}{ext}"):
            return f"{video_id}{ext}"
    
    raise FileNotFoundError(f"Downloaded video file for {video_id} not found")

def extract_audio(cache_dir, video_id):
    """
    Extract audio from video file if audio doesn't already exist.
    
    Args:
        cache_dir (str): Cache directory for temporary files
        video_id (str): YouTube video ID
        
    Returns:
        str: Path to the audio file
    """
    audio_file = f"{video_id}.wav"
    
    # Check if audio file already exists
    audio_path = f"{cache_dir}/{audio_file}"

    if os.path.exists(audio_path):
        print(f"{audio_path} already cached.")
        return audio_path
    else:   
        # Extract audio using yt-dlp if video ends with supported extension
        # Otherwise, assume it's already been processed to the best format
        print(f"Fetching audio for {video_id}...")
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'outtmpl': f'{cache_dir}/{video_id}.%(ext)s',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
    
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio extraction failed. {audio_path} not found.")
    
    return audio_path

def transcribe_audio_with_pyano(audio_path, hf_token, verbose=True):
    """
    Perform speaker diarization using PyAnnote's speaker diarization pipeline.
    Process the diarization to create a list of entries containing speaker id, 
    start of speaking in seconds, duration of speaking and end of speaking,
    for entries following each other by the same speaker.
    
    Checks for existing diarization JSON file before running the pipeline.
    
    Args:
        audio_path (str): Path to the audio file
        hf_token (str): Hugging Face authentication token
        verbose (bool): Whether to show detailed progress
        
    Returns:
        dict: Structured diarization result with speaker segments
    """
    try:
        # Generate diarization JSON filename based on audio path
        diarization_json_path = f"{os.path.splitext(audio_path)[0]}_diarization.json"
        
        # Check if diarization JSON already exists
        if os.path.exists(diarization_json_path):
            print(f"Found existing diarization at {diarization_json_path}. Loading from file...")
            with open(diarization_json_path, "r") as f:
                return json.load(f)
        
        if not hf_token or hf_token.strip() == "" or hf_token == "HUGGINGFACE_ACCESS_TOKEN_GOES_HERE":
            print("\nERROR: A valid Hugging Face token is required for speaker diarization.")
            print("\nHow to get a Hugging Face token:")
            print("1. Create an account at https://huggingface.co/join")
            print("2. Go to https://huggingface.co/settings/tokens to create a new token")
            print("3. Visit https://huggingface.co/pyannote/speaker-diarization-3.1 and accept the model terms")
            print("4. Use the token when running the script: --hf_token YOUR_TOKEN_HERE\n")
            return None
            
        # instantiate the pipeline
        print("Loading PyAnnote speaker diarization pipeline...")
        from pyannote.audio import Pipeline
        from pyannote.audio.pipelines.utils.hook import ProgressHook
        
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token)
                
        # run the pipeline on the audio file with progress hook
        print(f"Running speaker diarization on {audio_path}...")
        with ProgressHook() as hook:
            diarization = pipeline(audio_path, hook=hook)
                
        # First, collect all raw segments from diarization
        raw_segments = []
        for segment, track, speaker in diarization.itertracks(yield_label=True):
            # Extract speaker ID from the label (format is usually "speaker_1", "speaker_2", etc.)
            speaker_id = speaker.split('_')[1] if '_' in speaker else speaker
            
            raw_segments.append({
                "start": segment.start,
                "end": segment.end,
                "duration": segment.end - segment.start,
                "speaker": f"Speaker {speaker_id}",
                "speaker_id": speaker_id,
                # PyAnnote doesn't provide per-segment confidence, so we use a default
                "confidence": 0.9
            })
        
        # Sort segments by start time
        raw_segments.sort(key=lambda x: x["start"])
        
        # Now group consecutive segments by the same speaker
        structured_segments = []
        if not raw_segments:
            return {"segments": []}
            
        current_segment = raw_segments[0].copy()
        
        for i in range(1, len(raw_segments)):
            segment = raw_segments[i]
            
            # If same speaker and segments are close enough (within 0.5 seconds), merge them
            if (segment["speaker_id"] == current_segment["speaker_id"]):  
                # Extend the current segment
                current_segment["end"] = segment["end"]
                current_segment["duration"] = current_segment["end"] - current_segment["start"]
            else:
                # Add the completed segment to our results and start a new one
                structured_segments.append(current_segment)
                current_segment = segment.copy()
        
        # Add the last segment
        structured_segments.append(current_segment)
        
        print(f"Processed {len(raw_segments)} raw segments into {len(structured_segments)} merged speaker segments")
        
        # Save the processed diarization to JSON
        result = {"segments": structured_segments}
        print(f"Saving processed diarization to {diarization_json_path}...")
        with open(diarization_json_path, "w") as f:
            json.dump(result, f, indent=4)
        
        return result
        
    except Exception as e:
        print(f"ERROR in PyAnnote diarization: {str(e)}")
        print("\nTo fix this issue:")
        print("1. Make sure you have a valid Hugging Face token")
        print("2. Visit https://huggingface.co/pyannote/speaker-diarization-3.1 and accept the user conditions")
        print("3. Run the script again with your valid token")
        return None

def fetch_youtube_transcript(video_id, language="en", verbose=True):
    """
    Fetch transcript from YouTube using YouTubeTranscriptApi.
    
    Args:
        video_id (str): YouTube video ID
        language (str, optional): Language code to force specific language detection
        verbose (bool): Whether to show detailed progress
        
    Returns:
        dict: Transcription result with timestamps
    """
    try:
        # Display progress message
        if verbose:
            print(f"Fetching transcript for video {video_id} using YouTubeTranscriptApi...")
        
        # Fetch transcript
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
        
        if not transcript_list:
            print("Warning: No transcript found for the video.")
            return {
                "text": "",
                "segments": [],
                "language": language
            }
        
        # Convert YouTube transcript format to a format similar to Whisper output
        # for compatibility with existing code
        full_text = " ".join([item["text"] for item in transcript_list])
        
        # Create segments in a format compatible with our existing pipeline
        segments = []
        for i, item in enumerate(transcript_list):
            segments.append({
                "id": i,
                "seek": 0,
                "start": item["start"],
                "end": item["start"] + item["duration"],
                "text": item["text"],
                "tokens": [],
                "temperature": 0.0,
                "avg_logprob": 0.0,
                "compression_ratio": 1.0,
                "no_speech_prob": 0.0,
                # Create word-level timestamps by treating each transcript segment as a single word
                # This is a simplification since YouTube API doesn't provide word-level timestamps
                "words": [{
                    "word": item["text"],
                    "start": item["start"],
                    "end": item["start"] + item["duration"],
                    "probability": 1.0
                }]
            })
        
        transcription = {
            "text": full_text,
            "segments": segments,
            "language": language
        }
        
        # Add metadata
        transcription["processing_metadata"] = {
            "source": "youtube_transcript_api",
            "processing_time": None  # Will be filled by caller if needed
        }
        
        return transcription
        
    except Exception as e:
        print(f"Error fetching YouTube transcript: {str(e)}")
        # Provide error details but return a structured response that won't break downstream
        return {
            "text": "",
            "segments": [],
            "error": str(e),
            "error_type": type(e).__name__
        }

def transcribe_audio_with_whisper_turbo(audio_path, model_size="medium", language="en", verbose=True):
    """
    Transcribe audio using Whisper-Turbo (faster-whisper) with enhanced configuration and word-level timestamps.
    
    Args:
        audio_path (str): Path to the audio file
        model_size (str): Whisper model size (tiny, base, small, medium, large, large-v2, large-v3)
        language (str, optional): Language code to force specific language detection
        verbose (bool): Whether to show detailed progress
        
    Returns:
        dict: Transcription result with enhanced metadata
    """
    try:
        # Display progress message
        print(f"Transcribing audio with Whisper-Turbo {model_size} model...")
        
        # Determine compute device
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "float32"
        
        if verbose:
            print(f"Using device: {device}, compute type: {compute_type}")
            
        # Load model for initial ASR using faster-whisper (Whisper-Turbo)
        print("Loading Whisper-Turbo ASR model...")
        model = faster_whisper.WhisperModel(model_size, device=device, compute_type=compute_type)
        
        # Transcribe audio
        if verbose:
            print("Performing ASR transcription...")
            
        # Set up ASR options
        beam_size = 5
        
        # Force English if no language is specified (to avoid issues with unsupported languages)
        forced_language = language if language else "en"
        
        # Run ASR on audio file
        segments_generator, info = model.transcribe(
            audio_path,
            beam_size=beam_size,
            language=forced_language,  # Force language to avoid detection issues
            word_timestamps=True,      # Enable word timestamps
            vad_filter=True,           # Filter out non-speech
            vad_parameters=dict(min_silence_duration_ms=500)  # Adjust VAD parameters
        )
        
        # Convert faster-whisper output to compatible format
        segments = []
        all_segments = list(segments_generator)  # Convert generator to list to use it multiple times
        
        if not all_segments:
            print("Warning: No segments detected in the audio.")
            return {
                "text": "",
                "segments": [],
                "language": forced_language
            }
        
        for segment in all_segments:
            words = []
            for word in segment.words:
                words.append({
                    "word": word.word,
                    "start": word.start,
                    "end": word.end,
                    "probability": word.probability
                })
                
            segments.append({
                "id": len(segments),
                "seek": 0,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "tokens": [],
                "temperature": 0.0,
                "avg_logprob": 0.0,
                "compression_ratio": 1.0,
                "no_speech_prob": 0.0,
                "words": words
            })
        
        transcription = {
            "text": " ".join([segment.text for segment in all_segments]),
            "segments": segments,
            "language": forced_language
        }
        
        # Add metadata
        transcription["processing_metadata"] = {
            "model_size": model_size,
            "device_used": device,
            "processing_time": None,  # Will be filled by caller if needed
            "whisper_turbo_version": faster_whisper.__version__ if hasattr(faster_whisper, "__version__") else "unknown"
        }
        
        return transcription
        
    except Exception as e:
        print(f"Error during Whisper-Turbo transcription: {str(e)}")
        # Provide error details but return a structured response that won't break downstream
        return {
            "text": "",
            "segments": [],
            "error": str(e),
            "error_type": type(e).__name__
        }

def align_speakers_to_words(diarization, transcription, overlap_threshold=0.5):
    """
    For each entry in diarization, find the text segments in transcription that overlap
    with the start and end timestamps and concatenate all that have the best fit.
    Creates a new field in diarization called "text" that contains this concatenated text.
    
    Args:
        diarization (dict): PyAnnote diarization result with speaker segments
        transcription (dict): Whisper-Turbo transcription with word-level timestamps
        overlap_threshold (float): Minimum overlap ratio to consider a segment as overlapping
        
    Returns:
        list: Words with assigned speakers, and diarization segments with added text
    """
    print("Aligning speakers to words based on timestamps...")
    
    if not diarization or "segments" not in diarization or not diarization["segments"]:
        print("Warning: No speaker segments found in diarization result.")
        return []
    
    # Extract all words from all segments for traditional word-level alignment
    words_with_speakers = []
    
    # Sort speaker segments by start time
    speaker_segments = sorted(diarization["segments"], key=lambda x: x["start"])
    
    # First, add text field to each diarization segment
    for speaker_segment in speaker_segments:
        speaker_start = speaker_segment["start"]
        speaker_end = speaker_segment["end"]
        speaker_duration = speaker_end - speaker_start
        
        # Find all transcription segments that overlap with this speaker segment
        matching_text_segments = []
        
        for segment in transcription.get("segments", []):
            segment_start = segment["start"]
            segment_end = segment["end"]
            
            # Calculate overlap between transcription segment and speaker segment
            overlap_start = max(segment_start, speaker_start)
            overlap_end = min(segment_end, speaker_end)
            overlap_duration = max(0, overlap_end - overlap_start)
            
            # Calculate overlap ratio relative to segment duration
            segment_duration = segment_end - segment_start
            segment_overlap_ratio = overlap_duration / segment_duration if segment_duration > 0 else 0
            
            # Calculate overlap ratio relative to speaker duration
            speaker_overlap_ratio = overlap_duration / speaker_duration if speaker_duration > 0 else 0
            
            # Consider this segment if either overlap ratio meets the threshold
            if segment_overlap_ratio >= overlap_threshold or speaker_overlap_ratio >= overlap_threshold:
                matching_text_segments.append({
                    "text": segment["text"],
                    "start": segment_start,
                    "end": segment_end,
                    "overlap_duration": overlap_duration,
                    "overlap_ratio": max(segment_overlap_ratio, speaker_overlap_ratio)
                })
        
        # Sort matching segments by overlap ratio (best matches first)
        matching_text_segments.sort(key=lambda x: x["overlap_ratio"], reverse=True)
        
        # Concatenate text from all matching segments
        concatenated_text = " ".join([segment["text"] for segment in matching_text_segments])
        
        # Add the concatenated text to the speaker segment
        speaker_segment["text"] = concatenated_text
    
    # Now perform traditional word-level alignment for backward compatibility
    # Process each segment in the transcription
    for segment in transcription.get("segments", []):
        # Skip segments without words
        if "words" not in segment or not segment["words"]:
            continue
        
        # Process each word in the segment
        for word in segment["words"]:
            word_start = word["start"]
            word_end = word["end"]
            word_duration = word_end - word_start
            
            # Find the best matching speaker segment
            best_speaker = None
            best_overlap = 0
            
            for speaker_segment in speaker_segments:
                # Calculate overlap between word and speaker segment
                overlap_start = max(word_start, speaker_segment["start"])
                overlap_end = min(word_end, speaker_segment["end"])
                overlap_duration = max(0, overlap_end - overlap_start)
                
                # Calculate overlap ratio relative to word duration
                overlap_ratio = overlap_duration / word_duration if word_duration > 0 else 0
                
                # Update best match if this overlap is better
                if overlap_ratio > best_overlap:
                    best_overlap = overlap_ratio
                    best_speaker = speaker_segment
            
            # Assign speaker if overlap meets threshold
            if best_speaker and best_overlap >= overlap_threshold:
                speaker = best_speaker["speaker"]
                speaker_id = best_speaker.get("speaker_id", "unknown")
            else:
                # Default speaker if no good match
                speaker = "Unknown Speaker"
                speaker_id = "unknown"
            
            # Add word with speaker information
            words_with_speakers.append({
                "word": word["word"],
                "start": word_start,
                "end": word_end,
                "speaker": speaker,
                "speaker_id": speaker_id,
                "confidence": word.get("probability", 0.9)
            })
    
    return words_with_speakers

def group_by_speaker(words_with_speakers):
    """
    Group words by speaker turns with enhanced formatting.
    
    Args:
        words_with_speakers (list): Words with speaker information
        
    Returns:
        list: Transcript segments grouped by speaker with proper formatting
    """
    print("Grouping text by speaker turns...")
    transcript = []
    current_speaker = None
    current_speaker_id = None
    current_text = ""
    segment_start = 0
    
    # Define known speakers (can be expanded or loaded from a configuration)
    # This will help with proper naming in the transcript
    speaker_names = {
        # Template for custom speaker names - can be filled manually or from config
        # "1": "John Doe, Company Name", 
    }
    
    for word_data in words_with_speakers:
        if current_speaker is None:
            # Initialize first segment
            current_speaker = word_data["speaker"]
            current_speaker_id = word_data.get("speaker_id", "unknown")
            segment_start = word_data["start"]
            current_text = word_data["word"]
        elif current_speaker != word_data["speaker"]:
            # Speaker changed, format and save the current segment
            
            # Format speaker name according to transcript.txt style
            # Either use a custom name if defined, or use the default Speaker X format
            display_name = speaker_names.get(
                str(current_speaker_id), 
                current_speaker
            )
            
            # Format timestamp in HH:MM:SS format as seen in transcript.txt
            timestamp = format_timestamp(segment_start)
            
            transcript.append({
                "speaker": current_speaker,
                "speaker_id": current_speaker_id,
                "display_name": display_name,
                "timestamp": timestamp,
                "start": segment_start,
                "end": word_data["start"],
                "text": current_text.strip()
            })
            
            # Start new segment
            current_speaker = word_data["speaker"]
            current_speaker_id = word_data.get("speaker_id", "unknown")
            segment_start = word_data["start"]
            current_text = word_data["word"]
        else:
            # Same speaker, add to current text
            current_text += " " + word_data["word"]
    
    # Add the last segment
    if current_speaker:
        # Format last segment the same way
        display_name = speaker_names.get(
            str(current_speaker_id), 
            current_speaker
        )
        timestamp = format_timestamp(segment_start)
        
        transcript.append({
            "speaker": current_speaker,
            "speaker_id": current_speaker_id,
            "display_name": display_name,
            "timestamp": timestamp,
            "start": segment_start,
            "end": words_with_speakers[-1]["end"],
            "text": current_text.strip()
        })
    
    return transcript

def format_timestamp(seconds):
    """
    Format time in seconds to HH:MM:SS format for transcript display.
    
    Args:
        seconds (float): Time in seconds
        
    Returns:
        str: Formatted time string
    """
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    seconds = int(seconds % 60)
    return f"({hours:02d}:{minutes:02d}:{seconds:02d})"

def generate_transcript_from_diarization(diarization):
    """
    Generate transcript directly from diarization segments that include text.
    
    Args:
        diarization (dict): Diarization result with speaker segments and text
            
    Returns:
        list: Transcript segments formatted for output
    """
    print("Generating transcript from diarization segments...")
    
    if not diarization or "segments" not in diarization or not diarization["segments"]:
        print("Warning: No speaker segments found in diarization result.")
        return []
    
    transcript = []
    
    # Define known speakers (can be expanded or loaded from a configuration)
    speaker_names = {}
    
    # Sort speaker segments by start time
    speaker_segments = sorted(diarization["segments"], key=lambda x: x["start"])
    
    for segment in speaker_segments:
        # Skip segments without text
        if "text" not in segment or not segment["text"].strip():
            continue
            
        speaker = segment["speaker"]
        speaker_id = segment.get("speaker_id", "unknown")
        start_time = segment["start"]
        
        # Format speaker name according to transcript.txt style
        # Either use a custom name if defined, or use the default Speaker X format
        display_name = speaker_names.get(
            str(speaker_id), 
            speaker
        )
        
        # Format timestamp in HH:MM:SS format
        timestamp = format_timestamp(start_time)
        
        transcript.append({
            "speaker": speaker,
            "speaker_id": speaker_id,
            "display_name": display_name,
            "timestamp": timestamp,
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"].strip()
        })
    
    return transcript

def create_transcript_string(transcript, video_id):
    """
    Create and return a formatted transcript string.
    
    Args:
        transcript (list): Processed transcript
        video_id (str): YouTube video ID
        
    Returns:
        str: Formatted transcript text
    """
    # Create a human-readable formatted transcript string
    transcript_string = ""
    
    for segment in transcript:
        # Format: Speaker Name, Company Name (timestamp):
        transcript_string += f"{segment['display_name']}, Company {segment['speaker_id']} {segment['timestamp']}:\n"
        transcript_string += f"{segment['text']}\n"
        transcript_string += "\n"  # Add blank line between speakers for readability
    
    # Print formatted transcript
    print("\nTranscript:")
    for segment in transcript:
        print(f"{segment['display_name']} {segment['timestamp']}:")
        print(f"{segment['text']}\n")
        
    return transcript_string

def _get_youtube_transcript(cache_dir, video_id, hf_token, model_size="medium", language="en", overlap_threshold=0.5):
    """
    Main function to get transcript from YouTube video using YouTubeTranscriptApi for transcription
    and PyAnnote for speaker diarization.
    
    Args:
        video_id (str): YouTube video ID
        hf_token (str): Hugging Face authentication token
        model_size (str): Whisper model size (only used if falling back to Whisper)
        cleanup (bool): Whether to remove temporary files
        language (str, optional): Force specific language for transcription
        overlap_threshold (float): Minimum overlap ratio to assign a speaker to a word
        
    Returns:
        str: The formatted transcript text
    """
    
    # Step 1: Download the video for audio extraction (needed for diarization)
    # video_path = download_youtube_video(video_id)
    
    # Step 2: Extract audio for diarization
    audio_path = extract_audio(cache_dir, video_id)
    
    # Step 3: Fetch transcript from YouTube
    print(f"Fetching transcript from YouTube for video {video_id}...")
    transcription = fetch_youtube_transcript(video_id, language)
    
    # If YouTube transcript fails, fall back to Whisper
    if not transcription or "segments" not in transcription or not transcription["segments"]:
        print("YouTube transcript not available. Falling back to Whisper-Turbo...")
        transcription = transcribe_audio_with_whisper_turbo(audio_path, model_size, language)
        
        if not transcription or "segments" not in transcription or not transcription["segments"]:
            print("Transcription failed or contains no segments.")
            return []
    
    # Step 4: Perform speaker diarization with PyAnnote
    print("Using PyAnnote for speaker diarization...")
    diarization = transcribe_audio_with_pyano(audio_path, hf_token)
    
    # Check if diarization succeeded
    if diarization is None:
        print("Speaker diarization failed. Returning transcription without speaker information.")
        # Create a simplified transcript without speaker information
        simplified_transcript = []
        for segment in transcription.get("segments", []):
            simplified_transcript.append({
                "speaker": "Unknown Speaker",
                "speaker_id": "unknown",
                "display_name": "Unknown Speaker",
                "timestamp": format_timestamp(segment.get("start", 0)),
                "start": segment.get("start", 0),
                "end": segment.get("end", 0),
                "text": segment.get("text", "").strip()
            })
        return create_transcript_string(simplified_transcript, video_id)
    
    # Step 5: Align speakers with words using time-based matching
    # This now adds text to each diarization segment
    align_speakers_to_words(diarization, transcription, overlap_threshold)
    
    # Step 6: Generate transcript directly from diarization segments
    transcript = generate_transcript_from_diarization(diarization)
    
    # Step 7: Create and return the transcript string
    return create_transcript_string(transcript, video_id)

def test_transcript(video_id, hf_token, model_size="large-v3", language=None, force_refresh=False, overlap_threshold=0.5):
    """
    Test function to easily generate transcripts for different videos.
    
    Args:
        video_id (str): YouTube video ID
        hf_token (str): Hugging Face authentication token
        model_size (str): Whisper model size
        language (str, optional): Force specific language code
        force_refresh (bool): Whether to regenerate transcript even if it exists
        overlap_threshold (float): Minimum overlap ratio to assign a speaker to a word
    """
    # If force refresh, delete existing transcript and diarization files
    if force_refresh:
        json_path = f"{video_id}_transcript.json"
        txt_path = f"{video_id}_transcript.txt"
        diarization_json_path = f"{video_id}_diarization.json"
        
        if os.path.exists(json_path):
            print(f"Removing existing transcript: {json_path}")
            os.remove(json_path)
        if os.path.exists(txt_path):
            print(f"Removing existing transcript text: {txt_path}")
            os.remove(txt_path)
        if os.path.exists(diarization_json_path):
            print(f"Removing existing diarization: {diarization_json_path}")
            os.remove(diarization_json_path)
    
    # Process the transcript
    print(f"Processing transcript for video ID: {video_id}")
    print(f"Using YouTubeTranscriptApi for transcription (with Whisper {model_size} as fallback)")
    print(f"Using PyAnnote for speaker diarization")
    
    start_time = time.time()
    transcript = _get_youtube_transcript(
        cache_dir = 'cache',
        video_id=video_id,
        hf_token=HF_TOKEN,
   )
    
    processing_time = time.time() - start_time
    print(f"\nTranscript processing completed in {processing_time:.2f} seconds")
    print(f"Transcript generated successfully as a string")
    print(transcript)
    
    return transcript

def get_youtube_transcript(cache_dir, video_id):
    """
    Main function to get transcript from YouTube video using YouTubeTranscriptApi for transcription
    and PyAnnote for speaker diarization.
    
    Args:
        cache_dir (str): Cache directory for temporary files
        video_id (str): YouTube video ID
        hf_token (str): Hugging Face authentication token
        model_size (str): Whisper model size (only used if falling back to Whisper)
        cleanup (bool): Whether to remove temporary files
        language (str, optional): Force specific language for transcription
        overlap_threshold (float): Minimum overlap ratio to assign a speaker to a word
        
    Returns:
        str: The formatted transcript text
    """
    return _get_youtube_transcript(
        cache_dir = cache_dir,
        video_id=video_id,
        hf_token=HF_TOKEN,
    )


# Usage example
if __name__ == "__main__":
    import time
    import argparse
    
    # Set up command line argument parsing for easier usage
    parser = argparse.ArgumentParser(description="Generate transcripts from YouTube videos with speaker diarization using YouTubeTranscriptApi and PyAnnote")
    parser.add_argument("--video_id", default="idV4GQRflHM", help="YouTube video ID")
    parser.add_argument("--hf_token", help="Hugging Face token")
    parser.add_argument("--model", default="small", choices=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"], help="Whisper model size")
    parser.add_argument("--language", default="en", help="Force specific language (e.g., 'en' for English)")
    parser.add_argument("--force_refresh", action="store_true", help="Force regeneration of transcript")
    parser.add_argument("--gpu", action="store_true", help="Force use GPU if available")
    parser.add_argument("--overlap_threshold", type=float, default=0.5, help="Minimum overlap ratio to assign a speaker to a word (0.0-1.0)")
    
    args = parser.parse_args()
    
    # If GPU flag is set, force CUDA usage if available
    if args.gpu and torch.cuda.is_available():
        torch.set_default_device('cuda')
        print("Forcing GPU usage for acceleration")
    
    # Run the test function
    transcript = test_transcript(
        video_id=args.video_id,
        hf_token=args.hf_token,
        model_size=args.model,
        language=args.language,
        force_refresh=args.force_refresh,
        overlap_threshold=args.overlap_threshold
    )
