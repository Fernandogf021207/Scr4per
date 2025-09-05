from typing import Optional
from psycopg2.extras import Json
from .deps import _schema

def upsert_profile(cur, platform: str, username: str, full_name: Optional[str] = None,
                   profile_url: Optional[str] = None, photo_url: Optional[str] = None) -> int:
    schema = _schema(platform)
    cur.execute(
        f"""
        INSERT INTO {schema}.profiles(platform, username, full_name, profile_url, photo_url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (platform, username)
        DO UPDATE SET
            full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''),  {schema}.profiles.full_name),
            profile_url = COALESCE(NULLIF(EXCLUDED.profile_url, ''), {schema}.profiles.profile_url),
            photo_url = COALESCE(NULLIF(EXCLUDED.photo_url, ''),  {schema}.profiles.photo_url),
            updated_at = NOW()
        RETURNING id;
        """,
        (platform, username, full_name, profile_url, photo_url)
    )
    return cur.fetchone()["id"]

def add_relationship(cur, platform: str, owner_username: str, related_username: str, rel_type: str):
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

def add_post(cur, platform: str, owner_username: str, post_url: str):
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

def add_comment(cur, platform: str, post_url: str, commenter_username: str):
    schema = _schema(platform)
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

def add_reaction(cur, platform: str, post_url: str, reactor_username: str, reaction_type: Optional[str] = None):
    schema = _schema(platform)
    cur.execute(f"SELECT id, platform FROM {schema}.posts WHERE post_url=%s", (post_url,))
    post = cur.fetchone()
    if not post:
        raise ValueError("post_url not found. Create the post first.")
    if post["platform"] != platform:
        raise ValueError("platform mismatch for post_url")
    reactor_id = upsert_profile(cur, platform, reactor_username)
    cur.execute(
        f"""
        INSERT INTO {schema}.reactions(post_id, reactor_profile_id, reaction_type)
        VALUES (%s, %s, %s)
        ON CONFLICT (post_id, reactor_profile_id) DO NOTHING
        RETURNING id;
        """,
        (post["id"], reactor_id, reaction_type)
    )
    row = cur.fetchone()
    return row["id"] if row else None