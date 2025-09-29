from __future__ import annotations
from typing import List, Dict, Any, Optional
import asyncio

from fastapi import HTTPException
from playwright.async_api import async_playwright

from .aggregation import Aggregator, make_profile, normalize_username, valid_username
from src.utils.url import extract_username_from_url, normalize_input_url
from ..deps import storage_state_for
from ..repositories import upsert_profile, add_relationship
from ..db import get_conn

# Reuse existing scraper functions (import here to avoid circulars)
from src.scrapers.facebook.scraper import (
    obtener_datos_usuario_facebook,
    scrap_followers as fb_scrap_followers,
    scrap_followed as fb_scrap_followed,
    scrap_friends_all as fb_scrap_friends,
)
from src.scrapers.instagram.scraper import (
    obtener_datos_usuario_principal as ig_obtener_datos,
    scrap_seguidores as ig_scrap_followers,
    scrap_seguidos as ig_scrap_followed,
)
from src.scrapers.x.scraper import (
    obtener_datos_usuario_principal as x_obtener_datos,
    scrap_seguidores as x_scrap_followers,
    scrap_seguidos as x_scrap_followed,
)

REL_FOLLOWER = 'seguidor'
REL_FOLLOWING = 'seguido'
REL_FRIEND = 'amigo'

MAX_ROOTS = 5  # configurable in future

async def multi_scrape_execute(requests: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not requests:
        raise HTTPException(status_code=422, detail={"code":"VALIDATION_ERROR", "message":"No roots provided"})
    if len(requests) > MAX_ROOTS:
        raise HTTPException(status_code=422, detail={"code":"LIMIT_EXCEEDED", "message": f"Max {MAX_ROOTS} roots"})

    # Validate inputs
    norm_requests = []
    for r in requests:
        platform = r.get('platform')
        username = normalize_username(r.get('username'))
        max_fotos = r.get('max_fotos') or r.get('max_fotos') or 5
        if not valid_username(username):
            raise HTTPException(status_code=422, detail={"code":"VALIDATION_ERROR", "message": f"Invalid username: {username}"})
        norm_requests.append({"platform": platform, "username": username, "max_fotos": max_fotos})

    # Sequential (F1) - later: parallel with semaphores
    agg = Aggregator()

    async with async_playwright() as pw:
        for req in norm_requests:
            platform = req['platform']
            username = req['username']
            max_photos = req['max_fotos']

            storage_state = storage_state_for(platform)
            if not storage_state:
                agg.warnings.append({"code":"ROOT_SKIPPED", "message": f"Missing storage_state for {platform}"})
                continue
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=storage_state)
            page = await context.new_page()
            try:
                root_profile, followers, following, friends = await _scrape_one(platform, username, page, max_photos)
                # Add root profile
                agg.add_root(make_profile(platform, root_profile['username'], root_profile.get('full_name'), root_profile.get('profile_url'), root_profile.get('photo_url'), (platform, username)))
                # Normalize and add lists
                _ingest_list(agg, platform, username, followers, direction='followers')
                _ingest_list(agg, platform, username, following, direction='following')
                _ingest_list(agg, platform, username, friends, direction='friends')

                # Root-root relations (optional F1): simple detection (A follows B & B follows A handled naturally if both roots present)
                # After adding all roots we could post-process, but leaving natural accumulation for now.

                # Persist minimal (same approach as /scrape) - upsert root + direct relations participants
                try:
                    with get_conn() as conn:
                        with conn.cursor() as cur:
                            # Root
                            upsert_profile(cur, platform, username, root_profile.get('full_name'), root_profile.get('profile_url'), root_profile.get('photo_url'))
                            # Others
                            for rel_item in (followers + following + friends):
                                norm = _normalize_user_item(platform, rel_item)
                                fu = norm.get('username')
                                if fu and valid_username(fu):
                                    upsert_profile(cur, platform, fu, norm.get('full_name'), norm.get('profile_url'), norm.get('photo_url'))
                                    # Relationship direction mapping for DB english types
                                    if norm.get('_rel_type_db'):
                                        add_relationship(cur, platform, norm.get('_rel_source_db'), norm.get('_rel_target_db'), norm.get('_rel_type_db'))
                            conn.commit()
                except Exception:
                    pass
            except Exception as e:
                agg.warnings.append({"code":"PARTIAL_FAILURE", "message": f"{platform}:{username} {str(e)}"})
            finally:
                await context.close()
                await browser.close()

    return agg.build_payload(roots_requested=len(norm_requests))


