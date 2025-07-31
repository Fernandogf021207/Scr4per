import logging
import asyncio
from urllib.parse import urljoin
from src.utils.common import limpiar_url

logger = logging.getLogger(__name__)

async def obtener_foto_perfil_facebook(page):
    """Intentar obtener la foto de perfil del usuario principal de Facebook"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    try:
        for selector in FACEBOOK_CONFIG["foto_selectors"]:
            foto_element = await page.query_selector(selector)
            if foto_element:
                src = await foto_element.get_attribute("src")
                if src and not src.startswith("data:") and "profile" in src.lower():
                    return src
        return None
    except Exception as e:
        logger.warning(f"No se pudo obtener foto de perfil: {e}")
        return None

async def obtener_nombre_usuario_facebook(page):
    """Obtener el nombre de usuario y nombre completo de Facebook"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    try:
        current_url = page.url
        username_from_url = current_url.rstrip('/').split('/')[-1].split('?')[0]
        
        if 'profile.php' in current_url:
            params = current_url.split('?')[1] if '?' in current_url else ''
            for param in params.split('&'):
                if param.startswith('id='):
                    username_from_url = param.split('=')[1]
                    break
        
        if username_from_url in ['friends', 'followers']:
            parts = current_url.split('/')
            username_from_url = parts[-2] if len(parts) > 2 else 'unknown'
        
        nombre_completo = None
        for selector in FACEBOOK_CONFIG["nombre_selectors"]:
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

