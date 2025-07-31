import logging

logger = logging.getLogger(__name__)

async def obtener_foto_perfil_x(page):
    """Intentar obtener la foto de perfil del usuario principal de X"""
    from src.scrapers.x.config import X_CONFIG
    try:
        for selector in X_CONFIG["foto_selectors"]:
            foto_element = await page.query_selector(selector)
            if foto_element:
                src = await foto_element.get_attribute("src")
                if src and not src.startswith("data:") and "profile_images" in src:
                    return src
        return None
    except Exception as e:
        logger.warning(f"No se pudo obtener foto de perfil: {e}")
        return None

async def obtener_nombre_usuario_x(page):
    """Obtener el nombre de usuario y nombre completo de X"""
    from src.scrapers.x.config import X_CONFIG
    try:
        current_url = page.url
        username_from_url = current_url.split('/')[-1] if not current_url.endswith('/') else current_url.split('/')[-2]
        username_from_url = username_from_url.split('?')[0]
        
        if username_from_url in ['followers', 'following']:
            parts = current_url.split('/')
            username_from_url = parts[-2] if len(parts) > 2 else 'unknown'
        
        nombre_completo = None
        for selector in X_CONFIG["nombre_selectors"]:
            element = await page.query_selector(selector)
            if element:
                text = await element.inner_text()
                text = text.strip()
                if text and not text.startswith('@') and text != username_from_url:
                    nombre_completo = text
                    break
        
        return {
            'username': username_from_url,
            'nombre_completo': nombre_completo or username_from_url
        }
    except Exception as e:
        logger.warning(f"Error obteniendo nombre de usuario: {e}")
        return {'username': 'unknown', 'nombre_completo': 'unknown'}

async def procesar_usuarios_en_pagina(page, usuarios_dict):
    """Procesar usuarios visibles en la página actual"""
    from src.scrapers.x.config import X_CONFIG
    from src.utils.common import limpiar_url
    try:
        elementos_usuarios = []
        for selector in X_CONFIG["user_cell_selectors"]:
            elementos_usuarios = await page.query_selector_all(selector)
            if elementos_usuarios and len(elementos_usuarios) > 0:
                break
        
        usuarios_procesados = 0
        
        for elemento in elementos_usuarios:
            try:
                enlace = None
                for selector_enlace in X_CONFIG["enlace_selectors"]:
                    enlace = await elemento.query_selector(selector_enlace)
                    if enlace:
                        break
                
                if not enlace:
                    continue
                    
                href = await enlace.get_attribute("href")
                if not href or not href.startswith('/'):
                    continue
                    
                if any(pattern in href for pattern in X_CONFIG["patterns_to_exclude"]):
                    continue
                
                url_usuario = f"https://x.com{href}"
                url_limpia = limpiar_url(url_usuario)
                username_usuario = href.strip('/').split('/')[-1]
                
                if (username_usuario.isdigit() or 
                    len(username_usuario) < 2 or 
                    len(username_usuario) > 50 or
                    username_usuario in ['followers', 'following', 'status']):
                    continue
                
                if url_limpia in usuarios_dict:
                    continue
                
                url_foto = ""
                for selector_img in X_CONFIG["img_selectors"]:
                    img_element = await elemento.query_selector(selector_img)
                    if img_element:
                        src = await img_element.get_attribute("src")
                        if src and not src.startswith("data:") and "profile_images" in src:
                            url_foto = src
                            break
                
                nombre_completo_usuario = username_usuario
                for selector_nombre in X_CONFIG["nombre_usuario_selectors"]:
                    nombre_element = await elemento.query_selector(selector_nombre)
                    if nombre_element:
                        texto = await nombre_element.inner_text()
                        texto = texto.strip()
                        if (texto and 
                            not texto.startswith('@') and 
                            len(texto) > 1 and 
                            len(texto) <= 100 and
                            texto != username_usuario):
                            nombre_completo_usuario = texto
                            break
                
                usuarios_dict[url_limpia] = {
                    "nombre_usuario": nombre_completo_usuario,
                    "username_usuario": username_usuario,
                    "link_usuario": url_limpia,
                    "foto_usuario": url_foto
                }
                
                usuarios_procesados += 1

            except Exception as e:
                logger.warning(f"Error procesando usuario individual: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error general procesando usuarios en página: {e}")

    return usuarios_procesados