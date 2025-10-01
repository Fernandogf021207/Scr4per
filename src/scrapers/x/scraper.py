import asyncio
from urllib.parse import urljoin
from src.utils.common import limpiar_url
from src.utils.url import normalize_input_url
from src.utils.dom import scroll_window
from src.utils.output import guardar_resultados
from src.utils.list_parser import build_user_item
from src.utils.url import normalize_post_url
from src.scrapers.x.utils import (
    obtener_foto_perfil_x,
    obtener_nombre_usuario_x,
    procesar_usuarios_en_pagina
)

import logging
logger = logging.getLogger(__name__)

async def extraer_usuarios_lista(page, tipo_lista="seguidores"):
    """Extraer usuarios de una lista (seguidores o seguidos) con scroll mejorado"""
    print(f"Cargando {tipo_lista}...")
    usuarios_dict = {}
    
    scroll_attempts = 0
    max_scroll_attempts = 50
    no_new_content_count = 0
    max_no_new_content = 5
    
    await page.wait_for_timeout(3000)
    
    while scroll_attempts < max_scroll_attempts and no_new_content_count < max_no_new_content:
        try:
            current_user_count = len(usuarios_dict)
            
            await scroll_window(page, 0)  # helper applies a sensible default
            
            await page.wait_for_timeout(2000)
            nuevos_usuarios_encontrados = await procesar_usuarios_en_pagina(page, usuarios_dict)
            
            if len(usuarios_dict) > current_user_count:
                no_new_content_count = 0
                print(f"list {tipo_lista}: {len(usuarios_dict)} users (scroll {scroll_attempts + 1})")
            else:
                no_new_content_count += 1
                print(f"list {tipo_lista}: no new users (scroll {scroll_attempts + 1}, empty_attempts={no_new_content_count})")
            
            scroll_attempts += 1
            
            if scroll_attempts % 10 == 0:
                print(f"list {tipo_lista}: pause for rate limiting (collected={len(usuarios_dict)})")
                await page.wait_for_timeout(5000)
            
            is_at_bottom = await page.evaluate(
                "() => (window.innerHeight + window.pageYOffset) >= (document.body.scrollHeight - 1000)"
            )
            
            if is_at_bottom and no_new_content_count >= 3:
                print(f"list {tipo_lista}: end reached")
                break
                
        except Exception as e:
            logger.warning(f"Error en scroll {scroll_attempts}: {e}")
            no_new_content_count += 1
            
        await page.wait_for_timeout(1000)

    print(f"list {tipo_lista}: scrolls={scroll_attempts}, unique_users={len(usuarios_dict)}")
    
    return list(usuarios_dict.values())

