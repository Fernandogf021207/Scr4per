import os
import sys
from typing import Optional, Literal, List, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Ensure project root is on sys.path so we can import src.*
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

# Playwright (async) for scrapers
from playwright.async_api import async_playwright

# Scrapers and configs
from src.scrapers.facebook.scraper import (
    obtener_datos_usuario_facebook,
    scrap_followers as fb_scrap_followers,
    scrap_followed as fb_scrap_followed,
    scrap_friends_all as fb_scrap_friends,
    scrap_comentarios_fotos as fb_scrap_comments,
    scrap_reacciones_fotos as fb_scrap_reactions,
)
from src.scrapers.facebook.config import FACEBOOK_CONFIG
from src.scrapers.instagram.scraper import (
    obtener_datos_usuario_principal as ig_obtener_datos,
    scrap_seguidores as ig_scrap_followers,
    scrap_seguidos as ig_scrap_followed,
    scrap_comentadores_instagram as ig_scrap_commenters,
)
from src.scrapers.instagram.config import INSTAGRAM_CONFIG
from src.scrapers.x.scraper import (
    obtener_datos_usuario_principal as x_obtener_datos,
    scrap_seguidores as x_scrap_followers,
    scrap_seguidos as x_scrap_followed,
    scrap_comentadores as x_scrap_commenters,
)
from src.scrapers.x.config import X_CONFIG

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

# ---------- Schema routing ----------
SCHEMA_BY_PLATFORM = {
    'x': 'red_x',
    'instagram': 'red_instagram',
    'facebook': 'red_facebook',
}

def _schema(platform: str) -> str:
    return SCHEMA_BY_PLATFORM.get(platform, 'red_x')

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
    rel_type: Literal['follower', 'following', 'friend']

class PostIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    owner_username: str
    post_url: str

class CommentIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    post_url: str
    commenter_username: str

class ReactionIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    post_url: str
    reactor_username: str
    reaction_type: Optional[str] = None  # e.g., like/love/etc on FB

class ScrapeRequest(BaseModel):
    url: str
    platform: Literal['x', 'instagram', 'facebook']
    max_photos: Optional[int] = 5

# ---------- DB helpers ----------

def get_conn():
    return psycopg2.connect(cursor_factory=RealDictCursor, **DB_CONFIG)

# Upsert profile and return id

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

