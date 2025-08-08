import logging
logger = logging.getLogger(__name__)

async def obtener_foto_perfil_facebook(page):
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    try:
        for selector in FACEBOOK_CONFIG["foto_selectors"]:
            element = await page.query_selector(selector)
            if element:
                src = await element.get_attribute("xlink:href") or await element.get_attribute("src")
                if src and "scontent" in src:
                    return src
        return None
    except Exception as e:
        logger.warning(f"No se pudo obtener foto de perfil: {e}")
        return None

async def obtener_nombre_usuario_facebook(page):
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    try:
        current_url = page.url
        username = current_url.strip('/').split('/')[-1]
        nombre_completo = None
        for selector in FACEBOOK_CONFIG["nombre_selectors"]:
            element = await page.query_selector(selector)
            if element:
                text = await element.inner_text()
                if text:
                    nombre_completo = text.strip()
                    break
        return {
            'username': username,
            'nombre_completo': nombre_completo or username
        }
    except Exception as e:
        logger.warning(f"Error obteniendo nombre de usuario: {e}")
        return {'username': 'unknown', 'nombre_completo': 'unknown'}

async def procesar_usuarios_en_pagina(page, usuarios_dict):
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    from src.utils.common import limpiar_url
    try:
        elementos_usuarios = []
        for selector in FACEBOOK_CONFIG["user_cell_selectors"]:
            elementos_usuarios = await page.query_selector_all(selector)
            if elementos_usuarios:
                break

        for elemento in elementos_usuarios:
            try:
                enlace = None
                for selector in FACEBOOK_CONFIG["enlace_selectors"]:
                    enlace = await elemento.query_selector(selector)
                    if enlace:
                        break
                if not enlace:
                    continue

                href = await enlace.get_attribute("href")
                if not href or any(p in href for p in FACEBOOK_CONFIG["patterns_to_exclude"]):
                    continue

                username_usuario = href.strip('/').split('?')[0].split('/')[-1]
                url_usuario = f"https://www.facebook.com{href}" if href.startswith('/') else href
                url_limpia = limpiar_url(url_usuario)

                if url_limpia in usuarios_dict:
                    continue

                url_foto = ""
                for img_selector in FACEBOOK_CONFIG["img_selectors"]:
                    img = await elemento.query_selector(img_selector)
                    if img:
                        src = await img.get_attribute("src")
                        if src and "scontent" in src:
                            url_foto = src
                            break

                nombre_completo = username_usuario
                for nombre_selector in FACEBOOK_CONFIG["nombre_usuario_selectors"]:
                    nombre_element = await elemento.query_selector(nombre_selector)
                    if nombre_element:
                        texto = await nombre_element.inner_text()
                        if texto:
                            nombre_completo = texto.strip()
                            break

                usuarios_dict[url_limpia] = {
                    "nombre_usuario": nombre_completo,
                    "username_usuario": username_usuario,
                    "link_usuario": url_limpia,
                    "foto_usuario": url_foto
                }

            except Exception as e:
                logger.warning(f"Error procesando usuario individual: {e}")

        return len(usuarios_dict)
    except Exception as e:
        logger.error(f"Error general procesando usuarios: {e}")
        return 0