import re
from typing import Tuple, Optional

import backoff
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from .logging_setup import logger
from backend.video_utils import is_youtube_url, extract_youtube_id

class HtmlExtractor:
    """Handles fetching and extracting content from HTML pages"""

    @backoff.on_exception(
        backoff.expo,
        (PlaywrightTimeoutError, Exception),
        max_tries=3
    )
    async def fetch_html(self, url: str) -> str:
        """Fetch HTML content from URL using Playwright"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until='networkidle')
                await page.wait_for_timeout(2000)
                return await page.content()
            except Exception as e:
                logger.error(f"Error fetching {url}: {str(e)}")
                raise
            finally:
                await browser.close()

    def is_direct_youtube_url(self, url: str) -> bool:
        """Check if URL is a direct YouTube URL"""
        return is_youtube_url(url)
    
    def extract_youtube_id_from_url(self, url: str) -> Optional[str]:
        """Extract YouTube ID directly from URL"""
        return extract_youtube_id(url)
    
    def extract_metadata(self, html_content: str, url: str = None) -> Tuple[str, str, str]:
        """
        Extract title, date and youtube_id from HTML content
        
        Args:
            html_content: HTML content to extract metadata from
            url: Original URL, used for direct YouTube URL detection
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract title from meta tags or h1
            title = None
            meta_title = soup.find('meta', property='og:title')
            if meta_title:
                title = meta_title.get('content')
            if not title:
                h1 = soup.find('h1')
                if h1:
                    title = h1.text.strip()
            
            # Extract date - look for common date patterns
            date = None
            date_meta = soup.find('meta', property=['article:published_time', 'datePublished'])
            if date_meta:
                date = date_meta.get('content', '').split('T')[0]  # Get just the date part
            
            # Extract YouTube ID from meta tags or URL in content
            youtube_id = None
            
            # First check if we have a direct YouTube URL
            if url and self.is_direct_youtube_url(url):
                youtube_id = self.extract_youtube_id_from_url(url)
                logger.info(f"Extracted YouTube ID {youtube_id} directly from URL {url}")
            
            # If not found, try meta tags
            if not youtube_id:
                yt_meta = soup.find('meta', property='og:video')
                if yt_meta:
                    video_url = yt_meta.get('content', '')
                    if 'youtube.com' in video_url or 'youtu.be' in video_url:
                        # Extract ID from URL
                        if 'v=' in video_url:
                            youtube_id = video_url.split('v=')[1].split('&')[0]
                        else:
                            youtube_id = video_url.split('/')[-1]
            
            # If still not found, look for YouTube embeds in iframes
            if not youtube_id:
                iframes = soup.find_all('iframe')
                for iframe in iframes:
                    src = iframe.get('src', '')
                    if 'youtube.com/embed/' in src:
                        youtube_id = src.split('/embed/')[1].split('?')[0]
                        break
            
            return title, date, youtube_id
            
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            raise

    def extract_transcript(self, html_content: str) -> str:
        """Extract raw transcript text from HTML content using pattern matching"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # First try to find any div that contains text matching our transcript pattern
            # More flexible pattern that handles variations in spacing and punctuation
            transcript_pattern = re.compile(r'[A-Za-z\s]+\s*,\s*[A-Za-z\s]+\s*\([\s*\d{2}\s*:]+\)\s*:')
            
            # Convert HTML to text while preserving some structure
            text_content = soup.get_text('\n', strip=True)
            
            # Split into lines and look for the transcript pattern
            lines = text_content.split('\n')
            for i, line in enumerate(lines):
                if transcript_pattern.match(line):
                    # Found the start of transcript, join remaining lines
                    transcript_text = '\n'.join(lines[i:])
                    
                    # Clean up the transcript text
                    # Remove any content after a clear ending pattern (if exists)
                    end_patterns = [
                        'video transcripts are provided for reference only',
                        'Related content',
                        'Share this video',
                        'Comments',
                        'Additional resources',
                        'About the author',
                        'Read more',
                        'Subscribe',
                        'Follow us',
                        'More from',
                        'Tags:',
                        'Categories:',
                        'Share this:',
                        'Like this:'
                    ]
                    for pattern in end_patterns:
                        if pattern in transcript_text:
                            transcript_text = transcript_text.split(pattern)[0]
                    
                    return transcript_text.strip()
            
            # If pattern not found in plain text, try searching in HTML
            # This handles cases where the text might be split across elements
            all_text = []
            for element in soup.find_all(['div', 'p', 'span', 'article', 'section']):
                text = element.get_text(strip=True)
                if transcript_pattern.search(text):
                    # Found an element containing the pattern
                    # First try to get text from the element itself
                    transcript_element = element
                    
                    # If the text is too short, try parent elements
                    while transcript_element and len(transcript_element.get_text()) < 500:
                        transcript_element = transcript_element.parent
                        if not transcript_element:
                            break
                    
                    if transcript_element:
                        # Get text from the transcript element and its siblings
                        current = transcript_element
                        while current and len(all_text) < 100:
                            # Get text from current element
                            current_text = current.get_text(strip=True)
                            if current_text:
                                all_text.append(current_text)
                            
                            # Also check children if this is a container
                            for child in current.find_all(['div', 'p', 'span'], recursive=False):
                                child_text = child.get_text(strip=True)
                                if child_text and child_text not in all_text:
                                    all_text.append(child_text)
                            
                            # Move to next sibling
                            current = current.find_next_sibling()
                            
                            # Stop if we hit an element that likely indicates the end
                            if current and any(p.lower() in current.get_text().lower() for p in end_patterns):
                                break
                    break
            
            if all_text:
                combined_text = '\n'.join(all_text)
                # Clean up the combined text
                for pattern in end_patterns:
                    if pattern in combined_text:
                        combined_text = combined_text.split(pattern)[0]
                return combined_text.strip()
            
            raise Exception("Could not find transcript content matching expected pattern")
            
        except Exception as e:
            logger.error(f"Error extracting transcript: {str(e)}")
            raise