async def procesar_usuarios_en_pagina_facebook(page, usuarios_dict, tipo_lista):
    """Procesar usuarios visibles en la página actual"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    try:
        elementos_usuarios = []
        for selector in FACEBOOK_CONFIG["user_cell_selectors"]:
            elementos_usuarios = await page.query_selector_all(selector)
            if elementos_usuarios and len(elementos_usuarios) > 0:
                break
        
        usuarios_procesados = 0
        
        for elemento in elementos_usuarios:
            try:
                enlace = None
                for selector_enlace in FACEBOOK_CONFIG["enlace_selectors"]:
                    enlace = await elemento.query_selector(selector_enlace)
                    if enlace:
                        break
                
                if not enlace:
                    continue
                    
                href = await enlace.get_attribute("href")
                if not href or not href.startswith('/'):
                    continue
                    
                if any(pattern in href for pattern in FACEBOOK_CONFIG["patterns_to_exclude"]):
                    continue
                
                url_usuario = f"https://www.facebook.com{href}"
                url_limpia = limpiar_url(url_usuario)
                username_usuario = href.strip('/').split('/')[-1]
                if 'profile.php' in href:
                    params = href.split('?')[1] if '?' in href else ''
                    for param in params.split('&'):
                        if param.startswith('id='):
                            username_usuario = param.split('=')[1]
                            break
                
                if (username_usuario.isdigit() and len(username_usuario) < 5) or len(username_usuario) > 50:
                    continue
                
                if url_limpia in usuarios_dict:
                    continue
                
                url_foto = ""
                for selector_img in FACEBOOK_CONFIG["img_selectors"]:
                    img_element = await elemento.query_selector(selector_img)
                    if img_element:
                        src = await img_element.get_attribute("src")
                        if src and not src.startswith("data:"):
                            url_foto = src
                            break
                
                nombre_completo_usuario = username_usuario
                for selector_nombre in FACEBOOK_CONFIG["nombre_usuario_selectors"]:
                    nombre_element = await elemento.query_selector(selector_nombre)
                    if nombre_element:
                        texto = await nombre_element.inner_text()
                        texto = texto.strip()
                        if (texto and 
                            not texto.startswith('@') and 
                            len(texto) > 1 and 
                            len(texto) <= 100 and
                            texto != username_usuario and
                            not texto.lower().startswith(("1 amigo", "2 amigos", "3 amigos"))):
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
                logger.warning(f"Error procesando usuario individual en {tipo_lista}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error general procesando usuarios en página: {e}")

    return usuarios_procesados

async def obtener_comentadores_facebook(page):
    """Extraer usuarios que han comentado en los posts del usuario principal"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    print("Cargando comentarios de posts...")
    comentadores_dict = {}
    
    scroll_attempts = 0
    max_scroll_attempts = FACEBOOK_CONFIG["max_scroll_attempts"]
    no_new_content_count = 0
    max_no_new_content = FACEBOOK_CONFIG["max_no_new_content"]
    posts_encontrados = 0
    max_posts = FACEBOOK_CONFIG["max_posts"]
    
    await page.wait_for_timeout(3000)
    
    while scroll_attempts < max_scroll_attempts and posts_encontrados < max_posts:
        try:
            posts = await page.query_selector_all(FACEBOOK_CONFIG["post_selectors"][0])
            if not posts:
                no_new_content_count += 1
                if no_new_content_count >= max_no_new_content:
                    print("  ✅ No más posts encontrados")
                    break
                print(f"  ⏳ No se encontraron posts en scroll {scroll_attempts + 1}")
                await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                await page.wait_for_timeout(FACEBOOK_CONFIG["scroll_pause_ms"])
                scroll_attempts += 1
                continue
            
            for post_index in range(posts_encontrados, min(len(posts), max_posts)):
                try:
                    posts = await page.query_selector_all(FACEBOOK_CONFIG["post_selectors"][0])
                    if post_index >= len(posts):
                        break
                        
                    post = posts[post_index]
                    post_link = await post.query_selector('a[href*="/posts/"], a[href*="/permalink.php"]')
                    if not post_link:
                        logger.warning(f"No se encontró enlace al post en el post {post_index + 1}")
                        continue
                        
                    post_url = urljoin("https://www.facebook.com", await post_link.get_attribute("href"))
                    logger.info(f"Procesando post: {post_url}")
                    
                    scroll_position = await page.evaluate("window.pageYOffset")
                    await page.goto(post_url)
                    await page.wait_for_timeout(5000)
                    
                    # Cargar más comentarios
                    for _ in range(3):
                        for selector in ['a[href*="comment_id"]', 'span:has-text("View more comments")', 'div[aria-label*="more comments"]']:
                            button = await page.query_selector(selector)
                            if button:
                                await button.click()
                                await page.wait_for_timeout(2000)
                    
                    for _ in range(3):
                        await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                        await page.wait_for_timeout(2000)
                    
                    comentarios_encontrados = False
                    for selector in FACEBOOK_CONFIG["comment_selectors"]:
                        comentarios = await page.query_selector_all(selector)
                        if comentarios:
                            comentarios_encontrados = True
                            logger.info(f"Encontrados {len(comentarios)} comentarios potenciales con selector: {selector}")
                            for comentario in comentarios:
                                try:
                                    enlace_usuario = await comentario.query_selector('a[href^="/"]')
                                    if not enlace_usuario:
                                        logger.debug("No se encontró enlace de usuario en el comentario")
                                        continue
                                        
                                    href = await enlace_usuario.get_attribute("href")
                                    if not href or any(p in href for p in ['/posts/', '/permalink.php']):
                                        logger.debug(f"Enlace inválido: {href}")
                                        continue
                                        
                                    url_usuario = f"https://www.facebook.com{href}"
                                    url_limpia = limpiar_url(url_usuario)
                                    username_usuario = href.strip('/').split('/')[-1]
                                    if 'profile.php' in href:
                                        params = href.split('?')[1] if '?' in href else ''
                                        for param in params.split('&'):
                                            if param.startswith('id='):
                                                username_usuario = param.split('=')[1]
                                                break
                                    
                                    if (username_usuario.isdigit() and len(username_usuario) < 5) or len(username_usuario) > 50:
                                        logger.debug(f"Username inválido: {username_usuario}")
                                        continue
                                        
                                    if url_limpia in comentadores_dict:
                                        logger.debug(f"Usuario duplicado: {url_limpia}")
                                        continue
                                        
                                    url_foto = ""
                                    for img_selector in FACEBOOK_CONFIG["img_selectors"]:
                                        img_element = await comentario.query_selector(img_selector)
                                        if img_element:
                                            src = await img_element.get_attribute("src")
                                            if src and not src.startswith("data:"):
                                                url_foto = src
                                                break
                                    
                                    nombre_completo = username_usuario
                                    for nombre_selector in FACEBOOK_CONFIG["nombre_usuario_selectors"]:
                                        nombre_element = await comentario.query_selector(nombre_selector)
                                        if nombre_element:
                                            texto = await nombre_element.inner_text()
                                            texto = texto.strip()
                                            if (texto and 
                                                not texto.startswith('@') and 
                                                len(texto) > 1 and
                                                not texto.lower().startswith(("1 amigo", "2 amigos", "3 amigos"))):
                                                nombre_completo = texto
                                                break
                                    
                                    comentadores_dict[url_limpia] = {
                                        "nombre_usuario": nombre_completo,
                                        "username_usuario": username_usuario,
                                        "link_usuario": url_limpia,
                                        "foto_usuario": url_foto,
                                        "post_url": post_url
                                    }
                                    logger.info(f"Comentador añadido: @{username_usuario}")
                                    
                                except Exception as e:
                                    logger.warning(f"Error procesando comentario: {e}")
                                    continue
                            
                            break
                    
                    if not comentarios_encontrados:
                        logger.warning(f"No se encontraron comentarios en el post {post_url}")
                    
                    posts_encontrados += 1
                    print(f"  📝 Post {posts_encontrados}/{max_posts} procesado. Comentadores: {len(comentadores_dict)}")
                    
                    await page.go_back()
                    await page.wait_for_timeout(3000)
                    await page.evaluate(f"window.scrollTo(0, {scroll_position})")
                    await page.wait_for_timeout(2000)
                    
                except Exception as e:
                    logger.warning(f"Error procesando post {post_index + 1}: {e}")
                    continue
            
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            await page.wait_for_timeout(FACEBOOK_CONFIG["scroll_pause_ms"])
            scroll_attempts += 1
            
            if scroll_attempts % 5 == 0:
                print(f"  🔄 Pausa para evitar rate limiting... ({posts_encontrados} posts procesados)")
                await page.wait_for_timeout(FACEBOOK_CONFIG["rate_limit_pause_ms"])
                
        except Exception as e:
            logger.warning(f"Error en scroll {scroll_attempts}: {e}")
            no_new_content_count += 1
            await page.wait_for_timeout(1000)
    
    if not comentadores_dict:
        print("⚠️ No se encontraron comentadores. Posibles causas:")
        print("  - Los posts no tienen comentarios visibles")
        print("  - El perfil es privado o los comentarios están restringidos")
        print("  - La sesión no está autenticada o no tiene permisos")
        print("  - Facebook cambió la estructura de los comentarios")
    
    print(f"✅ Extracción de comentadores completada. Total: {len(comentadores_dict)}")
    return list(comentadores_dict.values())