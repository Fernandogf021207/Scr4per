from typing import Dict, Optional
from .db import get_conn
import os
from paths import STORAGE_DIR

SCHEMA_BY_PLATFORM: Dict[str, str] = {
    'x': 'red_x',
    'instagram': 'red_instagram',
    'facebook': 'red_facebook',
}

def _schema(platform: str) -> str:
    return SCHEMA_BY_PLATFORM.get(platform, 'red_x')

# Scraper storage-state helpers
# Nota: Con el nuevo sistema de sesiones multi-usuario, las sesiones están en la DB.
# Estos paths son solo fallback para compatibilidad con código legacy.
from src.scrapers.instagram.config import INSTAGRAM_CONFIG
from src.scrapers.x.config import X_CONFIG

def storage_state_for(platform: str, tenant: Optional[str] = None) -> str:
    """Devuelve la ruta al storage_state.

    - Si tenant está presente, usa data/storage/{tenant}/{platform}_storage_state.json
    - Si no, usa la ruta global por defecto (data/storage/{platform}_storage_state.json)
    
    NOTA: Con el nuevo sistema multi-usuario, las sesiones deben obtenerse desde la DB
    usando ScrapingService en lugar de archivos locales.
    """
    if tenant:
        safe_tenant = ''.join(c for c in tenant if c.isalnum() or c in ('-', '_', '.'))[:80]
        tenant_dir = os.path.join(STORAGE_DIR, safe_tenant)
        os.makedirs(tenant_dir, exist_ok=True)
        return os.path.join(tenant_dir, f"{platform}_storage_state.json")

    # Fallback paths para compatibilidad con código legacy
    if platform == 'facebook':
        return 'data/storage/facebook_storage_state.json'
    if platform == 'instagram':
        return INSTAGRAM_CONFIG.get('storage_state_path')
    if platform == 'x':
        return X_CONFIG.get('storage_state_path')
    return ''