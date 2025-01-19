import asyncio
import json
import time
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import List

from .constants import CACHE_DIR, CLIP_DIR
from .content_processor import ContentProcessor
from .logging_setup import logger

async def process_urls(urls: List[str], batch_size: int = 3, max_retries: int = 3):
    """Process URLs in batches with concurrent execution"""
    processor = ContentProcessor(CACHE_DIR, CLIP_DIR)
    total_urls = len(urls)
    failed_urls = []
    
    for i in range(0, total_urls, batch_size):
        batch = urls[i:i + batch_size]
        batch_num = i//batch_size + 1
        total_batches = (total_urls + batch_size - 1)//batch_size
        logger.info(f"Processing batch {batch_num}/{total_batches}")
        
        start_time = time.time()
        tasks = [processor.process_url(url) for url in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for url, result in zip(batch, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to process {url}: {result}")
                failed_urls.append(url)
            elif result is None:
                logger.warning(f"No results for {url}")
                failed_urls.append(url)
            else:
                logger.info(f"Successfully processed {url}")
        
        batch_time = time.time() - start_time
        logger.info(f"Batch {batch_num}/{total_batches} completed in {batch_time:.2f}s")
        
        # Add a small delay between batches to prevent rate limiting
        if i + batch_size < total_urls:
            await asyncio.sleep(1)
    
    # Retry failed URLs
    if failed_urls:
        logger.info(f"Retrying {len(failed_urls)} failed URLs")
        retry_count = 0
        while failed_urls and retry_count < max_retries:
            retry_count += 1
            logger.info(f"Retry attempt {retry_count}/{max_retries}")
            
            retry_batch = failed_urls.copy()
            failed_urls.clear()
            
            tasks = [processor.process_url(url) for url in retry_batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for url, result in zip(retry_batch, results):
                if isinstance(result, Exception) or result is None:
                    failed_urls.append(url)
                else:
                    logger.info(f"Successfully processed {url} on retry {retry_count}")
            
            if failed_urls:
                logger.warning(f"{len(failed_urls)} URLs still failed after retry {retry_count}")
                await asyncio.sleep(5)  # Longer delay between retries
        
        if failed_urls:
            logger.error(f"Failed to process {len(failed_urls)} URLs after {max_retries} retries")
            for url in failed_urls:
                logger.error(f"Failed URL: {url}")

async def process_zip_file(zip_path: Path) -> None:
    """Process JSON files from a zip archive"""
    # Ensure CACHE_DIR exists
    CACHE_DIR.mkdir(exist_ok=True)
    
    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp())
    logger.info(f"Created temporary directory: {temp_dir}")
    
    try:
        # Extract zip contents
        logger.info(f"Extracting {zip_path} to temporary directory")
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(temp_dir)
        
        # Process each JSON file
        json_files = list(temp_dir.glob('*.json'))
        logger.info(f"Found {len(json_files)} JSON files to process")
        
        processor = ContentProcessor(CACHE_DIR, CLIP_DIR)
        for json_file in json_files:
            try:
                logger.info(f"Processing {json_file.name}")
                with open(json_file, 'r') as f:
                    json_data = json.load(f)
                processor.process_transcript(json_data, filename=json_file.name)
                logger.info(f"Successfully processed {json_file.name}")
                
                # Copy processed JSON file to CACHE_DIR
                shutil.copy2(json_file, CACHE_DIR / json_file.name)
                logger.info(f"Copied {json_file.name} to cache directory")
            except Exception as e:
                logger.error(f"Error processing {json_file.name}: {str(e)}")
                continue
    
    except Exception as e:
        logger.error(f"Error processing zip file: {str(e)}")
        raise
    
    finally:
        # Clean up temporary directory
        try:
            shutil.rmtree(temp_dir)
            logger.info("Cleaned up temporary directory")
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory: {str(e)}")

async def main():
    """Main entry point"""
    import sys
    
    # Check if zip file argument is provided
    if len(sys.argv) > 1 and sys.argv[1].endswith('.zip'):
        zip_path = Path(sys.argv[1])
        if not zip_path.exists():
            logger.error(f"Error: Zip file {zip_path} not found.")
            return
        
        logger.info(f"Processing zip file: {zip_path}")
        try:
            await process_zip_file(zip_path)
            logger.info("Zip file processing complete")
            return
        except Exception as e:
            logger.error(f"Failed to process zip file: {str(e)}")
            return
    
    # Default behavior - process URLs from file
    url_file = Path("dsp-urls-one.txt")
    if not url_file.exists():
        logger.error(f"Error: {url_file} not found.")
        return

    urls = url_file.read_text().strip().split('\n')
    if not urls:
        logger.error("No URLs found in input file.")
        return

    start_time = time.time()
    total_urls = len(urls)
    logger.info(f"Starting processing of {total_urls} URLs")
    
    try:
        await process_urls(urls)
    except Exception as e:
        logger.error(f"Fatal error during processing: {e}")
    finally:
        total_time = time.time() - start_time
        logger.info(f"Processing complete in {total_time:.2f}s. Check logs for details.")
        
        # Create zip file of cache json files
        with zipfile.ZipFile('urls.zip', 'w') as zipf:
            for json_file in CACHE_DIR.glob('*.json'):
                zipf.write(json_file, json_file.name)
        logger.info("Created urls.zip with all cache JSON files")
        
        # Print summary
        processor = ContentProcessor(CACHE_DIR, CLIP_DIR)
        successful = sum(1 for url in urls if (processor.get_cached_url(url)[1]).exists())
        failed = total_urls - successful
        logger.info(f"Summary:")
        logger.info(f"- Total URLs: {total_urls}")
        logger.info(f"- Successfully processed: {successful}")
        logger.info(f"- Failed: {failed}")
        logger.info(f"- Success rate: {(successful/total_urls)*100:.1f}%")
        logger.info(f"- Average time per URL: {total_time/total_urls:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
