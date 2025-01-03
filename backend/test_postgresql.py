import psycopg2
import numpy as np
from psycopg2.extensions import register_adapter, AsIs
import sys
from dotenv import load_dotenv
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',  # Simple format for Cloud Run logs
    handlers=[logging.StreamHandler(sys.stdout)]  # Output to stdout for Cloud Run
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

def addapt_numpy_array(numpy_array):
    return AsIs(f"'[{', '.join(map(str, numpy_array.tolist()))}]'")

# Register the NumPy array adapter
register_adapter(np.ndarray, addapt_numpy_array)

def test_postgresql_connection():
    """Test PostgreSQL connection and configuration"""
    try:
        # Connect to PostgreSQL
        db_name=os.getenv("DB_NAME")
        db_user=os.getenv("DB_USER")
        db_password=os.getenv("DB_PWD")
        db_host=os.getenv("DB_HOST", "localhost")
 
        # Extract project ID from the host
        project_id = db_host.split('.')[0]  # Gets 'ep-cool-poetry-a5t2k9y4'
        
        # Construct connection string with correct project name
        conn_str = f"postgresql://{db_user}:{db_password}@{db_host}:5432/{db_name}?sslmode=require&options=project%3D{project_id}"
        
        conn = psycopg2.connect(conn_str)
        logger.info("✓ Successfully connected to PostgreSQL")

        # Create a cursor
        cur = conn.cursor()

        # Test 1: Check pgvector extension
        cur.execute("SELECT * FROM pg_extension WHERE extname = 'vector';")
        if cur.fetchone() is not None:
            logger.info("✓ pgvector extension is installed")
        else:
            logger.error("✗ pgvector extension is not installed")
            sys.exit(1)

        # Test 2: Create a test table with vector column
        cur.execute("""
            DROP TABLE IF EXISTS test_vectors;
            CREATE TABLE test_vectors (
                id serial PRIMARY KEY,
                embedding vector(3)
            );
        """)
        logger.info("✓ Successfully created test table")

        # Test 3: Insert and query vector data
        test_vector = np.array([1.0, 2.0, 3.0])
        cur.execute(
            "INSERT INTO test_vectors (embedding) VALUES (%s) RETURNING id;",
            (test_vector,)
        )
        inserted_id = cur.fetchone()[0]
        logger.info("✓ Successfully inserted test vector")

        # Test 4: Query the inserted vector
        cur.execute("SELECT embedding FROM test_vectors WHERE id = %s;", (inserted_id,))
        retrieved_vector = cur.fetchone()[0]
        logger.info(f"✓ Successfully retrieved test vector: {retrieved_vector}")

        # Test 5: Test vector similarity search
        cur.execute("""
            SELECT embedding <-> %s as distance
            FROM test_vectors
            ORDER BY distance
            LIMIT 1;
        """, (test_vector,))
        distance = cur.fetchone()[0]
        logger.info(f"✓ Successfully performed similarity search, distance: {distance}")

        # Cleanup
        cur.execute("DROP TABLE test_vectors;")
        conn.commit()
        logger.info("✓ Cleanup completed")

        cur.close()
        conn.close()
        logger.info("\n✅ All PostgreSQL tests passed successfully!")
        return True

    except Exception as e:
        logger.error(f"\n✗ Error: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_postgresql_connection()
    sys.exit(0 if success else 1)
