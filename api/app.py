import os
from typing import Optional, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load env variables from ./db/.env if present
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'db', '.env'))

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "scr4per"),
    "user": os.getenv("POSTGRES_USER", "scr4per_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "your_password_here"),
}

app = FastAPI(title="Scr4per DB API", version="0.1.0")

# ---------- Pydantic models ----------
class ProfileIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    username: str
    full_name: Optional[str] = None
    profile_url: Optional[str] = None
    photo_url: Optional[str] = None

class Profile(ProfileIn):
    id: int

class RelationshipIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    owner_username: str
    related_username: str
    rel_type: Literal['follower', 'following']

class PostIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    owner_username: str
    post_url: str

class CommentIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    post_url: str
    commenter_username: str

# ---------- DB helpers ----------

def get_conn():
    return psycopg2.connect(cursor_factory=RealDictCursor, **DB_CONFIG)

# Upsert profile and return id

def upsert_profile(cur, platform: str, username: str, full_name: Optional[str] = None,
                   profile_url: Optional[str] = None, photo_url: Optional[str] = None) -> int:
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

# ---------- Routes ----------

@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                ok = cur.fetchone()["ok"]
        return {"status": "ok", "db": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/profiles", response_model=Profile)
def create_or_update_profile(p: ProfileIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                pid = upsert_profile(cur, p.platform, p.username, p.full_name, p.profile_url, p.photo_url)
                conn.commit()
                cur.execute("SELECT id, platform, username, full_name, profile_url, photo_url FROM profiles WHERE id=%s", (pid,))
                row = cur.fetchone()
                return Profile(**row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/relationships")
def create_relationship(r: RelationshipIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                owner_id = upsert_profile(cur, r.platform, r.owner_username)
                related_id = upsert_profile(cur, r.platform, r.related_username)
                cur.execute(
                    """
                    INSERT INTO relationships(platform, owner_profile_id, related_profile_id, rel_type)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (platform, owner_profile_id, related_profile_id, rel_type) DO NOTHING
                    RETURNING id;
                    """,
                    (r.platform, owner_id, related_id, r.rel_type)
                )
                inserted = cur.fetchone()
                conn.commit()
                return {"inserted": bool(inserted), "relationship_id": inserted["id"] if inserted else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/posts")
def create_post(p: PostIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                owner_id = upsert_profile(cur, p.platform, p.owner_username)
                cur.execute(
                    """
                    INSERT INTO posts(platform, owner_profile_id, post_url)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (platform, post_url) DO NOTHING
                    RETURNING id;
                    """,
                    (p.platform, owner_id, p.post_url)
                )
                post = cur.fetchone()
                conn.commit()
                return {"inserted": bool(post), "post_id": post["id"] if post else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/comments")
def create_comment(c: CommentIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # find post id (or insert post stub by URL only if exists with any owner)
                cur.execute("SELECT id, platform FROM posts WHERE post_url=%s", (c.post_url,))
                post = cur.fetchone()
                if not post:
                    raise HTTPException(status_code=400, detail="post_url not found. Create /posts first.")
                if post["platform"] != c.platform:
                    raise HTTPException(status_code=400, detail="platform mismatch for post_url")

                commenter_id = upsert_profile(cur, c.platform, c.commenter_username)
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
                conn.commit()
                return {"inserted": bool(row), "comment_id": row["id"] if row else None}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
