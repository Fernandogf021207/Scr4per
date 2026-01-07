import os
import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from urllib.parse import quote_plus

# Load env from db/.env if present
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'db', '.env'))

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST"),
    "port": int(os.getenv("POSTGRES_PORT") or 5432),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

# PostgreSQL connection string para SQLAlchemy
# URL-encode user and password to handle special characters like @, :, /, etc.
DATABASE_URL = (
    f"postgresql://{quote_plus(DB_CONFIG['user'])}:{quote_plus(DB_CONFIG['password'])}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
)

# SQLAlchemy engine y SessionLocal
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_conn():
    """Retorna conexión psycopg2 con RealDictCursor (uso legacy)."""
    return psycopg2.connect(cursor_factory=RealDictCursor, **DB_CONFIG)


def get_sqlalchemy_session() -> Session:
    """Retorna una nueva sesión de SQLAlchemy para usar con el pool de cuentas."""
    return SessionLocal()