from typing import List, Dict, Any, Optional, Literal
from fastapi import APIRouter, HTTPException
from playwright.async_api import async_playwright
from ..schemas import ScrapeRequest
from ..db import get_conn
from ..deps import storage_state_for
from ..repositories import upsert_profile, add_relationship, add_post, add_comment, add_reaction
from src.utils.url import normalize_input_url, normalize_post_url
from src.utils.images import local_or_proxy_photo_url
from .related import _build_related_from_db

# Scrapers
from src.scrapers.facebook.scraper import (
    obtener_datos_usuario_facebook,
    scrap_followers as fb_scrap_followers,
    scrap_followed as fb_scrap_followed,
    scrap_friends_all as fb_scrap_friends,
    scrap_comentarios_fotos as fb_scrap_comments,
    scrap_reacciones_fotos as fb_scrap_reactions,
)
from src.scrapers.instagram.scraper import (
    obtener_datos_usuario_principal as ig_obtener_datos,
    scrap_seguidores as ig_scrap_followers,
    scrap_seguidos as ig_scrap_followed,
    scrap_comentadores_instagram as ig_scrap_commenters,
    scrap_reacciones_instagram as ig_scrap_reactions,
)
from src.scrapers.x.scraper import (
    obtener_datos_usuario_principal as x_obtener_datos,
    scrap_seguidores as x_scrap_followers,
    scrap_seguidos as x_scrap_followed,
    scrap_comentadores as x_scrap_commenters,
)

router = APIRouter()

def _extract_username(item: Dict[str, Any]) -> Optional[str]:
    return (item or {}).get('username_usuario') or (item or {}).get('username')

def _extract_fields(item: Dict[str, Any]) -> Dict[str, Optional[str]]:
    return {
        'full_name': (item or {}).get('nombre_usuario') or (item or {}).get('full_name'),
        'profile_url': (item or {}).get('link_usuario') or (item or {}).get('profile_url'),
        'photo_url': (item or {}).get('foto_usuario') or (item or {}).get('photo_url'),
    }

