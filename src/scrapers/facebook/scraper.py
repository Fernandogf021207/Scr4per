import asyncio
import logging
from urllib.parse import urljoin
from src.scrapers.facebook.utils import (
    obtener_foto_perfil_facebook,
    obtener_nombre_usuario_facebook,
    procesar_usuarios_en_pagina
)
from src.utils.common import limpiar_url
logger = logging.getLogger(__name__)

async def obtener_datos_usuario_principal(page, perfil_url):
    print("Obteniendo datos del perfil principal de Facebook...")
    await page.goto(perfil_url)
    await page.wait_for_timeout(5000)
    datos_usuario = await obtener_nombre_usuario_facebook(page)
    foto = await obtener_foto_perfil_facebook(page)
    datos_usuario['foto_perfil'] = foto
    datos_usuario['url_usuario'] = perfil_url
    print(f"Usuario detectado: @{datos_usuario['username']} ({datos_usuario['nombre_completo']})")
    return datos_usuario

async def extraer_usuarios_lista(page, tipo_lista="amigos"):
    """Extraer usuarios de una lista (amigos, seguidores o seguidos) con scroll mejorado y rate limiting"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    
    print(f"Cargando {tipo_lista}...")
    usuarios_dict = {}
    
    scroll_attempts = 0
    max_scroll_attempts = FACEBOOK_CONFIG['max_scroll_attempts']
    no_new_content_count = 0
    max_no_new_content = FACEBOOK_CONFIG['max_no_new_content']
    
    await page.wait_for_timeout(3000)
    
    while scroll_attempts < max_scroll_attempts and no_new_content_count < max_no_new_content:
        try:
            current_user_count = len(usuarios_dict)
            
            # Scroll suave para evitar detección
            await page.evaluate("""
                () => {
                    const scrollHeight = document.body.scrollHeight;
                    const currentScroll = window.pageYOffset;
                    const clientHeight = window.innerHeight;
                    window.scrollBy(0, clientHeight * 0.8);
                }
            """)
            
            await page.wait_for_timeout(FACEBOOK_CONFIG['scroll_pause_ms'])
            
            # Procesar tarjetas de usuarios en la página actual
            await procesar_tarjetas_usuarios(page, usuarios_dict)
            
            if len(usuarios_dict) > current_user_count:
                no_new_content_count = 0
                print(f"  📊 {tipo_lista}: {len(usuarios_dict)} usuarios encontrados (scroll {scroll_attempts + 1})")
            else:
                no_new_content_count += 1
                print(f"  ⏳ Sin nuevos usuarios en scroll {scroll_attempts + 1} (intentos sin contenido: {no_new_content_count})")
            
            scroll_attempts += 1
            
            # Rate limiting - pausa cada 10 scrolls
            if scroll_attempts % 10 == 0:
                print(f"  🔄 Pausa para evitar rate limiting... ({len(usuarios_dict)} usuarios hasta ahora)")
                await page.wait_for_timeout(FACEBOOK_CONFIG['rate_limit_pause_ms'])
            
            # Verificar si llegamos al final de la página
            is_at_bottom = await page.evaluate("""
                () => {
                    return (window.innerHeight + window.pageYOffset) >= document.body.scrollHeight - 1000;
                }
            """)
            
            if is_at_bottom and no_new_content_count >= 3:
                print(f"  ✅ Llegamos al final de la lista de {tipo_lista}")
                break
                
        except Exception as e:
            logger.warning(f"Error en scroll {scroll_attempts}: {e}")
            no_new_content_count += 1
            
        await page.wait_for_timeout(1000)

    print(f"✅ Scroll completado para {tipo_lista}. Total de scrolls: {scroll_attempts}")
    print(f"📊 Usuarios únicos extraídos: {len(usuarios_dict)}")
    
    return list(usuarios_dict.values())

async def procesar_tarjetas_usuarios(page, usuarios_dict):
    """Procesar las tarjetas de usuarios visibles en la página actual"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    
    try:
        # Múltiples selectores para diferentes estructuras de Facebook
        tarjetas_selectors = [
            'div[role="main"] div:has(a[tabindex="0"])',
            'div[data-pagelet="ProfileAppSection_0"] div:has(a[href*="facebook.com"])',
            'div[aria-label="People"] div:has(a)',
            'div[role="main"] > div > div:has(a[role="link"])'
        ]
        
        tarjetas = []
        for selector in tarjetas_selectors:
            tarjetas = await page.query_selector_all(selector)
            if tarjetas:
                break
        
        if not tarjetas:
            logger.warning("No se encontraron tarjetas de usuarios")
            return
        
        for tarjeta in tarjetas:
            try:
                # Buscar enlaces de perfil
                enlaces_selectors = [
                    'a[tabindex="0"]',
                    'a[href*="facebook.com"]',
                    'a[role="link"]:not([href*="/photo"])'
                ]
                
                a_nombre = None
                for selector in enlaces_selectors:
                    a_nombre = await tarjeta.query_selector(selector)
                    if a_nombre:
                        break
                
                # Buscar imágenes de perfil
                img_selectors = [
                    'a[tabindex="-1"] img',
                    'img[src*="scontent"]',
                    'img[alt*="foto de perfil"]'
                ]
                
                a_img = None
                for selector in img_selectors:
                    a_img = await tarjeta.query_selector(selector)
                    if a_img:
                        break

                if not a_nombre:
                    continue

                nombre = await a_nombre.inner_text() if a_nombre else "Sin nombre"
                nombre = nombre.strip()
                perfil = await a_nombre.get_attribute("href") if a_nombre else None
                imagen = await a_img.get_attribute("src") if a_img else None
                
                if not perfil or not nombre:
                    continue
                
                perfil_limpio = limpiar_url(perfil)

                # Filtrar contenido no deseado
                if (nombre.lower().startswith(("1 amigo", "2 amigos", "3 amigos", "mutual friend")) or
                    any(pattern in perfil_limpio for pattern in FACEBOOK_CONFIG["patterns_to_exclude"])):
                    continue

                if perfil_limpio not in usuarios_dict:
                    usuarios_dict[perfil_limpio] = {
                        "nombre_usuario": nombre,
                        "username_usuario": nombre.replace(" ", "_").lower(),
                        "link_usuario": perfil_limpio,
                        "foto_usuario": imagen or ""
                    }

            except Exception as e:
                logger.warning(f"Error procesando tarjeta: {e}")
                
    except Exception as e:
        logger.warning(f"Error general procesando tarjetas: {e}")

