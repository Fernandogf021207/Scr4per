import logging
logger = logging.getLogger(__name__)

async def obtener_foto_perfil_instagram(page):
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    try:
        for selector in INSTAGRAM_CONFIG["foto_selectors"]:
            element = await page.query_selector(selector)
            if element:
                src = await element.get_attribute("src")
                if src and "cdninstagram" in src:
                    return src
        return None
    except Exception as e:
        logger.warning(f"No se pudo obtener foto de perfil: {e}")
        return None

async def obtener_nombre_usuario_instagram(page):
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    try:
        username = page.url.strip('/').split('/')[-1]
        nombre_completo = None
        for selector in INSTAGRAM_CONFIG["nombre_selectors"]:
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
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    from src.utils.common import limpiar_url
    try:
        elementos_usuarios = []
        for selector in INSTAGRAM_CONFIG["user_cell_selectors"]:
            elementos_usuarios = await page.query_selector_all(selector)
            if elementos_usuarios:
                break

        for elemento in elementos_usuarios:
            try:
                enlace = None
                for enlace_selector in INSTAGRAM_CONFIG["enlace_selectors"]:
                    enlace = await elemento.query_selector(enlace_selector)
                    if enlace:
                        break
                if not enlace:
                    continue

                href = await enlace.get_attribute("href")
                if not href or any(p in href for p in INSTAGRAM_CONFIG["patterns_to_exclude"]):
                    continue

                username_usuario = href.strip('/')
                url_usuario = f"https://www.instagram.com/{username_usuario}"
                url_limpia = limpiar_url(url_usuario)

                if url_limpia in usuarios_dict:
                    continue

                url_foto = ""
                for img_selector in INSTAGRAM_CONFIG["img_selectors"]:
                    img = await elemento.query_selector(img_selector)
                    if img:
                        src = await img.get_attribute("src")
                        if src and "cdninstagram" in src:
                            url_foto = src
                            break

                nombre_completo = username_usuario
                for nombre_selector in INSTAGRAM_CONFIG["nombre_usuario_selectors"]:
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
