import os
from dotenv import load_dotenv
import sqlalchemy as sa

# Load environment variables from .env file
load_dotenv()

def create_engine_url():
    DB_USER = os.environ["DB_USER"]
    DB_PWD = os.environ["DB_PWD"]
    DB_NAME = os.environ["DB_NAME"]
    
    # Check if running in Cloud Run
    if "INSTANCE_CONNECTION_NAME" in os.environ:
        INSTANCE_CONNECTION_NAME = os.environ["INSTANCE_CONNECTION_NAME"]
        # Cloud SQL connection
        return sa.engine.URL.create(
            drivername="postgresql+pg8000",
            username=DB_USER,
            password=DB_PWD,
            database=DB_NAME,
            query={
                "unix_sock": f"/cloudsql/{INSTANCE_CONNECTION_NAME}/.s.PGSQL.5432"
            }
        )
    else:
        # Local connection
        DB_HOST = os.environ["DB_HOST"]
        return sa.engine.URL.create(
            drivername="postgresql+pg8000",
            username=DB_USER,
            password=DB_PWD,
            host=DB_HOST,
            database=DB_NAME
        )

# Create engine with configuration
engine = sa.create_engine(
    create_engine_url(),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=2
)

def get_data():
    try:
        with engine.connect() as conn:
            # Test connection
            result = conn.execute(sa.text("SELECT version()"))
            print("Successfully connected to database!")
            row = result.first()
            print(f"Database version: {row[0] if row else 'Unknown'}")
            
            # Your actual query
            result = conn.execute(sa.text("SELECT * FROM transcripts"))
            for row in result:
                print(row)
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        raise

if __name__ == "__main__":
    get_data()