async def scrap_amigos(page, perfil_url):
    """Scrapear amigos del usuario con scroll optimizado y rate limiting"""
    print("\n🔄 Navegando a la lista de amigos...")
    try:
        amigos_url = urljoin(perfil_url, "friends")
        await page.goto(amigos_url)
        await page.wait_for_timeout(6000)
        
        amigos = await extraer_usuarios_lista(page, "amigos")
        print(f"📊 Amigos encontrados: {len(amigos)}")
        return amigos
        
    except Exception as e:
        print(f"❌ Error extrayendo amigos: {e}")
        return []

async def scrap_seguidores(page, perfil_url):
    """Scrapear seguidores del usuario"""
    print("\n🔄 Navegando a la lista de seguidores...")
    try:
        # Facebook usa diferentes URLs para seguidores
        seguidores_urls = [
            urljoin(perfil_url, "followers"),
            urljoin(perfil_url, "friends_followers"),
            f"{perfil_url.rstrip('/')}/followers"
        ]
        
        for seguidores_url in seguidores_urls:
            try:
                await page.goto(seguidores_url)
                await page.wait_for_timeout(6000)
                
                # Verificar si la página cargó correctamente
                content = await page.content()
                if "followers" in content.lower() or "seguidores" in content.lower():
                    seguidores = await extraer_usuarios_lista(page, "seguidores")
                    print(f"📊 Seguidores encontrados: {len(seguidores)}")
                    return seguidores
                    
            except Exception as e:
                logger.warning(f"Error con URL {seguidores_url}: {e}")
                continue
        
        print("⚠️ No se pudo acceder a la lista de seguidores")
        return []
        
    except Exception as e:
        print(f"❌ Error extrayendo seguidores: {e}")
        return []

async def scrap_seguidos(page, perfil_url):
    """Scrapear usuarios seguidos por el usuario"""
    print("\n🔄 Navegando a la lista de seguidos...")
    try:
        # Facebook usa diferentes URLs para seguidos
        seguidos_urls = [
            urljoin(perfil_url, "following"),
            urljoin(perfil_url, "friends_following"),
            f"{perfil_url.rstrip('/')}/following"
        ]
        
        for seguidos_url in seguidos_urls:
            try:
                await page.goto(seguidos_url)
                await page.wait_for_timeout(6000)
                
                # Verificar si la página cargó correctamente
                content = await page.content()
                if "following" in content.lower() or "siguiendo" in content.lower():
                    seguidos = await extraer_usuarios_lista(page, "seguidos")
                    print(f"📊 Seguidos encontrados: {len(seguidos)}")
                    return seguidos
                    
            except Exception as e:
                logger.warning(f"Error con URL {seguidos_url}: {e}")
                continue
        
        print("⚠️ No se pudo acceder a la lista de seguidos")
        return []
        
    except Exception as e:
        print(f"❌ Error extrayendo seguidos: {e}")
        return []

