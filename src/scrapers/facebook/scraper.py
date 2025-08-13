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

async def find_comment_button(post):
    """Encuentra el botón de comentarios de manera generalista usando múltiples estrategias"""
    try:
        # Estrategia 1: Buscar usando JavaScript para evaluar contenido (más confiable)
        comment_button = await post.evaluate("""
            (post) => {
                // Buscar todos los botones en el post
                const buttons = post.querySelectorAll('div[role="button"], span[role="button"]');
                
                for (const button of buttons) {
                    const text = button.textContent.toLowerCase();
                    
                    // Buscar icono de comentarios específico
                    const hasCommentIcon = button.querySelector('i[style*="7H32i_pdCAf.png"]') ||
                                         button.querySelector('i[data-visualcompletion="css-img"]') ||
                                         button.querySelector('svg[aria-label*="comment" i]');
                    
                    // Buscar texto relacionado con comentarios
                    const hasCommentText = text.includes('comment') || 
                                          text.includes('comentario') ||
                                          text.includes('commenti') ||
                                          text.includes('comentários');
                    
                    // Buscar números que podrían indicar contador de comentarios
                    const hasNumberPattern = /^\\s*\\d+\\s*(comment|comentario|commenti)?/i.test(text);
                    
                    // Verificar si está en la zona de acciones del post (parte inferior)
                    const rect = button.getBoundingClientRect();
                    const postRect = post.getBoundingClientRect();
                    const isInActionArea = rect.top > (postRect.top + postRect.height * 0.7);
                    
                    // Buscar estructura típica de botón de comentarios
                    const hasTypicalStructure = button.querySelector('span') && 
                                               (button.querySelector('i') || button.querySelector('svg'));
                    
                    // Si cumple alguna de las condiciones y está en área de acciones
                    if ((hasCommentIcon || hasCommentText || hasNumberPattern || hasTypicalStructure) && isInActionArea) {
                        return button;
                    }
                }
                
                // Fallback: buscar botones que solo contengan números pequeños en área de acciones
                for (const button of buttons) {
                    const text = button.textContent.trim();
                    const rect = button.getBoundingClientRect();
                    const postRect = post.getBoundingClientRect();
                    const isInActionArea = rect.top > (postRect.top + postRect.height * 0.7);
                    
                    if (/^\\d{1,3}$/.test(text) && isInActionArea) {
                        return button;
                    }
                }
                
                return null;
            }
        """)
        
        if comment_button:
            print(f"  ✓ Botón de comentarios encontrado por análisis JavaScript")
            return comment_button
        
        # Estrategia 2: Buscar por iconos de comentarios usando selectores CSS
        icon_selectors = [
            'div[role="button"] i[style*="7H32i_pdCAf.png"]',
            'div[role="button"] i[data-visualcompletion="css-img"]',
            'div[role="button"]:has(i[style*="background-image"])',
            'span[role="button"] i[style*="7H32i_pdCAf.png"]',
        ]
        
        for selector in icon_selectors:
            try:
                button = await post.query_selector(selector)
                if button:
                    # Verificar que el botón esté en la parte inferior del post
                    is_in_action_area = await button.evaluate("""
                        (btn) => {
                            const btnRect = btn.getBoundingClientRect();
                            const post = btn.closest('div[role="article"]');
                            if (!post) return true; // Si no encuentra el post, asumir que está bien
                            const postRect = post.getBoundingClientRect();
                            return btnRect.top > (postRect.top + postRect.height * 0.7);
                        }
                    """)
                    
                    if is_in_action_area:
                        print(f"  ✓ Botón de comentarios encontrado por icono: {selector}")
                        return button
            except:
                continue
        
        # Estrategia 3: Buscar botones en la zona de acciones que contengan números
        action_area_buttons = await post.query_selector_all('div[role="button"], span[role="button"]')
        
        for button in action_area_buttons:
            try:
                # Verificar posición
                is_in_action_area = await button.evaluate("""
                    (btn) => {
                        const btnRect = btn.getBoundingClientRect();
                        const post = btn.closest('div[role="article"]');
                        if (!post) return false;
                        const postRect = post.getBoundingClientRect();
                        return btnRect.top > (postRect.top + postRect.height * 0.7);
                    }
                """)
                
                if not is_in_action_area:
                    continue
                
                # Verificar contenido
                text_content = await button.inner_text()
                text = text_content.strip().lower()
                
                # Si contiene solo números o números + texto de comentarios
                if (text.isdigit() and len(text) <= 3) or \
                   any(word in text for word in ['comment', 'comentario', 'commenti']):
                    print(f"  ✓ Botón de comentarios encontrado por contenido: '{text_content}'")
                    return button
                    
            except:
                continue
        
        print(f"  ⚠️ No se encontró botón de comentarios en el post")
        return None
        
    except Exception as e:
        logger.warning(f"Error buscando botón de comentarios: {e}")
        return None

