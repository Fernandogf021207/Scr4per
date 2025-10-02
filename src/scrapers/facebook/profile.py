import time
import logging
from src.utils.common import limpiar_url
from src.utils.url import normalize_input_url
from src.scrapers.facebook.utils import get_text, get_attr

logger = logging.getLogger(__name__)

def _ts() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

async def obtener_datos_usuario_facebook(page, perfil_url: str) -> dict:
    """Obtiene nombre, username (slug o id) y foto del perfil principal (facebook)."""
    perfil_url = normalize_input_url('facebook', perfil_url)
    start = time.time()
    await page.goto(perfil_url)
    await page.wait_for_timeout(1200)
    logger.info(f"{_ts()} facebook.profile loaded duration_ms={(time.time()-start)*1000:.0f}")

    nombre = None
    selectores_nombre = [
        'h1 span',
        'div[data-pagelet="ProfileTilesFeed_0"] h1 span',
        'div[role="main"] h1',
        'h2[dir="auto"]',
    ]
    for sel in selectores_nombre:
        el = await page.query_selector(sel)
        if el:
            nombre = await get_text(el)
            if nombre:
                break

    current = page.url
    cleaned = limpiar_url(current)
    username = cleaned.split('facebook.com/')[-1].strip('/')
    if '?' in username:
        username = username.split('?')[0]

    foto = None
    foto_selectores = [
        'image[height][width]',
        'image[aria-label*="profile"][xlink\\:href]',  # escapar ':' en string literal
        'img[alt*="profile"], img[src*="scontent"]',
        'image', 'img'
    ]
    for fs in foto_selectores:
        try:
            el = await page.query_selector(fs)
            if el:
                src = await get_attr(el, 'xlink:href') or await get_attr(el, 'src')
                if src and not src.startswith('data:'):
                    foto = src
                    break
        except Exception:
            continue

    return {
        'username': username or 'unknown',
        'nombre_completo': nombre or username or 'unknown',
        'foto_perfil': foto or '',
        'url_usuario': cleaned or perfil_url,
    }