async def scrap_comentadores_facebook(page, perfil_url):
    """Extraer usuarios que han comentado en los posts del usuario principal con rate limiting mejorado"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    
    print("\n🔄 Navegando al perfil para extraer comentadores...")
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(5000)

        comentadores_dict = {}
        posts_procesados = 0
        scroll_attempts = 0
        max_scroll_attempts = 20
        no_new_posts_count = 0
        max_no_new_posts = 3

        while (posts_procesados < FACEBOOK_CONFIG['max_posts'] and 
               scroll_attempts < max_scroll_attempts and 
               no_new_posts_count < max_no_new_posts):
            
            try:
                # Primero identificar posts de manera más estable
                posts_selectors = [
                    'div[role="article"]',
                    'div[data-pagelet="FeedUnit"]',
                    'div[data-ft*="top_level_post_id"]'
                ]
                
                posts = []
                for selector in posts_selectors:
                    posts = await page.query_selector_all(selector)
                    if posts:
                        print(f"  ✓ Encontrados {len(posts)} posts usando selector: {selector}")
                        break
                
                if not posts:
                    print("  ⚠️ No se encontraron posts en esta iteración")
                    no_new_posts_count += 1
                    await page.evaluate("window.scrollBy(0, window.innerHeight * 0.5)")
                    await page.wait_for_timeout(3000)
                    scroll_attempts += 1
                    continue
                
                current_posts_count = posts_procesados
                
                for post_index in range(posts_procesados, min(len(posts), FACEBOOK_CONFIG['max_posts'])):
                    try:
                        if post_index >= len(posts):
                            break
                        
                        # Re-obtener el post para evitar elementos desconectados del DOM
                        current_posts = await page.query_selector_all(posts_selectors[0])
                        if post_index >= len(current_posts):
                            print(f"  ⚠️ Post {post_index} ya no está disponible")
                            continue
                            
                        post = current_posts[post_index]
                        
                        # Verificar que el elemento esté conectado al DOM antes de hacer scroll
                        is_connected = await post.evaluate("element => element.isConnected")
                        if not is_connected:
                            print(f"  ⚠️ Post {post_index} no está conectado al DOM, saltando...")
                            continue
                        
                        print(f"  📝 Procesando post {post_index + 1}/{min(len(posts), FACEBOOK_CONFIG['max_posts'])}")
                        
                        # Scroll suave hacia el post
                        try:
                            await post.scroll_into_view_if_needed()
                            await page.wait_for_timeout(2000)
                        except Exception as scroll_error:
                            print(f"  ⚠️ Error haciendo scroll al post {post_index}: {scroll_error}")
                            # Intentar scroll manual como alternativa
                            await page.evaluate("window.scrollBy(0, 300)")
                            await page.wait_for_timeout(1000)
                        
                        # Buscar el contenedor de comentarios específico que proporcionaste
                        comment_container_selectors = [
                            # Selector específico del contenedor de comentarios
                            'div.x9f619.x1n2onr6.x1ja2u2z.x78zum5.xdt5ytf.x2lah0s.x193iq5w.xeuugli.x1icxu4v.x25sj25.x10b6aqq.x1yrsyyn',
                            # Selector del botón de comentarios
                            'div[role="button"][tabindex="0"] span[class*="html-span"] div.x1i10hfl',
                            # Selectores alternativos
                            'div[aria-label*="comentario" i]',
                            'div[role="button"]:has(i[style*="7H32i_pdCAf.png"])',
                            'span:has(span:contains("0"), span:contains("1"), span:contains("2"), span:contains("3"), span:contains("4"), span:contains("5"), span:contains("6"), span:contains("7"), span:contains("8"), span:contains("9"))'
                        ]
                        
                        comment_container = None
                        for selector in comment_container_selectors:
                            try:
                                comment_container = await post.query_selector(selector)
                                if comment_container:
                                    print(f"  ✓ Contenedor de comentarios encontrado con: {selector}")
                                    break
                            except Exception as e:
                                continue
                        
                        if comment_container:
                            try:
                                # Hacer clic en el contenedor de comentarios para expandirlos
                                print(f"  🖱️ Haciendo clic en contenedor de comentarios...")
                                await comment_container.click()
                                await page.wait_for_timeout(3000)
                                
                                # Esperar a que se carguen los comentarios
                                await page.wait_for_timeout(2000)
                                
                            except Exception as click_error:
                                print(f"  ⚠️ Error haciendo clic en comentarios: {click_error}")
                        
                        # Buscar comentarios después de expandir
                        comentarios_selectors = [
                            'div[aria-label="Comentario"]',
                            'div[data-ad-preview="message"]', 
                            'div[role="article"] div:has(a[href^="/"])',
                            'div:has(a[href^="/"]):has(img[src*="scontent"])',  # Comentarios con foto de perfil
                            'div[class*="comment"]'  # Selector más general
                        ]
                        
                        comentarios = []
                        for selector in comentarios_selectors:
                            comentarios = await post.query_selector_all(selector)
                            if comentarios:
                                print(f"  ✓ Encontrados {len(comentarios)} comentarios con: {selector}")
                                break
                        
                        if not comentarios:
                            print(f"  ℹ️ No se encontraron comentarios en el post {post_index + 1}")
                        
                        # Procesar comentarios encontrados
                        for comentario in comentarios:
                            try:
                                enlace_usuario = await comentario.query_selector('a[href^="/"]')
                                if not enlace_usuario:
                                    continue
                                    
                                href = await enlace_usuario.get_attribute("href")
                                if not href or '/photo' in href or '/video' in href:
                                    continue
                                    
                                username_usuario = href.strip('/').split('/')[-1]
                                url_usuario = f"https://www.facebook.com{href}" if href.startswith('/') else href
                                url_limpia = limpiar_url(url_usuario)

                                if url_limpia in comentadores_dict:
                                    continue

                                # Buscar imagen de perfil
                                img = await comentario.query_selector('img[src*="scontent"]')
                                foto = await img.get_attribute("src") if img else ""

                                # Buscar nombre
                                span = await comentario.query_selector('span')
                                nombre = await span.inner_text() if span else username_usuario

                                comentadores_dict[url_limpia] = {
                                    "nombre_usuario": nombre,
                                    "username_usuario": username_usuario,
                                    "link_usuario": url_limpia,
                                    "foto_usuario": foto,
                                    "post_url": page.url
                                }

                            except Exception as e:
                                logger.warning(f"Error procesando comentario: {e}")

                        posts_procesados += 1
                        print(f"  � Post {posts_procesados}/{FACEBOOK_CONFIG['max_posts']} procesado. Comentadores totales: {len(comentadores_dict)}")
                        
                        # Rate limiting cada 3 posts
                        if posts_procesados % FACEBOOK_CONFIG.get('rate_limit_posts_interval', 3) == 0:
                            print(f"  🔄 Pausa para evitar rate limiting...")
                            await page.wait_for_timeout(FACEBOOK_CONFIG['rate_limit_pause_ms'])

                    except Exception as e:
                        logger.warning(f"Error procesando post {post_index}: {e}")
                        continue
                
                # Si no se procesaron nuevos posts, incrementar contador
                if posts_procesados == current_posts_count:
                    no_new_posts_count += 1
                    print(f"  ⏳ No se procesaron nuevos posts (intento {no_new_posts_count}/{max_no_new_posts})")
                else:
                    no_new_posts_count = 0
                
                # Scroll para cargar más posts
                if posts_procesados < FACEBOOK_CONFIG['max_posts']:
                    print(f"  📜 Haciendo scroll para cargar más posts...")
                    await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                    await page.wait_for_timeout(3000)
                    scroll_attempts += 1
                    
                    # Verificar si llegamos al final
                    is_at_bottom = await page.evaluate("""
                        () => {
                            return (window.innerHeight + window.pageYOffset) >= document.body.scrollHeight - 1000;
                        }
                    """)
                    
                    if is_at_bottom:
                        print("  ✅ Llegamos al final de los posts")
                        break
                
            except Exception as e:
                logger.warning(f"Error en scroll {scroll_attempts}: {e}")
                no_new_posts_count += 1
                await page.wait_for_timeout(1000)

        print(f"✅ Comentadores extraídos: {len(comentadores_dict)}")
        if not comentadores_dict:
            print("ℹ️ Consejos para mejorar la extracción:")
            print("  - Verifica que tengas permisos para ver los comentarios")
            print("  - Asegúrate de estar autenticado correctamente")
            print("  - Algunos posts pueden no tener comentarios visibles")
            print("  - La estructura de Facebook puede haber cambiado")
        
        return list(comentadores_dict.values())

    except Exception as e:
        print(f"❌ Error extrayendo comentadores: {e}")
        return []

# Funciones alias para mantener compatibilidad con código existente
async def scrap_lista_usuarios(page, perfil_url):
    """Función alias para mantener compatibilidad - usa scrap_amigos"""
    return await scrap_amigos(page, perfil_url)