async def extraer_comentadores_x(page, max_posts=10):
    """Extraer usuarios que han comentado en los posts del usuario principal"""
    print("posts: commenters scan start")
    comentadores_dict = {}
    
    scroll_attempts = 0
    max_scroll_attempts = 30
    no_new_content_count = 0
    max_no_new_content = 5
    posts_encontrados = 0
    
    await page.wait_for_timeout(3000)
    
    while scroll_attempts < max_scroll_attempts and posts_encontrados < max_posts:
        try:
            posts = await page.query_selector_all('article[data-testid="tweet"]')
            if not posts:
                no_new_content_count += 1
                if no_new_content_count >= max_no_new_content:
                    print("posts: no more posts")
                    break
                print(f"posts: none found in scroll {scroll_attempts + 1}")
                await scroll_window(page, 0)
                await page.wait_for_timeout(2000)
                scroll_attempts += 1
                continue
            
            for post_index in range(posts_encontrados, min(len(posts), max_posts)):
                try:
                    posts = await page.query_selector_all('article[data-testid="tweet"]')
                    if post_index >= len(posts):
                        break
                        
                    post = posts[post_index]
                    post_link = await post.query_selector('a[href*="/status/"]')
                    if not post_link:
                        logger.warning(f"No se encontró enlace al post en el post {post_index + 1}")
                        continue
                        
                    post_url = urljoin("https://x.com", await post_link.get_attribute("href"))
                    logger.info(f"Procesando post: {post_url}")
                    
                    scroll_position = await page.evaluate("window.pageYOffset")
                    await page.goto(post_url)
                    await page.wait_for_timeout(5000)
                    
                    for _ in range(3):
                        await scroll_window(page, 0)
                        await page.wait_for_timeout(2000)
                    
                    comment_selectors = [
                        'div[data-testid="tweet"]:has(a[role="link"][href^="/"])',
                        'article[role="article"]:has(div[data-testid="tweetText"])',
                        'div[role="article"]:has(a[href^="/"][role="link"])'
                    ]
                    
                    comentarios_encontrados = False
                    for selector in comment_selectors:
                        comentarios = await page.query_selector_all(selector)
                        if comentarios:
                            comentarios_encontrados = True
                            logger.info(f"Encontrados {len(comentarios)} comentarios potenciales con selector: {selector}")
                            for comentario in comentarios:
                                try:
                                    enlace_usuario = await comentario.query_selector('a[role="link"][href^="/"]:not([href*="/status/"])')
                                    if not enlace_usuario:
                                        logger.debug("No se encontró enlace de usuario en el comentario")
                                        continue
                                        
                                    href = await enlace_usuario.get_attribute("href")
                                    if not href or '/status/' in href:
                                        logger.debug(f"Enlace inválido: {href}")
                                        continue
                                        
                                    url_usuario = f"https://x.com{href}"
                                    # Build normalized item
                                    item = build_user_item('x', url_usuario, None, None)
                                    url_limpia = item['link_usuario']
                                    username_usuario = item['username_usuario']
                                    
                                    if (username_usuario.isdigit() or 
                                        len(username_usuario) < 2 or 
                                        len(username_usuario) > 50):
                                        logger.debug(f"Username inválido: {username_usuario}")
                                        continue
                                        
                                    if url_limpia in comentadores_dict:
                                        logger.debug(f"Usuario duplicado: {url_limpia}")
                                        continue
                                        
                                    url_foto = ""
                                    img_selectors = [
                                        'img[src*="profile_images"]',
                                        'img[alt*="avatar"]',
                                        'div[data-testid="UserAvatar-Container-"] img'
                                    ]
                                    for img_selector in img_selectors:
                                        img_element = await comentario.query_selector(img_selector)
                                        if img_element:
                                            src = await img_element.get_attribute("src")
                                            if src and not src.startswith("data:"):
                                                url_foto = src
                                                break
                                    
                                    nombre_completo = username_usuario
                                    nombre_selectors = [
                                        'div[dir="ltr"] > span:first-child',
                                        'span[dir="ltr"]:not(:has(span))',
                                        'div[data-testid="UserName"] span:first-child'
                                    ]
                                    for nombre_selector in nombre_selectors:
                                        nombre_element = await comentario.query_selector(nombre_selector)
                                        if nombre_element:
                                            texto = await nombre_element.inner_text()
                                            texto = texto.strip()
                                            if texto and not texto.startswith('@') and len(texto) > 1:
                                                nombre_completo = texto
                                                break
                                    
                                    # finalize item
                                    item = build_user_item('x', url_usuario, nombre_completo, url_foto)
                                    item['post_url'] = normalize_post_url('x', post_url)
                                    comentadores_dict[url_limpia] = item
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
            
            await scroll_window(page, 0)
            await page.wait_for_timeout(2000)
            scroll_attempts += 1
            
            if scroll_attempts % 5 == 0:
                print(f"posts: rate limit pause (processed={posts_encontrados})")
                await page.wait_for_timeout(5000)
                
        except Exception as e:
            logger.warning(f"Error en scroll {scroll_attempts}: {e}")
            no_new_content_count += 1
            await page.wait_for_timeout(1000)
    
    if not comentadores_dict:
        print("⚠️ No se encontraron comentadores. Posibles causas:")
        print("  - Los posts no tienen comentarios visibles")
        print("  - El perfil es privado o los comentarios están restringidos")
        print("  - La sesión no está autenticada o no tiene permisos")
        print("  - X cambió la estructura de los comentarios")
    
    print(f"commenters: completed total={len(comentadores_dict)}")
    return list(comentadores_dict.values())

async def obtener_datos_usuario_principal(page, perfil_url):
    """Obtener datos del usuario principal"""
    print("Obteniendo datos del perfil principal...")
    await page.goto(perfil_url)
    await page.wait_for_timeout(5000)
    
    datos_usuario_x = await obtener_nombre_usuario_x(page)
    username = datos_usuario_x['username']
    nombre_completo = datos_usuario_x['nombre_completo']
    foto_perfil = await obtener_foto_perfil_x(page)
    
    print(f"Usuario detectado: @{username} ({nombre_completo})")
    
    return {
        'username': username,
        'nombre_completo': nombre_completo,
        'foto_perfil': foto_perfil or "",
        'url_usuario': perfil_url
    }

async def scrap_seguidores(page, perfil_url, username):
    """Scrapear seguidores del usuario"""
    print("followers: start")
    try:
        perfil_url = normalize_input_url('x', perfil_url)
        followers_url = f"{perfil_url.rstrip('/')}/followers"
        await page.goto(followers_url)
        await page.wait_for_timeout(3000)
        seguidores = await extraer_usuarios_lista(page, "seguidores")
        print(f"followers: count={len(seguidores)}")
        return seguidores
    except Exception as e:
        print(f"followers: error={e}")
        return []

async def scrap_seguidos(page, perfil_url, username):
    """Scrapear usuarios seguidos por el usuario"""
    print("following: start")
    try:
        perfil_url = normalize_input_url('x', perfil_url)
        following_url = f"{perfil_url.rstrip('/')}/following"
        await page.goto(following_url)
        await page.wait_for_timeout(3000)
        seguidos = await extraer_usuarios_lista(page, "seguidos")
        print(f"following: count={len(seguidos)}")
        return seguidos
    except Exception as e:
        print(f"following: error={e}")
        return []

async def scrap_comentadores(page, perfil_url, username, max_posts: int = 10):
    """Scrapear usuarios que comentaron los posts del usuario.
    max_posts limita la cantidad de posts del perfil objetivo a procesar.
    """
    print("commenters: start")
    try:
        perfil_url = normalize_input_url('x', perfil_url)
        await page.goto(perfil_url)
        await page.wait_for_timeout(3000)
        comentadores = await extraer_comentadores_x(page, max_posts=max_posts)
        print(f"commenters: count={len(comentadores)}")
        return comentadores
    except Exception as e:
        print(f"commenters: error={e}")
        return []