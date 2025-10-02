from __future__ import annotations
import json
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

_CONFIG_CACHE: Optional[Dict[str, Any]] = None

DEFAULT_CONFIG_FILENAME = 'scrapers_config.json'


def load_global_config() -> Dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    # Config file placed inside src/scrapers/ for simple relative resolution
    base_dir = Path(__file__).resolve().parent
    path = base_dir / DEFAULT_CONFIG_FILENAME
    if not path.exists():
        logger.warning(f"scrapers.config file_missing path={path}")
        _CONFIG_CACHE = {}
        return _CONFIG_CACHE
    try:
        _CONFIG_CACHE = json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"scrapers.config load_error path={path} error={e}")
        _CONFIG_CACHE = {}
    return _CONFIG_CACHE or {}


def platform_config(platform: str) -> Dict[str, Any]:
    cfg = load_global_config().get(platform, {})
    return cfg


class PlatformScraper(ABC):
    """Interface base para scrapers de plataformas.
    Cada implementación debe envolver la lógica existente (functions) sin reescritura masiva inicial.
    """

    def __init__(self, page, platform: str):
        self.page = page
        self.platform = platform
        self.config = platform_config(platform)

    async def prepare_page(self):
        """Hook para aplicar headers / blocking adicional antes de scrapear cada root (opcional)."""
        return

    @abstractmethod
    async def get_root_profile(self, username: str) -> Dict[str, Any]:
        ...

    async def get_followers(self, username: str) -> list[dict]:  # noqa: D401
        return []

    async def get_following(self, username: str) -> list[dict]:
        return []

    async def get_friends(self, username: str) -> list[dict]:
        return []

    async def get_commenters(self, username: str, max_items: int) -> list[dict]:
        return []

    async def get_reactors(self, username: str, max_items: int) -> list[dict]:
        return []