async def wait_for_modal(page):
    """Espera a que aparezca el modal de comentarios"""
    try:
        # Selectores típicos para modales de Facebook
        modal_selectors = [
            'div[role="dialog"]',
            'div[aria-modal="true"]', 
            'div[data-pagelet*="comment"]',
            'div[class*="modal"]',
            'div[style*="position: fixed"]',
        ]
        
        for selector in modal_selectors:
            try:
                # Esperar hasta 5 segundos por el modal
                await page.wait_for_selector(selector, timeout=5000)
                modal = await page.query_selector(selector)
                if modal:
                    print(f"  ✓ Modal encontrado con selector: {selector}")
                    return True
            except:
                continue
        
        # Si no se encuentra modal específico, verificar si la página cambió significativamente
        # (puede ser que el modal no tenga atributos específicos)
        await page.wait_for_timeout(2000)
        
        # Verificar si hay overlay o elementos que indiquen modal
        overlay_exists = await page.evaluate("""
            () => {
                // Buscar elementos con z-index alto que podrían ser modales
                const elements = document.querySelectorAll('div');
                for (const el of elements) {
                    const style = window.getComputedStyle(el);
                    if (style.position === 'fixed' && 
                        (parseInt(style.zIndex) > 100 || style.zIndex === 'auto')) {
                        return true;
                    }
                }
                return false;
            }
        """)
        
        if overlay_exists:
            print(f"  ✓ Modal detectado por overlay")
            return True
        
        print(f"  ⚠️ No se detectó modal de comentarios")
        return False
        
    except Exception as e:
        logger.warning(f"Error esperando modal: {e}")
        return False

async def extract_comments_from_modal(page, comentadores_dict):
    """Extrae comentarios del modal abierto"""
    try:
        comentarios_extraidos = 0
        
        # Selectores para comentarios en modal
        modal_comment_selectors = [
            'div[role="dialog"] div[aria-label="Comentario"]',
            'div[aria-modal="true"] div[aria-label="Comentario"]',
            'div[role="dialog"] div:has(a[href^="/"])',
            'div[aria-modal="true"] div:has(a[href^="/"])',
            # Selectores más generales para el modal
            'div:has(a[href^="/"]):has(img[src*="scontent"])',
            'div[role="article"] div:has(a[href^="/"])',
        ]
        
        comentarios = []
        for selector in modal_comment_selectors:
            try:
                comentarios = await page.query_selector_all(selector)
                if comentarios:
                    print(f"  ✓ Encontrados {len(comentarios)} comentarios en modal con: {selector}")
                    break
            except:
                continue
        
        if not comentarios:
            # Intentar scroll en el modal para cargar más comentarios
            print(f"  📜 Haciendo scroll en modal para cargar comentarios...")
            await page.evaluate("""
                () => {
                    // Buscar el contenedor scrolleable del modal
                    const modal = document.querySelector('div[role="dialog"], div[aria-modal="true"]');
                    if (modal) {
                        const scrollable = modal.querySelector('div[style*="overflow"]') || modal;
                        scrollable.scrollBy(0, 300);
                    }
                }
            """)
            await page.wait_for_timeout(2000)
            
            # Reintentar buscar comentarios
            for selector in modal_comment_selectors:
                try:
                    comentarios = await page.query_selector_all(selector)
                    if comentarios:
                        print(f"  ✓ Comentarios encontrados después del scroll: {len(comentarios)}")
                        break
                except:
                    continue
        
        # Procesar comentarios encontrados
        for comentario in comentarios:
            try:
                enlace_usuario = await comentario.query_selector('a[href^="/"]')
                if not enlace_usuario:
                    continue
                    
                href = await enlace_usuario.get_attribute("href")
                if not href or '/photo' in href or '/video' in href or '/watch' in href:
                    continue
                    
                username_usuario = href.strip('/').split('/')[-1]
                if not username_usuario or len(username_usuario) < 2:
                    continue
                    
                url_usuario = f"https://www.facebook.com{href}" if href.startswith('/') else href
                url_limpia = limpiar_url(url_usuario)

                if url_limpia in comentadores_dict:
                    continue

                # Buscar imagen de perfil
                img_selectors = [
                    'img[src*="scontent"]',
                    'img[alt*="foto de perfil"]',
                    'img[data-imgperflogname]'
                ]
                
                foto = ""
                for img_selector in img_selectors:
                    try:
                        img = await comentario.query_selector(img_selector)
                        if img:
                            foto = await img.get_attribute("src")
                            break
                    except:
                        continue

                # Buscar nombre del usuario
                nombre_selectors = [
                    'span[dir="auto"]',
                    'strong',
                    'a[href^="/"] span',
                ]
                
                nombre = username_usuario
                for nombre_selector in nombre_selectors:
                    try:
                        span = await comentario.query_selector(nombre_selector)
                        if span:
                            texto = await span.inner_text()
                            if texto and len(texto.strip()) > 0 and len(texto.strip()) < 100:
                                nombre = texto.strip()
                                break
                    except:
                        continue

                comentadores_dict[url_limpia] = {
                    "nombre_usuario": nombre,
                    "username_usuario": username_usuario,
                    "link_usuario": url_limpia,
                    "foto_usuario": foto or "",
                    "post_url": page.url
                }
                
                comentarios_extraidos += 1

            except Exception as e:
                logger.warning(f"Error procesando comentario en modal: {e}")
                continue
        
        return comentarios_extraidos
        
    except Exception as e:
        logger.warning(f"Error extrayendo comentarios del modal: {e}")
        return 0