@router.post("/scrape")
async def scrape(req: ScrapeRequest):
    platform = req.platform
    url = normalize_input_url(platform, req.url)
    max_photos = req.max_photos or 5

    storage_state = storage_state_for(platform)
    if not storage_state:
        raise HTTPException(status_code=400, detail=f"Missing storage_state for {platform}")

    perfil_obj: Dict[str, Any] = {}
    relacionados: List[Dict[str, str]] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=storage_state)
        page = await context.new_page()
        try:
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
                followers = await fb_scrap_followers(page, url, username)
                following = await fb_scrap_followed(page, url, username)
                friends = await fb_scrap_friends(page, url, username)
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
                reactions = await ig_scrap_reactions(page, url, username, max_posts=max_photos)
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
                commenters = await x_scrap_commenters(page, url, username, max_posts=max_photos)
                reactions = []
            else:
                raise HTTPException(status_code=400, detail="Unsupported platform")

            followers_usernames = [u for u in ([_extract_username(x) for x in followers] if followers else []) if u]
            following_usernames = [u for u in ([_extract_username(x) for x in following] if following else []) if u]
            friends_usernames = [u for u in ([_extract_username(x) for x in friends] if friends else []) if u]
            commenters_items = commenters or []
            commenters_usernames = [(_extract_username(x)) for x in commenters_items if _extract_username(x)]
            reactors_usernames = [u for u in ([_extract_username(x) for x in (reactions or [])] if reactions else []) if u]

            with get_conn() as conn:
                with conn.cursor() as cur:
                    try:
                        if perfil_obj.get('photo_url') and not str(perfil_obj['photo_url']).startswith('/storage/'):
                            perfil_obj['photo_url'] = await local_or_proxy_photo_url(
                                perfil_obj.get('photo_url'),
                                perfil_obj.get('username'),
                                mode='download',
                                page=page,
                                on_failure='empty',
                                retries=5,
                                backoff_seconds=0.5,
                            )
                    except Exception:
                        perfil_obj['photo_url'] = ""
                    upsert_profile(cur, platform, perfil_obj['username'], perfil_obj.get('full_name'), perfil_obj.get('profile_url'), perfil_obj.get('photo_url'))

                    by_username: Dict[str, Dict[str, Any]] = {}
                    for lst in [followers or [], following or [], friends or [], commenters or [], reactions or []]:
                        for it in lst:
                            uname = _extract_username(it)
                            if not uname:
                                continue
                            if uname not in by_username:
                                by_username[uname] = _extract_fields(it)
                            else:
                                fields = _extract_fields(it)
                                curf = by_username[uname]
                                by_username[uname] = {
                                    'full_name': curf.get('full_name') or fields.get('full_name'),
                                    'profile_url': curf.get('profile_url') or fields.get('profile_url'),
                                    'photo_url': curf.get('photo_url') or fields.get('photo_url'),
                                }

                    async def _ensure_local_photo(url: Optional[str], uname: str) -> str:
                        if not url:
                            return ""
                        if str(url).startswith('/storage/'):
                            return url
                        try:
                            return await local_or_proxy_photo_url(
                                url, uname, mode='download', page=page, on_failure='empty', retries=5, backoff_seconds=0.5
                            )
                        except Exception:
                            return ""

                    for u in followers_usernames:
                        f = by_username.get(u, {})
                        photo_local = await _ensure_local_photo(f.get('photo_url'), u)
                        upsert_profile(cur, platform, u, f.get('full_name'), f.get('profile_url'), photo_local)
                        add_relationship(cur, platform, perfil_obj['username'], u, 'follower')

                    for u in following_usernames:
                        f = by_username.get(u, {})
                        photo_local = await _ensure_local_photo(f.get('photo_url'), u)
                        upsert_profile(cur, platform, u, f.get('full_name'), f.get('profile_url'), photo_local)
                        add_relationship(cur, platform, perfil_obj['username'], u, 'following')

                    if platform == 'facebook':
                        for u in friends_usernames:
                            f = by_username.get(u, {})
                            photo_local = await _ensure_local_photo(f.get('photo_url'), u)
                            upsert_profile(cur, platform, u, f.get('full_name'), f.get('profile_url'), photo_local)
                            add_relationship(cur, platform, perfil_obj['username'], u, 'friend')

                    post_urls = set()
                    for item in commenters_items:
                        purl = normalize_post_url(platform, item.get('post_url')) if item.get('post_url') else None
                        if purl:
                            post_urls.add(purl)
                    for purl in post_urls:
                        add_post(cur, platform, perfil_obj['username'], purl)
                    for item in commenters_items:
                        purl = normalize_post_url(platform, item.get('post_url')) if item.get('post_url') else None
                        uname = _extract_username(item)
                        if purl and uname:
                            f = _extract_fields(item)
                            photo_local = await _ensure_local_photo(f.get('photo_url'), uname)
                            upsert_profile(cur, platform, uname, f.get('full_name'), f.get('profile_url'), photo_local)
                            try:
                                add_comment(cur, platform, purl, uname)
                            except ValueError:
                                add_post(cur, platform, perfil_obj['username'], purl)
                                add_comment(cur, platform, purl, uname)

                    for rx in reactions or []:
                        purl = normalize_post_url(platform, rx.get('post_url')) if rx.get('post_url') else None
                        uname = _extract_username(rx)
                        if purl and uname:
                            f = _extract_fields(rx)
                            photo_local = await _ensure_local_photo(f.get('photo_url'), uname)
                            upsert_profile(cur, platform, uname, f.get('full_name'), f.get('profile_url'), photo_local)
                            add_post(cur, platform, perfil_obj['username'], purl)
                            try:
                                add_reaction(cur, platform, purl, uname, rx.get('reaction_type'))
                            except ValueError:
                                add_post(cur, platform, perfil_obj['username'], purl)
                                add_reaction(cur, platform, purl, uname, rx.get('reaction_type'))

                    conn.commit()

            # Rebuild relacionados desde DB para consolidar tipos (como en app.py)
            try:
                with get_conn() as conn2:
                    with conn2.cursor() as cur2:
                        relacionados = _build_related_from_db(cur2, platform, perfil_obj['username'])
            except Exception:
                # Fallback: múltiples apariciones por tipo si no podemos leer DB
                relacionados = []
                relacionados += [
                    {"username": u, "tipo de relacion": 'seguidor', "full_name": None, "profile_url": None, "photo_url": None}
                    for u in followers_usernames
                ]
                relacionados += [
                    {"username": u, "tipo de relacion": 'seguido', "full_name": None, "profile_url": None, "photo_url": None}
                    for u in following_usernames
                ]
                relacionados += [
                    {"username": u, "tipo de relacion": 'comentó', "full_name": None, "profile_url": None, "photo_url": None}
                    for u in commenters_usernames
                ]
                relacionados += [
                    {"username": u, "tipo de relacion": 'amigo', "full_name": None, "profile_url": None, "photo_url": None}
                    for u in friends_usernames
                ]
                relacionados += [
                    {"username": u, "tipo de relacion": 'reaccionó', "full_name": None, "profile_url": None, "photo_url": None}
                    for u in reactors_usernames
                ]

            # Asegurar rutas locales en la respuesta (si algo quedó externo accidentalmente)
            objetivo_out = {
                **perfil_obj,
                "photo_url": (
                    await local_or_proxy_photo_url(
                        perfil_obj.get("photo_url"),
                        perfil_obj.get("username"),
                        mode="download",
                        page=page,
                        on_failure='empty',
                        retries=5,
                        backoff_seconds=0.5,
                    ) if (perfil_obj.get("photo_url") and not str(perfil_obj.get("photo_url")).startswith('/storage/')) else perfil_obj.get("photo_url")
                ),
            }
            relacionados_out = [
                {
                    **item,
                    "photo_url": (
                        await local_or_proxy_photo_url(
                            item.get("photo_url"),
                            item.get("username"),
                            mode="download",
                            page=page,
                            on_failure='empty',
                            retries=5,
                            backoff_seconds=0.5,
                        ) if (item.get("photo_url") and item.get("username") and not str(item.get("photo_url")).startswith('/storage/')) else item.get("photo_url")
                    ),
                }
                for item in relacionados
            ]

            return {
                "Perfil objetivo": objetivo_out,
                "Perfiles relacionados": relacionados_out,
            }
        finally:
            await context.close()
            await browser.close()