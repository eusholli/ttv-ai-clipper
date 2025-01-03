import os
import sys
import logging
import numpy as np
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.client import ClientOptions
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',  # Simple format for Cloud Run logs
    handlers=[logging.StreamHandler(sys.stdout)]  # Output to stdout for Cloud Run
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

class SupabaseConnection:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL", "https://skmlggkecapuxcroqqby.supabase.co")
        self.supabase_key = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNrbWxnZ2tlY2FwdXhjcm9xcWJ5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTczNTg4MTUxNCwiZXhwIjoyMDUxNDU3NTE0fQ.mXiCDBPe3yH11cM0L_sLr0QEQ_XC4fdtHx9lY2nX3IM")
        self.client: Optional[Client] = None

    def connect(self) -> Client:
        """Establish connection to Supabase with retry logic"""
        if self.client is not None:
            return self.client

        try:
            self.client = create_client(
                self.supabase_url,
                self.supabase_key,
                options=ClientOptions(
                    postgrest_client_timeout=10,  # HTTP timeout for REST calls
                    storage_client_timeout=10,    # HTTP timeout for storage operations
                    schema="public",             # Default schema
                    headers={
                        "x-custom-header": "test-script"  # Custom header for tracking
                    }
                )
            )
            logger.info("✓ Successfully connected to Supabase")
            return self.client
        except Exception as e:
            logger.error(f"✗ Error connecting to Supabase: {str(e)}")
            raise

def test_supabase_connection() -> bool:
    """Test Supabase connection and vector operations"""
    conn = SupabaseConnection()
    
    try:
        # Initialize connection
        supabase = conn.connect()

        # Test 1: Create test table
        try:
            setup_sql = """
            do $$
            begin
                -- Drop the test table if it exists
                drop table if exists test_vectors;
                
                -- Create the test table
                create table test_vectors (
                    id bigint primary key generated always as identity,
                    embedding vector(3)
                );
            end $$;
            """
            response = supabase.rpc('exec_sql', {'sql': setup_sql}).execute()
            logger.info("✓ Successfully created test table")
            
        except Exception as e:
            logger.error(f"✗ Error setting up database: {str(e)}")
            raise

        # Test 2: Insert vector data
        test_vector = np.array([1.0, 2.0, 3.0]).tolist()
        try:
            response = supabase.table('test_vectors').insert({
                'embedding': test_vector
            }).execute()
            
            inserted_id = response.data[0]['id'] if response.data else None
            if inserted_id:
                logger.info("✓ Successfully inserted test vector")
            else:
                raise Exception("No ID returned from insert operation")

        except Exception as e:
            logger.error(f"✗ Error inserting vector: {str(e)}")
            raise

        # Test 3: Query the inserted vector
        try:
            response = supabase.table('test_vectors').select('embedding').eq('id', inserted_id).execute()
            if response.data and response.data[0]['embedding']:
                retrieved_vector = response.data[0]['embedding']
                logger.info(f"✓ Successfully retrieved test vector: {retrieved_vector}")
            else:
                raise Exception("No vector data found in query response")

        except Exception as e:
            logger.error(f"✗ Error querying vector: {str(e)}")
            raise

        # Test 4: Test vector similarity search using direct vector operator
        try:
            # Using raw SQL for similarity search since it handles the operator syntax properly
            sql = """
            select json_agg(
                json_build_object(
                    'id', id,
                    'embedding', embedding,
                    'distance', embedding <-> '[1,2,3]'::vector
                )
            )
            from (
                select id, embedding
                from test_vectors 
                order by embedding <-> '[1,2,3]'::vector
                limit 1
            ) t;
            """
            response = supabase.rpc('exec_sql_select', {'sql': sql}).execute()
            
            if response.data and response.data[0]:
                results = response.data[0]
                if results and len(results) > 0:
                    distance = results[0]['distance']
                    logger.info(f"✓ Successfully performed similarity search, distance: {distance}")
                else:
                    raise Exception("No similarity search results returned")
            else:
                raise Exception("Invalid response format from similarity search")

        except Exception as e:
            logger.error(f"✗ Error performing similarity search: {str(e)}")
            raise

        # Test 5: Cleanup - Drop the test table
        try:
            cleanup_sql = "drop table if exists test_vectors;"
            response = supabase.rpc('exec_sql', {'sql': cleanup_sql}).execute()
            logger.info("✓ Cleanup completed")
        except Exception as e:
            logger.error(f"✗ Error during cleanup: {str(e)}")
            raise

        logger.info("\n✅ All Supabase tests passed successfully!")
        return True

    except Exception as e:
        logger.error(f"\n✗ Test failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_supabase_connection()
    sys.exit(0 if success else 1)