def add_reaction(cur, platform: str, post_url: str, reactor_username: str, reaction_type: Optional[str] = None) -> Optional[int]:
    schema = _schema(platform)
    cur.execute(f"SELECT id, platform FROM {schema}.posts WHERE post_url=%s", (post_url,))
    post = cur.fetchone()
    if not post:
        raise ValueError("post_url not found. Create the post first.")
    if post["platform"] != platform:
        raise ValueError("platform mismatch for post_url")
    reactor_id = upsert_profile(cur, platform, reactor_username)
    # Create table via migration; assume exists
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
                schema = _schema(p.platform)
                cur.execute(f"SELECT id, platform, username, full_name, profile_url, photo_url FROM {schema}.profiles WHERE id=%s", (pid,))
                row = cur.fetchone()
                return Profile(**row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/relationships")
def create_relationship(r: RelationshipIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                rel_id = add_relationship(cur, r.platform, r.owner_username, r.related_username, r.rel_type)
                conn.commit()
                return {"inserted": bool(rel_id), "relationship_id": rel_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/posts")
def create_post(p: PostIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                post_id = add_post(cur, p.platform, p.owner_username, p.post_url)
                conn.commit()
                return {"inserted": bool(post_id), "post_id": post_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/comments")
def create_comment(c: CommentIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    comment_id = add_comment(cur, c.platform, c.post_url, c.commenter_username)
                except ValueError as ve:
                    raise HTTPException(status_code=400, detail=str(ve))
                conn.commit()
                return {"inserted": bool(comment_id), "comment_id": comment_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reactions")
def create_reaction(r: ReactionIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    reaction_id = add_reaction(cur, r.platform, r.post_url, r.reactor_username, r.reaction_type)
                except ValueError as ve:
                    raise HTTPException(status_code=400, detail=str(ve))
                conn.commit()
                return {"inserted": bool(reaction_id), "reaction_id": reaction_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------- Scraper Orchestrator ----------

def _storage_state_for(platform: str) -> str:
    if platform == 'facebook':
        return FACEBOOK_CONFIG.get('storage_state_path')
    if platform == 'instagram':
        return INSTAGRAM_CONFIG.get('storage_state_path')
    if platform == 'x':
        return X_CONFIG.get('storage_state_path')
    return ''

def _extract_username(item: Dict[str, Any]) -> Optional[str]:
    return (item or {}).get('username_usuario') or (item or {}).get('username')

@app.post("/scrape")
async def scrape(req: ScrapeRequest):
    platform = req.platform
    url = req.url
    max_photos = req.max_photos or 5

    storage_state = _storage_state_for(platform)
    if not storage_state or not os.path.exists(storage_state):
        raise HTTPException(status_code=400, detail=f"Missing or invalid storage_state for {platform}")

    # Result accumulators
    perfil_obj: Dict[str, Any] = {}
    relacionados: List[Dict[str, str]] = []
    tipos_presentes: set = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(storage_state=storage_state)
        page = await context.new_page()
        try:
            # Perfil objetivo y username
            if platform == 'facebook':
                datos = await obtener_datos_usuario_facebook(page, url)
                username = datos.get('username') or 'unknown'
                perfil_obj = {
                    'platform': platform,
                    'username': username,
                    'full_name': datos.get('nombre_completo') or username,
                    'profile_url': datos.get('url_usuario') or url,
                    'photo_url': datos.get('foto_perfil') or '',
                }
                # Listas
                followers = await fb_scrap_followers(page, url, username)
                following = await fb_scrap_followed(page, url, username)
                friends = await fb_scrap_friends(page, url, username)
                # Fotos: comentarios y reacciones (reacciones no se devuelven en JSON, solo DB)
                commenters = await fb_scrap_comments(page, url, username, max_fotos=max_photos)
                reactions = await fb_scrap_reactions(page, url, username, max_fotos=max_photos, incluir_comentarios=True)
            elif platform == 'instagram':
                datos = await ig_obtener_datos(page, url)
                username = datos.get('username') or 'unknown'
                perfil_obj = {
                    'platform': platform,
                    'username': username,
                    'full_name': datos.get('nombre_completo') or username,
                    'profile_url': datos.get('url_usuario') or url,
                    'photo_url': datos.get('foto_perfil') or '',
                }
                followers = await ig_scrap_followers(page, url, username)
                following = await ig_scrap_followed(page, url, username)
                friends = []
                commenters = await ig_scrap_commenters(page, url, username, max_posts=max_photos)
                reactions = []  # Not implemented for IG in current codebase
            elif platform == 'x':
                datos = await x_obtener_datos(page, url)
                username = datos.get('username') or 'unknown'
                perfil_obj = {
                    'platform': platform,
                    'username': username,
                    'full_name': datos.get('nombre_completo') or username,
                    'profile_url': datos.get('url_usuario') or url,
                    'photo_url': datos.get('foto_perfil') or '',
                }
                followers = await x_scrap_followers(page, url, username)
                following = await x_scrap_followed(page, url, username)
                friends = []
                commenters = await x_scrap_commenters(page, url, username)
                reactions = []  # Not implemented for X in current codebase
            else:
                raise HTTPException(status_code=400, detail="Unsupported platform")

            # Normalize usernames
            followers_usernames = [u for u in ([_extract_username(x) for x in followers] if followers else []) if u]
            following_usernames = [u for u in ([_extract_username(x) for x in following] if following else []) if u]
            friends_usernames = [u for u in ([_extract_username(x) for x in friends] if friends else []) if u]
            commenters_items = commenters or []
            commenters_usernames = [
                (_extract_username(x)) for x in commenters_items if _extract_username(x)
            ]

            # Persist into DB
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Ensure target profile exists
                    upsert_profile(cur, platform, perfil_obj['username'], perfil_obj.get('full_name'), perfil_obj.get('profile_url'), perfil_obj.get('photo_url'))
                    # Relationships
                    for u in followers_usernames:
                        add_relationship(cur, platform, perfil_obj['username'], u, 'follower')
                    for u in following_usernames:
                        add_relationship(cur, platform, perfil_obj['username'], u, 'following')
                    # Friends only FB
                    if platform == 'facebook':
                        for u in friends_usernames:
                            add_relationship(cur, platform, perfil_obj['username'], u, 'friend')
                    # Posts + comments
                    # Build set of photo/post URLs from commenters items
                    post_urls = set()
                    for item in commenters_items:
                        purl = item.get('post_url')
                        if purl:
                            post_urls.add(purl)
                    for purl in post_urls:
                        add_post(cur, platform, perfil_obj['username'], purl)
                    for item in commenters_items:
                        purl = item.get('post_url')
                        uname = _extract_username(item)
                        if purl and uname:
                            try:
                                add_comment(cur, platform, purl, uname)
                            except ValueError:
                                # Ensure post exists then retry once
                                add_post(cur, platform, perfil_obj['username'], purl)
                                add_comment(cur, platform, purl, uname)
                    # Reactions (persist only)
                    for rx in reactions or []:
                        purl = rx.get('post_url')
                        uname = _extract_username(rx)
                        if purl and uname:
                            try:
                                add_post(cur, platform, perfil_obj['username'], purl)
                                add_reaction(cur, platform, purl, uname, rx.get('reaction_type'))
                            except ValueError:
                                add_post(cur, platform, perfil_obj['username'], purl)
                                add_reaction(cur, platform, purl, uname, rx.get('reaction_type'))
                    conn.commit()

            # Build normalized response (exactly three top-level fields)
            relacionados_map = {}
            for u in followers_usernames:
                relacionados_map.setdefault(u, 'seguidor')
            for u in following_usernames:
                relacionados_map.setdefault(u, 'seguido')
            for u in commenters_usernames:
                relacionados_map.setdefault(u, 'comentó')

            relacionados = [
                {"username": uname, "tipo de relacion": tipo}
                for uname, tipo in relacionados_map.items()
            ]
            tipos_presentes = set(relacionados_map.values())

            return {
                "Perfil objetivo": perfil_obj,
                "Perfiles relacionados": relacionados,
                "Tipo de relacion": sorted(tipos_presentes),
            }
        finally:
            await context.close()
            await browser.close()
