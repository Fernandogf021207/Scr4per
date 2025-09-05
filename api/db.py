import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load env from db/.env if present
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'db', '.env'))

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST"),
    "port": int(os.getenv("POSTGRES_PORT") or 5432),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

def get_conn():
    return psycopg2.connect(cursor_factory=RealDictCursor, **DB_CONFIG)