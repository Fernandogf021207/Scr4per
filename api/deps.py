from typing import Dict
from .db import get_conn

SCHEMA_BY_PLATFORM: Dict[str, str] = {
    'x': 'red_x',
    'instagram': 'red_instagram',
    'facebook': 'red_facebook',
}

def _schema(platform: str) -> str:
    return SCHEMA_BY_PLATFORM.get(platform, 'red_x')

# Scraper storage-state helpers
from src.scrapers.facebook.config import FACEBOOK_CONFIG
from src.scrapers.instagram.config import INSTAGRAM_CONFIG
from src.scrapers.x.config import X_CONFIG

def storage_state_for(platform: str) -> str:
    if platform == 'facebook':
        return FACEBOOK_CONFIG.get('storage_state_path')
    if platform == 'instagram':
        return INSTAGRAM_CONFIG.get('storage_state_path')
    if platform == 'x':
        return X_CONFIG.get('storage_state_path')
    return ''