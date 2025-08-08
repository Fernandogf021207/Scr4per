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

# ---------- Upserts / Inserts ----------

def upsert_profile(cur, platform: str, username: str,
                   full_name: Optional[str] = None,
                   profile_url: Optional[str] = None,
                   photo_url: Optional[str] = None) -> int:
    cur.execute(
        """
        INSERT INTO profiles(platform, username, full_name, profile_url, photo_url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (platform, username)
        DO UPDATE SET
            full_name = COALESCE(EXCLUDED.full_name, profiles.full_name),
            profile_url = COALESCE(EXCLUDED.profile_url, profiles.profile_url),
            photo_url = COALESCE(EXCLUDED.photo_url, profiles.photo_url),
            updated_at = NOW()
        RETURNING id;
        """,
        (platform, username, full_name, profile_url, photo_url)
    )
    return cur.fetchone()["id"]

def add_relationship(cur, platform: str, owner_username: str, related_username: str, rel_type: str) -> Optional[int]:
    owner_id = upsert_profile(cur, platform, owner_username)
    related_id = upsert_profile(cur, platform, related_username)
    cur.execute(
        """
        INSERT INTO relationships(platform, owner_profile_id, related_profile_id, rel_type)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (platform, owner_profile_id, related_profile_id, rel_type) DO NOTHING
        RETURNING id;
        """,
        (platform, owner_id, related_id, rel_type)
    )
    row = cur.fetchone()
    return row["id"] if row else None

def add_post(cur, platform: str, owner_username: str, post_url: str) -> Optional[int]:
    owner_id = upsert_profile(cur, platform, owner_username)
    cur.execute(
        """
        INSERT INTO posts(platform, owner_profile_id, post_url)
        VALUES (%s, %s, %s)
        ON CONFLICT (platform, post_url) DO NOTHING
        RETURNING id;
        """,
        (platform, owner_id, post_url)
    )
    row = cur.fetchone()
    return row["id"] if row else None

def add_comment(cur, platform: str, post_url: str, commenter_username: str) -> Optional[int]:
    # Validate post exists and platform matches
    cur.execute("SELECT id, platform FROM posts WHERE post_url=%s", (post_url,))
    post = cur.fetchone()
    if not post:
        raise ValueError("post_url not found. Create the post first.")
    if post["platform"] != platform:
        raise ValueError("platform mismatch for post_url")

    commenter_id = upsert_profile(cur, platform, commenter_username)
    cur.execute(
        """
        INSERT INTO comments(post_id, commenter_profile_id)
        VALUES (%s, %s)
        ON CONFLICT (post_id, commenter_profile_id) DO NOTHING
        RETURNING id;
        """,
        (post["id"], commenter_id)
    )
    row = cur.fetchone()
    return row["id"] if row else None

if __name__ == "__main__":
    # Tiny demo
    with get_conn() as conn:
        with conn.cursor() as cur:
            pid = upsert_profile(cur, 'x', 'demo_user', full_name='Demo User', profile_url='https://x.com/demo_user')
            print('profile id:', pid)
            rid = add_relationship(cur, 'x', 'demo_user', 'other_user', 'follower')
            print('relationship id:', rid)
            post_id = add_post(cur, 'x', 'demo_user', 'https://x.com/demo_user/status/1')
            print('post id:', post_id)
            try:
                cid = add_comment(cur, 'x', 'https://x.com/demo_user/status/1', 'commenter1')
                print('comment id:', cid)
            except ValueError as e:
                print('comment error:', e)