async def _scrape_one(platform: str, username: str, page, max_photos: int):
    perfil_url = build_profile_url(platform, username)
    if platform == 'facebook':
        datos = await obtener_datos_usuario_facebook(page, perfil_url)
        root_profile = {
            'platform': platform,
            'username': datos.get('username') or username,
            'full_name': datos.get('nombre_completo') or username,
            'profile_url': datos.get('url_usuario'),
            'photo_url': datos.get('foto_perfil'),
        }
        followers = await fb_scrap_followers(page, perfil_url, root_profile['username'])
        following = await fb_scrap_followed(page, perfil_url, root_profile['username'])
        friends = await fb_scrap_friends(page, perfil_url, root_profile['username'])
    elif platform == 'instagram':
        datos = await ig_obtener_datos(page, perfil_url)
        root_profile = {
            'platform': platform,
            'username': datos.get('username') or username,
            'full_name': datos.get('nombre_completo') or username,
            'profile_url': datos.get('url_usuario'),
            'photo_url': datos.get('foto_perfil'),
        }
        followers = await ig_scrap_followers(page, perfil_url, root_profile['username'])
        following = await ig_scrap_followed(page, perfil_url, root_profile['username'])
        friends = []
    elif platform == 'x':
        datos = await x_obtener_datos(page, perfil_url)
        root_profile = {
            'platform': platform,
            'username': datos.get('username') or username,
            'full_name': datos.get('nombre_completo') or username,
            'profile_url': datos.get('url_usuario'),
            'photo_url': datos.get('foto_perfil'),
        }
        followers = await x_scrap_followers(page, perfil_url, root_profile['username'])
        following = await x_scrap_followed(page, perfil_url, root_profile['username'])
        friends = []
    else:
        raise HTTPException(status_code=400, detail={"code":"PLATFORM_UNSUPPORTED", "message": platform})

    return root_profile, followers, following, friends


def build_profile_url(platform: str, username: str) -> str:
    """Construct canonical base profile URL from platform + username.
    We intentionally do not rely on scrapers to guess from a bare username to avoid invalid navigation like https://<username>.
    """
    u = (username or '').strip().lstrip('@')
    if platform == 'facebook':
        return f"https://www.facebook.com/{u}/"
    if platform == 'instagram':
        return f"https://www.instagram.com/{u}/"
    if platform == 'x':
        return f"https://x.com/{u}"
    return u


def _normalize_user_item(platform: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Accepts heterogeneous user dicts from different scrapers and normalizes keys.
    Expected output keys: username, full_name, profile_url, photo_url
    Some scrapers use variants: nombre_usuario, username_usuario, link_usuario, foto_usuario.
    """
    if not isinstance(raw, dict):
        return {}
    # Common variants
    username = raw.get('username') or raw.get('username_usuario') or raw.get('user') or raw.get('handle')
    full_name = raw.get('full_name') or raw.get('nombre_completo') or raw.get('nombre_usuario') or raw.get('name')
    profile_url = raw.get('profile_url') or raw.get('url_usuario') or raw.get('link_usuario') or raw.get('href')
    photo_url = raw.get('photo_url') or raw.get('foto_perfil') or raw.get('foto_usuario') or raw.get('image')

    # Derive username from URL if missing
    if (not username) and profile_url:
        username = extract_username_from_url(platform, profile_url)

    # Normalize URL form
    if profile_url:
        profile_url = normalize_input_url(platform, profile_url)

    # Final fallback
    username = (username or '').strip().lstrip('@')
    full_name = full_name or username

    return {
        'username': username,
        'full_name': full_name,
        'profile_url': profile_url,
        'photo_url': photo_url,
    }


def _ingest_list(agg: Aggregator, platform: str, root_username: str, items: List[Dict[str, Any]], *, direction: str):
    """Ingest a follower/following/friends list, create profiles + relations.
    direction: 'followers' | 'following' | 'friends'
    Relation semantics (Spanish API types):
      followers: follower -> root (seguidor)
      following: root -> followed (seguido)
      friends: bidirectional amigo (we add root->friend and friend->root?) For now single direction root->friend (amigo) plus friend->root (amigo) to represent undirected.
    """
    if not items:
        return
    for raw in items:
        norm = _normalize_user_item(platform, raw)
        u = norm.get('username')
        if not u or not valid_username(u) or u == root_username:
            continue
        agg.add_profile(make_profile(platform, u, norm.get('full_name'), norm.get('profile_url'), norm.get('photo_url'), (platform, root_username)))
        if direction == 'followers':
            agg.add_relation(platform, u, root_username, REL_FOLLOWER)
        elif direction == 'following':
            agg.add_relation(platform, root_username, u, REL_FOLLOWING)
        elif direction == 'friends':
            # Add both directions to reflect mutual friendship
            agg.add_relation(platform, root_username, u, REL_FRIEND)
            agg.add_relation(platform, u, root_username, REL_FRIEND)
