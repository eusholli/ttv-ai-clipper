import psycopg2
import numpy as np
from psycopg2.extensions import register_adapter, AsIs
import sys
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

def addapt_numpy_array(numpy_array):
    return AsIs(f"'[{', '.join(map(str, numpy_array.tolist()))}]'")

# Register the NumPy array adapter
register_adapter(np.ndarray, addapt_numpy_array)

def test_postgresql_connection():
    """Test PostgreSQL connection and configuration"""
    try:
        # Check for required environment variables
        required_vars = ['DB_NAME', 'DB_USER', 'DB_PWD', 'DB_HOST']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

        conn = None    
        # Check if running in Cloud Run (INSTANCE_CONNECTION_NAME will be set)
        instance_connection_name = os.getenv('INSTANCE_CONNECTION_NAME')
        if instance_connection_name:
            # Use Unix domain socket for Cloud SQL
            db_socket_dir = '/cloudsql'
            cloud_sql_connection_name = os.getenv('INSTANCE_CONNECTION_NAME')
            
            conn = psycopg2.connect(
                dbname=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PWD'),
                host=f'{db_socket_dir}/{cloud_sql_connection_name}',
                connect_timeout=30
            )
        else:
            # Use regular connection for local development
            conn = psycopg2.connect(
                dbname=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PWD'),
                host=os.getenv('DB_HOST'),
                sslmode='require',  # Required for Neon database connections
                connect_timeout=30  # Set connection timeout to 30 seconds
            )
        print("✓ Successfully connected to PostgreSQL")

        # Create a cursor
        cur = conn.cursor()

        # Test 1: Check pgvector extension
        cur.execute("SELECT * FROM pg_extension WHERE extname = 'vector';")
        if cur.fetchone() is not None:
            print("✓ pgvector extension is installed")
        else:
            print("✗ pgvector extension is not installed")
            sys.exit(1)

        # Test 2: Create a test table with vector column
        cur.execute("""
            DROP TABLE IF EXISTS test_vectors;
            CREATE TABLE test_vectors (
                id serial PRIMARY KEY,
                embedding vector(3)
            );
        """)
        print("✓ Successfully created test table")

        # Test 3: Insert and query vector data
        test_vector = np.array([1.0, 2.0, 3.0])
        cur.execute(
            "INSERT INTO test_vectors (embedding) VALUES (%s) RETURNING id;",
            (test_vector,)
        )
        inserted_id = cur.fetchone()[0]
        print("✓ Successfully inserted test vector")

        # Test 4: Query the inserted vector
        cur.execute("SELECT embedding FROM test_vectors WHERE id = %s;", (inserted_id,))
        retrieved_vector = cur.fetchone()[0]
        print("✓ Successfully retrieved test vector:", retrieved_vector)

        # Test 5: Test vector similarity search
        cur.execute("""
            SELECT embedding <-> %s as distance
            FROM test_vectors
            ORDER BY distance
            LIMIT 1;
        """, (test_vector,))
        distance = cur.fetchone()[0]
        print("✓ Successfully performed similarity search, distance:", distance)

        # Cleanup
        # cur.execute("DROP TABLE test_vectors;")
        # conn.commit()
        # print("✓ Cleanup completed")

        cur.close()
        conn.close()
        print("\n✅ All PostgreSQL tests passed successfully!")
        return True

    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_postgresql_connection()
    sys.exit(0 if success else 1)