async def close_modal(page):
    """Cierra el modal de comentarios"""
    try:
        # Intentar cerrar con botón de cerrar
        close_selectors = [
            'div[role="dialog"] div[aria-label="Cerrar"]',
            'div[role="dialog"] div[aria-label="Close"]',
            'div[aria-modal="true"] button[aria-label="Cerrar"]',
            'div[aria-modal="true"] button[aria-label="Close"]',
            'div[role="dialog"] svg[aria-label="Cerrar"]',
            'div[role="dialog"] svg[aria-label="Close"]',
        ]
        
        for selector in close_selectors:
            try:
                close_button = await page.query_selector(selector)
                if close_button:
                    await close_button.click()
                    await page.wait_for_timeout(1000)
                    print(f"  ✓ Modal cerrado con botón")
                    return True
            except:
                continue
        
        # Si no hay botón, intentar con ESC
        try:
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(1000)
            print(f"  ✓ Modal cerrado con ESC")
            return True
        except:
            pass
        
        # Como último recurso, hacer clic fuera del modal
        try:
            await page.evaluate("""
                () => {
                    // Buscar el overlay/backdrop y hacer clic
                    const modal = document.querySelector('div[role="dialog"], div[aria-modal="true"]');
                    if (modal && modal.parentElement) {
                        modal.parentElement.click();
                    }
                }
            """)
            await page.wait_for_timeout(1000)
            print(f"  ✓ Modal cerrado haciendo clic fuera")
            return True
        except:
            pass
        
        print(f"  ⚠️ No se pudo cerrar el modal automáticamente")
        return False
        
    except Exception as e:
        logger.warning(f"Error cerrando modal: {e}")
        return False

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
                        
                        # Buscar el botón de comentarios con estrategia generalista
                        comment_button = await find_comment_button(post)
                        
                        if comment_button:
                            try:
                                # Hacer clic en el botón de comentarios para abrir el modal
                                print(f"  🖱️ Haciendo clic en botón de comentarios...")
                                await comment_button.click()
                                await page.wait_for_timeout(3000)
                                
                                # Esperar a que aparezca el modal
                                modal_found = await wait_for_modal(page)
                                
                                if modal_found:
                                    print(f"  ✓ Modal de comentarios abierto")
                                    # Extraer comentarios del modal
                                    comentarios_extraidos = await extract_comments_from_modal(page, comentadores_dict)
                                    print(f"  📊 Comentarios extraídos del modal: {comentarios_extraidos}")
                                    
                                    # Cerrar el modal
                                    await close_modal(page)
                                else:
                                    print(f"  ⚠️ No se pudo abrir el modal de comentarios")
                                
                            except Exception as click_error:
                                print(f"  ⚠️ Error procesando comentarios: {click_error}")
                        else:
                            print(f"  ℹ️ No se encontró botón de comentarios en el post {post_index + 1}")

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