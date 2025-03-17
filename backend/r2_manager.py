import os
import logging
import sys
from pathlib import Path
from functools import lru_cache
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class R2Manager:
    def __init__(self):
        """Initialize R2 manager with credentials from environment variables"""
        # Load environment variables
        load_dotenv()
        
        # Get credentials from env vars
        self.account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID') 
        self.access_key_id = os.getenv('CLOUDFLARE_ACCESS_KEY_ID')
        self.secret_access_key = os.getenv('CLOUDFLARE_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('CLOUDFLARE_BUCKET_NAME')
        # Define storage limit (10GB in bytes)
        self.storage_limit = 10 * 1024 * 1024 * 1024
        
        # Validate required environment variables
        if not all([self.account_id, self.access_key_id, 
                   self.secret_access_key, self.bucket_name]):
            raise ValueError("Missing required credentials. Check environment variables.")
        
        # s3_client will be initialized lazily
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy initialization of R2 client"""
        if self._s3_client is None:
            endpoint = f'https://{self.account_id}.r2.cloudflarestorage.com'
            logger.info(f"Connecting to endpoint: {endpoint}")
            self._s3_client = boto3.client(
                service_name='s3',
                endpoint_url=endpoint,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name='auto'  # R2 doesn't use regions, but boto3 requires this
            )
        return self._s3_client

    @lru_cache(maxsize=128)
    def get_total_space_used(self) -> int:
        """
        Calculate total space used in the R2 bucket
        
        Returns:
            int: Total space used in bytes
        """
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name)
            total_size = 0
            
            for obj in response.get('Contents', []):
                total_size += obj['Size']
                
            return total_size
            
        except ClientError as e:
            logger.error(f"Error calculating total space: {str(e)}")
            return 0

    def file_exists(self, object_name: str) -> bool:
        """
        Check if a file already exists in the R2 bucket
        
        Args:
            object_name (str): The name of the object to check
            
        Returns:
            bool: True if file exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=object_name)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"Error checking file existence: {str(e)}")
            raise

    @staticmethod
    @lru_cache(maxsize=128)
    def _get_content_type(file_path: str) -> str:
        """Determine content type based on file extension"""
        extension = Path(file_path).suffix.lower()
        content_types = {
            '.mp4': 'video/mp4',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.webm': 'video/webm'
        }
        return content_types.get(extension, 'application/octet-stream')

    def upload_file(self, file_path: str, object_name: str = None) -> bool:
        """
        Upload a file to Cloudflare R2 storage if it doesn't already exist and if under storage limit
        
        Args:
            file_path (str): Path to the file to upload
            object_name (str): S3 object name (if different from file_path)
            
        Returns:
            bool: True if file was uploaded successfully or already exists, False otherwise
        """
        # If object_name not specified, use file name
        if object_name is None:
            object_name = Path(file_path).name
            
        try:
            # Verify file exists and is readable
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return False

            # Check if file already exists in bucket
            if self.file_exists(object_name):
                logger.info(f"File {object_name} already exists in bucket {self.bucket_name}")
                return True

            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Check if adding this file would exceed storage limit
            total_used = self.get_total_space_used()
            if total_used + file_size > self.storage_limit:
                logger.error(f"Upload would exceed storage limit of {self.storage_limit/1024/1024/1024:.2f}GB. " +
                           f"Current usage: {total_used/1024/1024/1024:.2f}GB, " +
                           f"File size: {file_size/1024/1024/1024:.2f}GB")
                return False

            # Upload file with content type detection
            content_type = self._get_content_type(file_path)
            self.s3_client.upload_file(
                file_path, 
                self.bucket_name, 
                object_name,
                ExtraArgs={'ContentType': content_type}
            )
            
            logger.info(f"Successfully uploaded {file_path} to {self.bucket_name}/{object_name}")
            return True
            
        except ClientError as e:
            logger.error(f"Upload failed: {str(e)}")
            return False

    @lru_cache(maxsize=128)
    def list_videos(self):
        """
        List all videos in the bucket
        
        Returns:
            list: List of video filenames in the bucket
        """
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name)
            videos = []
            
            for obj in response.get('Contents', []):
                if obj['Key'].lower().endswith(('.mp4', '.mov', '.avi', '.webm')):
                    videos.append(obj['Key'])
                    
            return videos
            
        except ClientError as e:
            logger.error(f"Error listing videos: {str(e)}")
            return []

    def generate_presigned_url(self, object_name: str, expiration: int = 3600):
        """
        Generate a presigned URL for video access
        
        Args:
            object_name (str): Name of the object in the bucket
            expiration (int): URL expiration time in seconds (default: 1 hour)
            
        Returns:
            str: Presigned URL or None if error
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': object_name
                },
                ExpiresIn=expiration
            )
            return url
            
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            return None

    def get_video_content(self, url: str):
        """
        Download video content from presigned URL
        
        Args:
            url (str): Presigned URL to download from
            
        Returns:
            bytes: Video content or None if error
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            logger.error(f"Error downloading video: {str(e)}")
            return None

    def get_video_url_and_content(self, object_name: str, expiration: int = 3600):
        """
        Get both presigned URL and video content for an object
        
        Args:
            object_name (str): Name of the object in the bucket
            expiration (int): URL expiration time in seconds (default: 1 hour)
            
        Returns:
            tuple: (presigned_url, video_content) or (None, None) if error
        """
        url = self.generate_presigned_url(object_name, expiration)
        if url:
            content = self.get_video_content(url)
            return url, content
        return None, None

    def delete_file(self, clip_name: str) -> bool:
        """
        Delete a specific file from the R2 bucket
        
        Args:
            clip_name (str): Name of the file to delete
            
        Returns:
            bool: True if file was deleted successfully, False otherwise
        """
        try:
            # Check if file exists before attempting to delete
            if not self.file_exists(clip_name):
                logger.warning(f"File {clip_name} not found in bucket {self.bucket_name}")
                return False
                
            # Delete the file
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=clip_name
            )
            logger.info(f"Successfully deleted {clip_name} from bucket {self.bucket_name}")
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting file {clip_name}: {str(e)}")
            return False

    def delete_files_by_prefix(self, prefix: str) -> int:
        """
        Delete all files in the bucket that start with the given prefix
        
        Args:
            prefix (str): Prefix to match against object names
            
        Returns:
            int: Number of files deleted
        """
        try:
            # List all objects with the prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' not in response:
                logger.info(f"No files found with prefix: {prefix}")
                return 0
                
            # Prepare objects for deletion
            objects = [{'Key': obj['Key']} for obj in response['Contents']]
            deleted_count = len(objects)
            
            if objects:
                # Delete the objects
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': objects}
                )
                logger.info(f"Deleted {deleted_count} files with prefix: {prefix}")
            
            return deleted_count
            
        except ClientError as e:
            logger.error(f"Error deleting files with prefix {prefix}: {str(e)}")
            raise

    def delete_all_objects(self, bucket_name: str) -> int:
        """
        Delete all objects in the specified bucket
        
        Args:
            bucket_name (str): Name of the bucket to clear
            
        Returns:
            int: Number of objects deleted
        """
        try:
            total_deleted = 0
            continuation_token = None
            
            # Use pagination to handle buckets with more than 1000 objects
            while True:
                # List objects with pagination
                list_kwargs = {'Bucket': bucket_name}
                if continuation_token:
                    list_kwargs['ContinuationToken'] = continuation_token
                
                response = self.s3_client.list_objects_v2(**list_kwargs)
                
                if 'Contents' not in response:
                    if total_deleted == 0:
                        logger.info(f"No objects found in bucket: {bucket_name}")
                    break
                
                # Prepare objects for deletion (max 1000 per request)
                objects = [{'Key': obj['Key']} for obj in response['Contents']]
                batch_count = len(objects)
                
                if objects:
                    # Delete the objects
                    delete_response = self.s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': objects}
                    )
                    
                    # Check for errors in the delete response
                    if 'Errors' in delete_response and delete_response['Errors']:
                        for error in delete_response['Errors']:
                            logger.error(f"Error deleting {error.get('Key')}: {error.get('Code')} - {error.get('Message')}")
                        batch_count -= len(delete_response['Errors'])
                    
                    total_deleted += batch_count
                    logger.info(f"Deleted {batch_count} objects from bucket: {bucket_name}")
                
                # Check if there are more objects to list
                if response.get('IsTruncated', False):
                    continuation_token = response.get('NextContinuationToken')
                else:
                    break
            
            logger.info(f"Total objects deleted from bucket {bucket_name}: {total_deleted}")
            return total_deleted
            
        except ClientError as e:
            logger.error(f"Error deleting all objects from bucket {bucket_name}: {str(e)}")
            raise


