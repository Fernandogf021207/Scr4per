from __future__ import annotations
from typing import Any, Dict, List
from .scraper import (
    obtener_datos_usuario_facebook,
    scrap_followers as fb_scrap_followers,
    scrap_followed as fb_scrap_followed,
    scrap_friends_all as fb_scrap_friends,
    scrap_comentarios_fotos as fb_scrap_comments,
    scrap_reacciones_fotos as fb_scrap_reactions,
)
from src.scrapers.base import PlatformScraper

class FacebookScraperAdapter(PlatformScraper):
    async def get_root_profile(self, username: str) -> Dict[str, Any]:
        perfil_url = f"https://www.facebook.com/{username}/"
        datos = await obtener_datos_usuario_facebook(self.page, perfil_url)
        return {
            'platform': 'facebook',
            'username': datos.get('username') or username,
            'full_name': datos.get('nombre_completo') or username,
            'profile_url': datos.get('url_usuario'),
            'photo_url': datos.get('foto_perfil'),
        }

    async def get_followers(self, username: str) -> List[dict]:
        perfil_url = f"https://www.facebook.com/{username}/"
        return await fb_scrap_followers(self.page, perfil_url, username)

    async def get_following(self, username: str) -> List[dict]:
        perfil_url = f"https://www.facebook.com/{username}/"
        return await fb_scrap_followed(self.page, perfil_url, username)

    async def get_friends(self, username: str) -> List[dict]:
        perfil_url = f"https://www.facebook.com/{username}/"
        return await fb_scrap_friends(self.page, perfil_url, username)

    async def get_commenters(self, username: str, max_items: int) -> List[dict]:
        perfil_url = f"https://www.facebook.com/{username}/"
        return await fb_scrap_comments(self.page, perfil_url, username, max_fotos=max_items)

    async def get_reactors(self, username: str, max_items: int) -> List[dict]:
        perfil_url = f"https://www.facebook.com/{username}/"
        return await fb_scrap_reactions(self.page, perfil_url, username, max_fotos=max_items, incluir_comentarios=False)
