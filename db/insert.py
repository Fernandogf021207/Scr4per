import os
from contextlib import contextmanager
from typing import Optional

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

# Map platform to schema
SCHEMA_BY_PLATFORM = {
    'x': 'red_x',
    'instagram': 'red_instagram',
    'facebook': 'red_facebook',
}
DEFAULT_SCHEMA = 'red_x'

@contextmanager
def get_conn():
    conn = psycopg2.connect(cursor_factory=RealDictCursor, **DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ---------- Helpers ----------

def _schema(platform: str) -> str:
    return SCHEMA_BY_PLATFORM.get(platform, DEFAULT_SCHEMA)

# ---------- Upserts / Inserts ----------

def upsert_profile(cur, platform: str, username: str,
                   full_name: Optional[str] = None,
                   profile_url: Optional[str] = None,
                   photo_url: Optional[str] = None) -> int:
    schema = _schema(platform)
    cur.execute(
        f"""
        INSERT INTO {schema}.profiles(platform, username, full_name, profile_url, photo_url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (platform, username)
        DO UPDATE SET
            full_name  = COALESCE(NULLIF(EXCLUDED.full_name, ''),  {schema}.profiles.full_name),
            profile_url= COALESCE(NULLIF(EXCLUDED.profile_url, ''), {schema}.profiles.profile_url),
            photo_url  = COALESCE(NULLIF(EXCLUDED.photo_url, ''),  {schema}.profiles.photo_url),
            updated_at = NOW()
        RETURNING id;
        """,
        (platform, username, full_name, profile_url, photo_url)
    )
    return cur.fetchone()["id"]

def add_relationship(cur, platform: str, owner_username: str, related_username: str, rel_type: str) -> Optional[int]:
    schema = _schema(platform)
    owner_id = upsert_profile(cur, platform, owner_username)
    related_id = upsert_profile(cur, platform, related_username)
    cur.execute(
        f"""
        INSERT INTO {schema}.relationships(platform, owner_profile_id, related_profile_id, rel_type)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (platform, owner_profile_id, related_profile_id, rel_type) DO NOTHING
        RETURNING id;
        """,
        (platform, owner_id, related_id, rel_type)
    )
    row = cur.fetchone()
    return row["id"] if row else None

def add_post(cur, platform: str, owner_username: str, post_url: str) -> Optional[int]:
    schema = _schema(platform)
    owner_id = upsert_profile(cur, platform, owner_username)
    cur.execute(
        f"""
        INSERT INTO {schema}.posts(platform, owner_profile_id, post_url)
        VALUES (%s, %s, %s)
        ON CONFLICT (platform, post_url) DO NOTHING
        RETURNING id;
        """,
        (platform, owner_id, post_url)
    )
    row = cur.fetchone()
    return row["id"] if row else None

def add_comment(cur, platform: str, post_url: str, commenter_username: str) -> Optional[int]:
    schema = _schema(platform)
    # Validate post exists and platform matches
    cur.execute(f"SELECT id, platform FROM {schema}.posts WHERE post_url=%s", (post_url,))
    post = cur.fetchone()
    if not post:
        raise ValueError("post_url not found. Create the post first.")
    if post["platform"] != platform:
        raise ValueError("platform mismatch for post_url")

    commenter_id = upsert_profile(cur, platform, commenter_username)
    cur.execute(
        f"""
        INSERT INTO {schema}.comments(post_id, commenter_profile_id)
        VALUES (%s, %s)
        ON CONFLICT (post_id, commenter_profile_id) DO NOTHING
        RETURNING id;
        """,
        (post["id"], commenter_id)
    )
    row = cur.fetchone()
    return row["id"] if row else None

if __name__ == "__main__":
    # Tiny demo across schemas
    with get_conn() as conn:
        with conn.cursor() as cur:
            for plat, user in [('x','demo_user_x'), ('instagram','demo_user_ig'), ('facebook','demo_user_fb')]:
                pid = upsert_profile(cur, plat, user, full_name=f'Demo {plat}', profile_url=f'https://{plat}.com/{user}')
                print(plat, 'profile id:', pid)
                rid = add_relationship(cur, plat, user, f'{user}_follower', 'follower')
                print(plat, 'relationship id:', rid)
                post_id = add_post(cur, plat, user, f'https://{plat}.com/{user}/status/1')
                print(plat, 'post id:', post_id)
                try:
                    cid = add_comment(cur, plat, f'https://{plat}.com/{user}/status/1', f'{user}_commenter')
                    print(plat, 'comment id:', cid)
                except ValueError as e:
                    print(plat, 'comment error:', e)
