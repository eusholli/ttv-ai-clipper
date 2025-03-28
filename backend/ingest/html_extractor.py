# Removed 're' import as it's only used by the deleted extract_transcript method
from typing import Tuple, Optional

import backoff
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from .logging_setup import logger
from backend.video_utils import is_youtube_url, extract_youtube_id

class HtmlExtractor:
    """Handles fetching HTML and extracting metadata""" # Updated docstring

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

    # --- extract_transcript method removed ---
