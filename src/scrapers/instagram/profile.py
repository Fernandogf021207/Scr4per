import time
import logging
from src.utils.url import normalize_input_url

logger = logging.getLogger(__name__)

def _ts() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

async def obtener_foto_perfil_instagram(page):
    """Intentar obtener la foto de perfil del usuario principal de Instagram (helper aislado)."""
    try:
        selectores_foto = [
            'img[alt*="foto de perfil"]',
            'img[data-testid="user-avatar"]',
            'header img',
            'article header img',
            'div[role="button"] img',
        ]
        for selector in selectores_foto:
            foto_element = await page.query_selector(selector)
            if foto_element:
                src = await foto_element.get_attribute("src")
                if src and not src.startswith("data:"):
                    return src
        return None
    except Exception as e:
        logger.debug(f"ig.profile photo_error={e}")
        return None

async def obtener_nombre_usuario_instagram(page):
    """Obtener el nombre de usuario y nombre completo de Instagram (helper aislado)."""
    try:
        current_url = page.url
        username_from_url = current_url.split('/')[-2] if current_url.endswith('/') else current_url.split('/')[-1]
        username_from_url = username_from_url.split('?')[0]
        if username_from_url in ['followers', 'following']:
            parts = current_url.split('/')
            for i, part in enumerate(parts):
                if part in ['followers', 'following'] and i > 0:
                    username_from_url = parts[i-1]
                    break
        selectores_nombre = [
            'header section div div h2',
            'header h2',
            'article header h2',
            'h1',
            'h2'
        ]
        nombre_completo = None
        for selector in selectores_nombre:
            element = await page.query_selector(selector)
            if element:
                text = (await element.inner_text() or '').strip()
                if text and text != username_from_url:
                    nombre_completo = text
                    break
        return {'username': username_from_url, 'nombre_completo': nombre_completo or username_from_url}
    except Exception as e:
        logger.debug(f"ig.profile name_error={e}")
        return {'username': 'unknown', 'nombre_completo': 'unknown'}

async def obtener_datos_usuario_principal(page, perfil_url):
    logger.info(f"{_ts()} instagram.profile start")
    perfil_url = normalize_input_url('instagram', perfil_url)
    t0 = time.time()
    await page.goto(perfil_url)
    try:
        await page.wait_for_selector('header', timeout=1800)
    except Exception:
        await page.wait_for_timeout(600)
    datos_usuario_ig = await obtener_nombre_usuario_instagram(page)
    username = datos_usuario_ig['username']
    nombre_completo = datos_usuario_ig['nombre_completo']
    foto_perfil = await obtener_foto_perfil_instagram(page)
    logger.info(f"{_ts()} instagram.profile detected username={username} name={nombre_completo} duration_ms={(time.time()-t0)*1000:.0f}")
    return {
        'username': username,
        'nombre_completo': nombre_completo,
        'foto_perfil': foto_perfil or "",
        'url_usuario': perfil_url
    }
