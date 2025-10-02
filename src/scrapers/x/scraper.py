import asyncio
from urllib.parse import urljoin
from src.utils.url import normalize_input_url
from src.utils.dom import scroll_window
from src.utils.list_parser import build_user_item
from src.utils.url import normalize_post_url
from src.scrapers.x.utils import (
    obtener_foto_perfil_x,
    obtener_nombre_usuario_x,
    procesar_usuarios_en_pagina
)
import time
import logging
logger = logging.getLogger(__name__)

def _ts():
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

async def extraer_usuarios_lista(page, tipo_lista="seguidores", rid: str | None = None):
    """Extraer usuarios de una lista con early-exit y métricas."""
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.list start type={tipo_lista}{ridp}")
    usuarios_dict = {}
    scroll_attempts = 0
    max_scroll_attempts = 40
    no_new_content_count = 0
    max_no_new_content = 4
    start = time.time()
    try:
        await page.wait_for_selector('div', timeout=1500)
    except Exception:
        await page.wait_for_timeout(500)
    while scroll_attempts < max_scroll_attempts and no_new_content_count < max_no_new_content:
        try:
            current_user_count = len(usuarios_dict)
            await scroll_window(page, 0)
            await page.wait_for_timeout(1000)
            await procesar_usuarios_en_pagina(page, usuarios_dict)
            if len(usuarios_dict) > current_user_count:
                no_new_content_count = 0
                logger.info(f"{_ts()} x.list progress type={tipo_lista} scroll={scroll_attempts+1} total={len(usuarios_dict)} new={len(usuarios_dict)-current_user_count}{ridp}")
            else:
                no_new_content_count += 1
                logger.info(f"{_ts()} x.list no_new type={tipo_lista} scroll={scroll_attempts+1} seq={no_new_content_count}{ridp}")
            
            scroll_attempts += 1
            if scroll_attempts % 12 == 0:
                await page.wait_for_timeout(1700)
            
            is_at_bottom = await page.evaluate(
                "() => (window.innerHeight + window.pageYOffset) >= (document.body.scrollHeight - 1000)"
            )
            
            if is_at_bottom and no_new_content_count >= 3:
                logger.info(f"{_ts()} x.list end_bottom type={tipo_lista}{ridp}")
                break
                
        except Exception as e:
            logger.warning(f"Error en scroll {scroll_attempts}: {e}")
            no_new_content_count += 1
            
        await page.wait_for_timeout(800)
    logger.info(f"{_ts()} x.list end type={tipo_lista} total={len(usuarios_dict)} scrolls={scroll_attempts} duration_ms={(time.time()-start)*1000:.0f}{ridp}")
    return list(usuarios_dict.values())

async def extraer_comentadores_x(page, max_posts=10, rid: str | None = None):
    """Extraer usuarios que comentaron (instrumentado)."""
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.commenters start target_posts={max_posts}{ridp}")
    comentadores_dict = {}
    
    scroll_attempts = 0
    max_scroll_attempts = 30
    no_new_content_count = 0
    max_no_new_content = 5
    posts_encontrados = 0
    
    try:
        await page.wait_for_selector('article[data-testid="tweet"]', timeout=1800)
    except Exception:
        await page.wait_for_timeout(600)
    
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
                    logger.info(f"{_ts()} x.commenters post start url={post_url}{ridp}")
                    
                    scroll_position = await page.evaluate("window.pageYOffset")
                    await page.goto(post_url)
                    await page.wait_for_timeout(1800)
                    
                    for _ in range(3):
                        await scroll_window(page, 0)
                        await page.wait_for_timeout(900)
                    
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
                            logger.info(f"{_ts()} x.commenters selector hit count={len(comentarios)} sel='{selector}'{ridp}")
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
                                    logger.info(f"{_ts()} x.commenters add username={username_usuario}{ridp}")
                                    
                                except Exception as e:
                                    logger.warning(f"Error procesando comentario: {e}")
                                    continue
                            
                            break
                    
                    if not comentarios_encontrados:
                        logger.warning(f"No se encontraron comentarios en el post {post_url}")
                    
                    posts_encontrados += 1
                    logger.info(f"{_ts()} x.commenters post_done idx={posts_encontrados}/{max_posts} total_commenters={len(comentadores_dict)}{ridp}")
                    
                    await page.go_back()
                    await page.wait_for_timeout(1200)
                    await page.evaluate(f"window.scrollTo(0, {scroll_position})")
                    await page.wait_for_timeout(1000)
                    
                except Exception as e:
                    logger.warning(f"Error procesando post {post_index + 1}: {e}")
                    continue
            
            await scroll_window(page, 0)
            await page.wait_for_timeout(2000)
            scroll_attempts += 1
            
            if scroll_attempts % 5 == 0:
                logger.info(f"{_ts()} x.commenters rate_pause processed={posts_encontrados}{ridp}")
                await page.wait_for_timeout(2500)
                
        except Exception as e:
            logger.warning(f"Error en scroll {scroll_attempts}: {e}")
            no_new_content_count += 1
            await page.wait_for_timeout(1000)
    
    if not comentadores_dict:
        logger.info(f"{_ts()} x.commenters empty_reason=NOT_FOUND_OR_PRIVATE{ridp}")
    logger.info(f"{_ts()} x.commenters done total={len(comentadores_dict)}{ridp}")
    return list(comentadores_dict.values())

async def obtener_datos_usuario_principal(page, perfil_url, rid: str | None = None):
    """Obtener datos del usuario principal (instrumentado)."""
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

async def scrap_seguidores(page, perfil_url, username, rid: str | None = None):
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.followers start{ridp}")
    try:
        perfil_url = normalize_input_url('x', perfil_url)
        followers_url = f"{perfil_url.rstrip('/')}/followers"
        await page.goto(followers_url)
        await page.wait_for_timeout(1200)
        seguidores = await extraer_usuarios_lista(page, "seguidores", rid=rid)
        logger.info(f"{_ts()} x.followers count={len(seguidores)}{ridp}")
        return seguidores
    except Exception as e:
        logger.warning(f"{_ts()} x.followers error={e}{ridp}")
        return []

async def scrap_seguidos(page, perfil_url, username, rid: str | None = None):
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.following start{ridp}")
    try:
        perfil_url = normalize_input_url('x', perfil_url)
        following_url = f"{perfil_url.rstrip('/')}/following"
        await page.goto(following_url)
        await page.wait_for_timeout(1200)
        seguidos = await extraer_usuarios_lista(page, "seguidos", rid=rid)
        logger.info(f"{_ts()} x.following count={len(seguidos)}{ridp}")
        return seguidos
    except Exception as e:
        logger.warning(f"{_ts()} x.following error={e}{ridp}")
        return []

async def scrap_comentadores(page, perfil_url, username, max_posts: int = 10, rid: str | None = None):
    """Scrapear usuarios que comentaron (instrumentado)."""
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.commenters root start max_posts={max_posts}{ridp}")
    try:
        perfil_url = normalize_input_url('x', perfil_url)
        await page.goto(perfil_url)
        await page.wait_for_timeout(1200)
        comentadores = await extraer_comentadores_x(page, max_posts=max_posts, rid=rid)
        logger.info(f"{_ts()} x.commenters root count={len(comentadores)}{ridp}")
        return comentadores
    except Exception as e:
        logger.warning(f"{_ts()} x.commenters root error={e}{ridp}")
        return []