def main():
    """
    Main function to run when the script is executed directly.
    Asks for a bucket name and confirmation before deleting all objects in the bucket.
    """
    print("R2 Bucket Cleanup Utility")
    print("-------------------------")
    print("WARNING: This will delete ALL objects in the specified bucket.")
    print("Make sure you have the correct R2 credentials in your environment variables.")
    print()
    
    # Get bucket name from user
    bucket_name = input("Enter the bucket name: ").strip()
    if not bucket_name:
        print("Error: Bucket name cannot be empty.")
        sys.exit(1)
    
    # Ask for confirmation
    confirmation = input(f"Are you sure you want to delete ALL objects in bucket '{bucket_name}'? (yes/no): ").strip().lower()
    
    if confirmation != "yes":
        print("Operation cancelled.")
        sys.exit(0)
    
    try:
        # Initialize R2Manager
        r2_manager = R2Manager()
        
        # Override the bucket name with the user-provided one
        original_bucket = r2_manager.bucket_name
        r2_manager.bucket_name = bucket_name
        
        print(f"Deleting all objects in bucket '{bucket_name}'...")
        deleted_count = r2_manager.delete_all_objects(bucket_name)
        
        if deleted_count > 0:
            print(f"Successfully deleted {deleted_count} objects from bucket '{bucket_name}'.")
        else:
            print(f"No objects found in bucket '{bucket_name}'.")
            
    except ValueError as e:
        print(f"Error: {str(e)}")
        print("Make sure your environment variables are set correctly.")
        sys.exit(1)
    except ClientError as e:
        print(f"AWS/R2 Error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
