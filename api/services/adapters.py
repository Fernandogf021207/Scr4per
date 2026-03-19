from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional

from playwright.async_api import Browser, async_playwright

from src.utils.url import normalize_input_url
from src.utils.images import local_or_proxy_photo_url

logger = logging.getLogger(__name__)

async def launch_browser(headless: bool = True) -> Browser:
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
        ],
    )
    # Attach playwright instance for later stop()
    browser._scr4per_pw = pw  # type: ignore[attr-defined]
    return browser


async def close_browser(browser: Browser):
    try:
        await browser.close()
    finally:
        pw = getattr(browser, "_scr4per_pw", None)
        if pw:
            await pw.stop()


def _profile_url(platform: str, username: str) -> str:
    base = {
        'instagram': f"https://www.instagram.com/{username}/",
        'facebook': f"https://www.facebook.com/{username}/",
        'x': f"https://x.com/{username}",
    }.get(platform, f"https://x.com/{username}")
    return normalize_input_url(platform, base)


def _map_user_item_to_profile(platform: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Mapea estructura de build_user_item a nuestro ProfileItem."""
    return {
        'platform': platform,
        'username': item.get('username_usuario') or '',
        'full_name': item.get('nombre_usuario') or item.get('nombre_completo_usuario') or None,
        'profile_url': item.get('link_usuario') or None,
        'photo_url': item.get('foto_usuario') or item.get('url_foto') or None,
    }


CONTEXT_OPTS = {
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "locale": "es-ES",
    "timezone_id": "America/Mexico_City",
    "color_scheme": "light",
    "device_scale_factor": 1.25,
    "reduced_motion": "reduce",
    "viewport": {"width": 1280, "height": 900},
}


class InstagramAdapter:
    platform = 'instagram'

    def __init__(self, browser: Browser, tenant: Optional[str] = None, storage_state: Optional[Any] = None):
        self.browser = browser
        self.tenant = tenant
        self.storage_state = storage_state
        self._engagement_cache: Dict[tuple, Dict[str, List[Dict[str, Any]]]] = {}

    async def _new_page(self):
        context = await self.browser.new_context(storage_state=self.storage_state, **CONTEXT_OPTS)
        page = await context.new_page()
        try:
            logger.info("ctx.open platform=%s tenant=%s ctx=%s", self.platform, self.tenant, id(context))
        except Exception:
            pass
        return context, page

    async def get_root_profile(self, username: str, image_base_path: Optional[str] = None) -> Dict[str, Any]:
        from src.scrapers.instagram.scraper import obtener_datos_usuario_principal
        context, page = await self._new_page()
        try:
            perfil_url = _profile_url(self.platform, username)
            data = await obtener_datos_usuario_principal(page, perfil_url)
            # Build base profile
            prof = {
                'platform': self.platform,
                'username': data.get('username') or username,
                'full_name': data.get('nombre_completo') or None,
                'profile_url': data.get('url_usuario') or perfil_url,
                'photo_url': data.get('foto_perfil') or None,
            }
            # Ensure local image path
            if prof.get('photo_url'):
                platform_ftp = f"red_{self.platform}"
                
                # Prepare ftp_path
                ftp_path = image_base_path if image_base_path else None
                if ftp_path and not ftp_path.endswith('/'):
                    ftp_path += '/'
                
                prof['photo_url'] = await local_or_proxy_photo_url(
                    prof['photo_url'], 
                    username, 
                    platform_ftp, 
                    mode='download', 
                    photo_owner=prof['username'], 
                    page=page,
                    ftp_path=ftp_path
                )
            return prof
        finally:
            await context.close()

    async def get_followers(self, username: str, max_photos: int = 5, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        from src.scrapers.instagram.scraper import scrap_seguidores
        context, page = await self._new_page()
        try:
            logger.info("list.start platform=%s type=followers username=%s ctx=%s", self.platform, username, id(context))
            perfil_url = _profile_url(self.platform, username)
            rows = await scrap_seguidores(page, perfil_url, username)
            platform_ftp = f"red_{self.platform}"
            
            # Prepare ftp_path
            ftp_path = image_base_path if image_base_path else None
            if ftp_path and not ftp_path.endswith('/'):
                ftp_path += '/'

            out: List[Dict[str, Any]] = []
            for r in rows:
                item = _map_user_item_to_profile(self.platform, r)
                out.append(item)
            
            import asyncio
            async def process_image(item):
                if item.get('photo_url'):
                    try:
                        item['photo_url'] = await local_or_proxy_photo_url(
                            item['photo_url'], 
                            username, 
                            platform_ftp, 
                            mode='download', 
                            photo_owner=item['username'], 
                            page=page,
                            ftp_path=ftp_path
                        )
                    except Exception:
                        pass
            
            if out:
                await asyncio.gather(*(process_image(item) for item in out))

            return out
        finally:
            await context.close()

    async def get_following(self, username: str, max_photos: int = 5, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        from src.scrapers.instagram.scraper import scrap_seguidos
        context, page = await self._new_page()
        try:
            logger.info("list.start platform=%s type=following username=%s ctx=%s", self.platform, username, id(context))
            perfil_url = _profile_url(self.platform, username)
            rows = await scrap_seguidos(page, perfil_url, username)
            platform_ftp = f"red_{self.platform}"
            
            # Prepare ftp_path
            ftp_path = image_base_path if image_base_path else None
            if ftp_path and not ftp_path.endswith('/'):
                ftp_path += '/'

            out: List[Dict[str, Any]] = []
            for r in rows:
                item = _map_user_item_to_profile(self.platform, r)
                out.append(item)
            
            import asyncio
            async def process_image(item):
                if item.get('photo_url'):
                    try:
                        item['photo_url'] = await local_or_proxy_photo_url(
                            item['photo_url'], 
                            username, 
                            platform_ftp, 
                            mode='download', 
                            photo_owner=item['username'], 
                            page=page,
                            ftp_path=ftp_path
                        )
                    except Exception:
                        pass
            
            if out:
                await asyncio.gather(*(process_image(item) for item in out))

            return out
        finally:
            await context.close()

    async def _get_post_engagement_bundle(self, username: str, max_photos: int = 5, image_base_path: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Extrae likes+comentarios en una sola pasada y cachea por request/adapter."""
        cache_key = (username, int(max_photos), image_base_path or '')
        if cache_key in self._engagement_cache:
            return self._engagement_cache[cache_key]

        from src.scrapers.instagram.scrapling_spider import scrap_post_engagements_scrapling
        context, page = await self._new_page()
        try:
            logger.info("list.start platform=%s type=post_engagement_bundle username=%s ctx=%s", self.platform, username, id(context))
            perfil_url = _profile_url(self.platform, username)
            result = await scrap_post_engagements_scrapling(page, perfil_url, username, max_posts=max_photos)

            reactions_rows = result.get('reactions', []) or []
            comments_rows = result.get('comments', []) or []

            reactions_out: List[Dict[str, Any]] = [_map_user_item_to_profile(self.platform, r) for r in reactions_rows]
            comments_out: List[Dict[str, Any]] = [_map_user_item_to_profile(self.platform, r) for r in comments_rows]

            platform_ftp = f"red_{self.platform}"
            ftp_path = image_base_path if image_base_path else None
            if ftp_path and not ftp_path.endswith('/'):
                ftp_path += '/'

            import asyncio

            async def process_image(item):
                if item.get('photo_url'):
                    try:
                        item['photo_url'] = await local_or_proxy_photo_url(
                            item['photo_url'],
                            username,
                            platform_ftp,
                            mode='download',
                            photo_owner=item['username'],
                            page=page,
                            ftp_path=ftp_path
                        )
                    except Exception:
                        pass

            combined = reactions_out + comments_out
            if combined:
                await asyncio.gather(*(process_image(item) for item in combined))

            payload = {
                'reactions': reactions_out,
                'comments': comments_out,
            }
            self._engagement_cache[cache_key] = payload
            return payload
        finally:
            await context.close()

    async def get_post_reactors(self, username: str, max_photos: int = 5, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        bundle = await self._get_post_engagement_bundle(username, max_photos=max_photos, image_base_path=image_base_path)
        return list(bundle.get('reactions', []))

    async def get_post_commenters(self, username: str, max_photos: int = 5, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        bundle = await self._get_post_engagement_bundle(username, max_photos=max_photos, image_base_path=image_base_path)
        return list(bundle.get('comments', []))

    async def get_friends(self, username: str) -> List[Dict[str, Any]]:
        return []


class FacebookAdapter:
    platform = 'facebook'

    def __init__(self, browser: Browser, tenant: Optional[str] = None, process_images: bool = True, storage_state: Optional[Any] = None):
        self.browser = browser
        self.tenant = tenant
        self.process_images = process_images
        self.storage_state = storage_state
        self._shared_context = None
        self._shared_page = None

    async def _new_page(self):
        if self._shared_context is not None and self._shared_page is not None:
            return self._shared_context, self._shared_page, False
        context = await self.browser.new_context(storage_state=self.storage_state, **CONTEXT_OPTS)
        page = await context.new_page()
        try:
            logger.info("ctx.open platform=%s tenant=%s ctx=%s", self.platform, self.tenant, id(context))
        except Exception:
            pass
        return context, page, True

    async def open_flow_session(self):
        if self._shared_context is not None and self._shared_page is not None:
            return
        context, page, _ = await self._new_page()
        self._shared_context = context
        self._shared_page = page

    async def close_flow_session(self):
        if self._shared_context is None:
            return
        context = self._shared_context
        self._shared_context = None
        self._shared_page = None
        await context.close()

    async def _maybe_process_images(self, items: List[Dict[str, Any]], username: str, page, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.process_images or not items:
            return items

        platform_ftp = f"red_{self.platform}"
        ftp_path = image_base_path if image_base_path else None
        if ftp_path and not ftp_path.endswith('/'):
            ftp_path += '/'

        import asyncio

        async def process_image(item):
            if item.get('photo_url'):
                try:
                    item['photo_url'] = await local_or_proxy_photo_url(
                        item['photo_url'],
                        username,
                        platform_ftp,
                        mode='download',
                        photo_owner=item['username'],
                        page=page,
                        ftp_path=ftp_path,
                    )
                except Exception:
                    pass

        await asyncio.gather(*(process_image(item) for item in items))
        return items

    async def get_root_profile(self, username: str, image_base_path: Optional[str] = None) -> Dict[str, Any]:
        from src.scrapers.facebook.scraper import obtener_datos_usuario_facebook
        context, page, should_close = await self._new_page()
        try:
            perfil_url = _profile_url(self.platform, username)
            data = await obtener_datos_usuario_facebook(page, perfil_url)
            prof = {
                'platform': self.platform,
                'username': data.get('username') or username,
                'full_name': data.get('nombre_completo') or None,
                'profile_url': data.get('url_usuario') or perfil_url,
                'photo_url': data.get('foto_perfil') or None,
            }
            if self.process_images and prof.get('photo_url'):
                ftp_path = image_base_path if image_base_path else None
                if ftp_path and not ftp_path.endswith('/'):
                    ftp_path += '/'
                prof['photo_url'] = await local_or_proxy_photo_url(
                    prof['photo_url'],
                    username,
                    f"red_{self.platform}",
                    mode='download',
                    photo_owner=prof['username'],
                    page=page,
                    ftp_path=ftp_path,
                )
            return prof
        finally:
            if should_close:
                await context.close()

    async def _list(self, username: str, lista: str, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        from src.scrapers.facebook.scraper import (
            scrap_friends_all,
            scrap_followed,
            scrap_followers,
        )
        context, page, should_close = await self._new_page()
        try:
            logger.info("list.start platform=%s type=%s username=%s ctx=%s", self.platform, lista, username, id(context))
            perfil_url = _profile_url(self.platform, username)
            fetcher = {
                'followers': scrap_followers,
                'followed': scrap_followed,
                'friends_all': scrap_friends_all,
            }.get(lista)
            if fetcher is None:
                logger.warning("list.unsupported platform=%s type=%s username=%s", self.platform, lista, username)
                return []

            rows = await fetcher(page, perfil_url, username)
            platform_ftp = f"red_{self.platform}"
            
            # Prepare ftp_path
            ftp_path = image_base_path if image_base_path else None
            if ftp_path and not ftp_path.endswith('/'):
                ftp_path += '/'

            out: List[Dict[str, Any]] = []
            for r in rows:
                item = _map_user_item_to_profile(self.platform, r)
                out.append(item)

            return await self._maybe_process_images(out, username, page, image_base_path=image_base_path)
        finally:
            if should_close:
                await context.close()

    async def get_followers(self, username: str, max_photos: int = 5, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self._list(username, 'followers', image_base_path)

    async def get_following(self, username: str, max_photos: int = 5, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self._list(username, 'followed', image_base_path)

    async def get_friends(self, username: str) -> List[Dict[str, Any]]:
        return await self._list(username, 'friends_all')

    async def get_photo_reactors(self, username: str, max_photos: int = 5, include_comment_reactions: bool = False, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Devuelve perfiles que reaccionaron a las últimas fotos públicas del usuario.
        Nota: La relación en orquestador será 'reacted'.
        """
        from src.scrapers.facebook.scraper import scrap_reacciones_fotos
        context, page, should_close = await self._new_page()
        try:
            logger.info("list.start platform=%s type=photo_reactors username=%s ctx=%s", self.platform, username, id(context))
            perfil_url = _profile_url(self.platform, username)
            rows = await scrap_reacciones_fotos(page, perfil_url, username, max_fotos=max_photos, incluir_comentarios=include_comment_reactions)

            out: List[Dict[str, Any]] = []
            for r in rows:
                item = _map_user_item_to_profile(self.platform, r)
                out.append(item)

            return await self._maybe_process_images(out, username, page, image_base_path=image_base_path)
        finally:
            if should_close:
                await context.close()

    async def get_photo_commenters(self, username: str, max_photos: int = 5, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Devuelve perfiles que comentaron en las últimas fotos públicas del usuario.
        Nota: La relación en orquestador será 'commented'.
        """
        from src.scrapers.facebook.scraper import scrap_comentarios_fotos
        context, page, should_close = await self._new_page()
        try:
            logger.info("list.start platform=%s type=photo_commenters username=%s ctx=%s", self.platform, username, id(context))
            perfil_url = _profile_url(self.platform, username)
            rows = await scrap_comentarios_fotos(page, perfil_url, username, max_fotos=max_photos)

            out: List[Dict[str, Any]] = []
            for r in rows:
                item = _map_user_item_to_profile(self.platform, r)
                out.append(item)

            return await self._maybe_process_images(out, username, page, image_base_path=image_base_path)
        finally:
            if should_close:
                await context.close()


class XAdapter:
    platform = 'x'

    def __init__(self, browser: Browser, tenant: Optional[str] = None, storage_state: Optional[Any] = None):
        self.browser = browser
        self.tenant = tenant
        self.storage_state = storage_state

    async def _new_page(self):
        context = await self.browser.new_context(storage_state=self.storage_state, **CONTEXT_OPTS)
        page = await context.new_page()
        try:
            logger.info("ctx.open platform=%s tenant=%s ctx=%s", self.platform, self.tenant, id(context))
        except Exception:
            pass
        return context, page

    async def get_root_profile(self, username: str, image_base_path: Optional[str] = None) -> Dict[str, Any]:
        from src.scrapers.x.utils import obtener_nombre_usuario_x, obtener_foto_perfil_x
        context, page = await self._new_page()
        try:
            perfil_url = _profile_url(self.platform, username)
            await page.goto(perfil_url)
            await page.wait_for_timeout(3000)
            data = await obtener_nombre_usuario_x(page)
            foto = await obtener_foto_perfil_x(page)
            prof = {
                'platform': self.platform,
                'username': data.get('username') or username,
                'full_name': data.get('nombre_completo') or None,
                'profile_url': perfil_url,
                'photo_url': foto or None,
            }
            if prof.get('photo_url'):
                platform_ftp = f"red_{self.platform}"
                # If image_base_path is provided, ensure it ends with / to be treated as directory
                ftp_path = image_base_path if image_base_path else None
                if ftp_path and not ftp_path.endswith('/'):
                    ftp_path += '/'
                
                prof['photo_url'] = await local_or_proxy_photo_url(
                    prof['photo_url'], 
                    username, 
                    platform_ftp, 
                    mode='download', 
                    photo_owner=prof['username'], 
                    page=page,
                    ftp_path=ftp_path
                )
            return prof
        finally:
            await context.close()

    async def _list(self, username: str, list_suffix: str, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        from src.scrapers.x.scraper import extraer_usuarios_lista
        context, page = await self._new_page()
        try:
            logger.info("list.start platform=%s type=%s username=%s ctx=%s", self.platform, list_suffix, username, id(context))
            perfil_url = _profile_url(self.platform, username)
            list_url = normalize_input_url('x', f"{perfil_url.rstrip('/')}/{list_suffix}")
            await page.goto(list_url)
            await page.wait_for_timeout(3000)
            rows = await extraer_usuarios_lista(page, tipo_lista=list_suffix)
            platform_ftp = f"red_{self.platform}"
            
            # Prepare ftp_path for list items
            ftp_path = image_base_path if image_base_path else None
            if ftp_path and not ftp_path.endswith('/'):
                ftp_path += '/'

            out: List[Dict[str, Any]] = []
            for r in rows:
                item = _map_user_item_to_profile(self.platform, r)
                out.append(item)
            
            # Process images in parallel
            import asyncio
            
            async def process_image(profile_item):
                if profile_item.get('photo_url'):
                    try:
                        profile_item['photo_url'] = await local_or_proxy_photo_url(
                            profile_item['photo_url'], 
                            username, 
                            platform_ftp, 
                            mode='download', 
                            photo_owner=profile_item['username'], 
                            page=page,
                            ftp_path=ftp_path
                        )
                    except Exception as e:
                        logger.warning(f"Failed to process image for {profile_item.get('username')}: {e}")

            if out:
                await asyncio.gather(*(process_image(item) for item in out))

            return out
        finally:
            await context.close()

    async def get_followers(self, username: str, max_photos: int = 5, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self._list(username, 'followers', image_base_path)

    async def get_following(self, username: str, max_photos: int = 5, image_base_path: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self._list(username, 'following', image_base_path)

    async def get_friends(self, username: str) -> List[Dict[str, Any]]:
        return []


def get_adapter(platform: str, browser: Browser, tenant: Optional[str] = None, process_images: bool = True, storage_state: Optional[Any] = None):
    if platform == 'instagram':
        return InstagramAdapter(browser, tenant, storage_state=storage_state)
    if platform == 'facebook':
        return FacebookAdapter(browser, tenant, process_images=process_images, storage_state=storage_state)
    return XAdapter(browser, tenant, storage_state=storage_state)
