import time
import logging
from src.utils.url import normalize_input_url
from .utils import obtener_foto_perfil_x, obtener_nombre_usuario_x

logger = logging.getLogger(__name__)

def _ts():
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

async def obtener_datos_usuario_principal(page, perfil_url, rid: str | None = None):
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.profile start url={perfil_url}{ridp}")
    t0 = time.time()
    await page.goto(perfil_url)
    try:
        await page.wait_for_selector('article, div', timeout=1800)
    except Exception:
        await page.wait_for_timeout(600)
    datos_usuario_x = await obtener_nombre_usuario_x(page)
    username = datos_usuario_x['username']
    nombre_completo = datos_usuario_x['nombre_completo']
    foto_perfil = await obtener_foto_perfil_x(page)
    logger.info(f"{_ts()} x.profile detected username={username} name={nombre_completo} duration_ms={(time.time()-t0)*1000:.0f}{ridp}")
    return {
        'username': username,
        'nombre_completo': nombre_completo,
        'foto_perfil': foto_perfil or "",
        'url_usuario': perfil_url
    }
