from __future__ import annotations
from typing import Any, Dict, List
from .scraper import (
    obtener_datos_usuario_principal as x_obtener_datos,
    scrap_seguidores as x_scrap_followers,
    scrap_seguidos as x_scrap_following,
    scrap_comentadores as x_scrap_commenters,
)
from src.scrapers.base import PlatformScraper

class XScraperAdapter(PlatformScraper):
    async def get_root_profile(self, username: str) -> Dict[str, Any]:
        perfil_url = f"https://x.com/{username}"
        datos = await x_obtener_datos(self.page, perfil_url)
        return {
            'platform': 'x',
            'username': datos.get('username') or username,
            'full_name': datos.get('nombre_completo') or username,
            'profile_url': datos.get('url_usuario'),
            'photo_url': datos.get('foto_perfil'),
        }

    async def get_followers(self, username: str) -> List[dict]:
        perfil_url = f"https://x.com/{username}"
        return await x_scrap_followers(self.page, perfil_url, username)

    async def get_following(self, username: str) -> List[dict]:
        perfil_url = f"https://x.com/{username}"
        return await x_scrap_following(self.page, perfil_url, username)

    async def get_commenters(self, username: str, max_items: int) -> List[dict]:
        perfil_url = f"https://x.com/{username}"
        return await x_scrap_commenters(self.page, perfil_url, username, max_posts=max_items)
