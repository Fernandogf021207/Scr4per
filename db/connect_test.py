import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load env from ./db/.env
BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, '.env'))

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "scr4per"),
    "user": os.getenv("POSTGRES_USER", "scr4per_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "your_password_here"),
}

if __name__ == "__main__":
    try:
        with psycopg2.connect(cursor_factory=RealDictCursor, **DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version() AS version")
                print("Connected!", cur.fetchone()["version"])
    except Exception as e:
        print("Connection failed:", e)
        raise
