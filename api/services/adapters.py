from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from playwright.async_api import Browser, async_playwright

from ..deps import storage_state_for
from src.utils.url import normalize_input_url


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
        'full_name': item.get('nombre_usuario') or None,
        'profile_url': item.get('link_usuario') or None,
        'photo_url': item.get('foto_usuario') or None,
    }


class InstagramAdapter:
    platform = 'instagram'

    def __init__(self, browser: Browser):
        self.browser = browser

    async def _new_page(self):
        storage = storage_state_for(self.platform)
        context = await self.browser.new_context(storage_state=storage if storage else None)
        page = await context.new_page()
        return context, page

    async def get_root_profile(self, username: str) -> Dict[str, Any]:
        from src.scrapers.instagram.scraper import obtener_datos_usuario_principal
        context, page = await self._new_page()
        try:
            perfil_url = _profile_url(self.platform, username)
            data = await obtener_datos_usuario_principal(page, perfil_url)
            return {
                'platform': self.platform,
                'username': data.get('username') or username,
                'full_name': data.get('nombre_completo') or None,
                'profile_url': data.get('url_usuario') or perfil_url,
                'photo_url': data.get('foto_perfil') or None,
            }
        finally:
            await context.close()

    async def get_followers(self, username: str, max_photos: int = 5) -> List[Dict[str, Any]]:
        from src.scrapers.instagram.scraper import scrap_seguidores
        context, page = await self._new_page()
        try:
            perfil_url = _profile_url(self.platform, username)
            rows = await scrap_seguidores(page, perfil_url, username)
            return [_map_user_item_to_profile(self.platform, r) for r in rows]
        finally:
            await context.close()

    async def get_following(self, username: str, max_photos: int = 5) -> List[Dict[str, Any]]:
        from src.scrapers.instagram.scraper import scrap_seguidos
        context, page = await self._new_page()
        try:
            perfil_url = _profile_url(self.platform, username)
            rows = await scrap_seguidos(page, perfil_url, username)
            return [_map_user_item_to_profile(self.platform, r) for r in rows]
        finally:
            await context.close()

    async def get_friends(self, username: str) -> List[Dict[str, Any]]:
        return []


class FacebookAdapter:
    platform = 'facebook'

    def __init__(self, browser: Browser):
        self.browser = browser

    async def _new_page(self):
        storage = storage_state_for(self.platform)
        context = await self.browser.new_context(storage_state=storage if storage else None)
        page = await context.new_page()
        return context, page

    async def get_root_profile(self, username: str) -> Dict[str, Any]:
        from src.scrapers.facebook.scraper import obtener_datos_usuario_facebook
        context, page = await self._new_page()
        try:
            perfil_url = _profile_url(self.platform, username)
            data = await obtener_datos_usuario_facebook(page, perfil_url)
            return {
                'platform': self.platform,
                'username': data.get('username') or username,
                'full_name': data.get('nombre_completo') or None,
                'profile_url': data.get('url_usuario') or perfil_url,
                'photo_url': data.get('foto_perfil') or None,
            }
        finally:
            await context.close()

    async def _list(self, username: str, lista: str) -> List[Dict[str, Any]]:
        from src.scrapers.facebook.scraper import navegar_a_lista, extraer_usuarios_listado
        context, page = await self._new_page()
        try:
            perfil_url = _profile_url(self.platform, username)
            ok = await navegar_a_lista(page, perfil_url, lista)
            if not ok:
                return []
            rows = await extraer_usuarios_listado(page, lista, username)
            return [_map_user_item_to_profile(self.platform, r) for r in rows]
        finally:
            await context.close()

    async def get_followers(self, username: str, max_photos: int = 5) -> List[Dict[str, Any]]:
        return await self._list(username, 'followers')

    async def get_following(self, username: str, max_photos: int = 5) -> List[Dict[str, Any]]:
        return await self._list(username, 'followed')

    async def get_friends(self, username: str) -> List[Dict[str, Any]]:
        return await self._list(username, 'friends_all')


class XAdapter:
    platform = 'x'

    def __init__(self, browser: Browser):
        self.browser = browser

    async def _new_page(self):
        storage = storage_state_for(self.platform)
        context = await self.browser.new_context(storage_state=storage if storage else None)
        page = await context.new_page()
        return context, page

    async def get_root_profile(self, username: str) -> Dict[str, Any]:
        from src.scrapers.x.utils import obtener_nombre_usuario_x, obtener_foto_perfil_x
        context, page = await self._new_page()
        try:
            perfil_url = _profile_url(self.platform, username)
            await page.goto(perfil_url)
            await page.wait_for_timeout(3000)
            data = await obtener_nombre_usuario_x(page)
            foto = await obtener_foto_perfil_x(page)
            return {
                'platform': self.platform,
                'username': data.get('username') or username,
                'full_name': data.get('nombre_completo') or None,
                'profile_url': perfil_url,
                'photo_url': foto or None,
            }
        finally:
            await context.close()

    async def _list(self, username: str, list_suffix: str) -> List[Dict[str, Any]]:
        from src.scrapers.x.scraper import extraer_usuarios_lista
        context, page = await self._new_page()
        try:
            perfil_url = _profile_url(self.platform, username)
            list_url = normalize_input_url('x', f"{perfil_url.rstrip('/')}/{list_suffix}")
            await page.goto(list_url)
            await page.wait_for_timeout(3000)
            rows = await extraer_usuarios_lista(page, tipo_lista=list_suffix)
            return [_map_user_item_to_profile(self.platform, r) for r in rows]
        finally:
            await context.close()

    async def get_followers(self, username: str, max_photos: int = 5) -> List[Dict[str, Any]]:
        return await self._list(username, 'followers')

    async def get_following(self, username: str, max_photos: int = 5) -> List[Dict[str, Any]]:
        return await self._list(username, 'following')

    async def get_friends(self, username: str) -> List[Dict[str, Any]]:
        return []


def get_adapter(platform: str, browser: Browser):
    if platform == 'instagram':
        return InstagramAdapter(browser)
    if platform == 'facebook':
        return FacebookAdapter(browser)
    return XAdapter(browser)
