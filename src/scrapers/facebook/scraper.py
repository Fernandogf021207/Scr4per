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
        # Candidatos generales en la zona inferior del post
        candidates = await post.query_selector_all('div[role="button"], span[role="button"], a[role="link"], div, span')

        async def is_in_action_area(el):
            try:
                return await el.evaluate("""
                    (btn) => {
                        const post = btn.closest('div[role="article"]') || btn.parentElement;
                        if (!post) return true;
                        const pr = post.getBoundingClientRect();
                        const br = btn.getBoundingClientRect();
                        return br.top > (pr.top + pr.height * 0.6);
                    }
                """)
            except:
                return False

        # 1) Buscar por texto/icono claro
        for el in candidates:
            try:
                if not await is_in_action_area(el):
                    continue
                text = (await el.inner_text() or '').lower()
                has_text = any(t in text for t in ['comment', 'comentario', 'comentários', 'commenti'])
                has_icon = await el.evaluate("el => !!(el.querySelector('i[data-visualcompletion=\"css-img\"], svg[aria-label*=\"omment\" i]) )")
                if has_text or has_icon:
                    return el
            except:
                continue

        # 2) Fallback: pequeño número con icono cercano
        for el in candidates:
            try:
                if not await is_in_action_area(el):
                    continue
                text = (await el.inner_text() or '').strip()
                if not text or not any(ch.isdigit() for ch in text):
                    continue
                icon_near = await el.evaluate("el => !!(el.closest('div')?.querySelector('i[data-visualcompletion=\"css-img\"], svg'))")
                if icon_near:
                    return el
            except:
                continue

        return None
    except Exception as e:
        logger.warning(f"Error buscando botón de comentarios: {e}")
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
            'div[role="dialog"] div[aria-label="Ver más comentarios"]',
            'div[aria-modal="true"] div[aria-label="Dejar un comentario"]',
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

async def find_likes_button(post):
    """Encuentra el botón/recuento de likes o reacciones en un post de forma generalista"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    try:
        async def is_in_actions(el):
            try:
                return await el.evaluate("""
                    (el) => {
                        const post = el.closest('div[role="article"]') || el.parentElement;
                        if (!post) return true;
                        const pr = post.getBoundingClientRect();
                        const er = el.getBoundingClientRect();
                        return er.top > (pr.top + pr.height * 0.6);
                    }
                """)
            except:
                return False

        # 1) Intento con selectores configurados
        for selector in FACEBOOK_CONFIG.get('likes_button_selectors', []):
            try:
                btn = await post.query_selector(selector)
                if btn and await is_in_actions(btn):
                    clickable = await btn.query_selector('div[role="button"], a[role="link"]') or btn
                    print(f"  ✓ Botón/recuento de likes detectado por selector: {selector}")
                    return clickable
            except:
                continue

        # 2) Buscar candidatos generales con texto o número e ícono
        candidates = await post.query_selector_all('div[role="button"], a[role="link"], span')
        for el in candidates:
            try:
                if not await is_in_actions(el):
                    continue
                text = (await el.inner_text() or '').lower()
                has_like_text = any(t in text for t in ['Consulta quién reaccionó a esto', 'likes', 'reacciones', 'reactions'])
                has_number = any(ch.isdigit() for ch in text)
                has_icon = await el.evaluate("el => !!(el.querySelector('i[data-visualcompletion=\"css-img\"], svg'))")
                if has_like_text or (has_number and has_icon):
                    return el
            except:
                continue

        return None
    except Exception as e:
        logger.warning(f"Error buscando botón de likes: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error buscando botón de likes: {e}")
        return None

async def extract_likes_from_modal(page, likers_dict):
    """Extrae usuarios del modal de likes (solo nombre y link si está disponible)"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    try:
        encontrados = 0

        # Hacer múltiples scrolls para cargar toda la lista
        max_scrolls = 20
        no_new_count = 0
        prev_count = len(likers_dict)

        for _ in range(max_scrolls):
            # Identificar items dentro del modal
            items = []
            for selector in FACEBOOK_CONFIG.get('modal_likes_item_selectors', []):
                try:
                    items = await page.query_selector_all(selector)
                    if items:
                        break
                except:
                    continue

            # Procesar items
            for it in items:
                try:
                    # Buscar enlace de perfil si lo hay
                    enlace = await it.query_selector('a[href^="/"]') or await it.query_selector('a[role="link"]')
                    href = await enlace.get_attribute('href') if enlace else None
                    nombre = None

                    # Buscar nombre visible
                    for sel in ['span[dir="auto"]', 'strong', 'span']:  # generalistas
                        try:
                            el = await it.query_selector(sel)
                            if el:
                                t = await el.inner_text()
                                if t and 1 < len(t.strip()) < 120:
                                    nombre = t.strip()
                                    break
                        except:
                            continue

                    if not nombre:
                        continue

                    if href:
                        from src.utils.common import limpiar_url
                        url = f"https://www.facebook.com{href}" if href.startswith('/') else href
                        url = limpiar_url(url)
                    else:
                        url = f"about:blank#{hash(nombre)}"  # marcador sin URL

                    if url in likers_dict:
                        continue

                    username = url.rstrip('/').split('/')[-1] if href else nombre.replace(' ', '_').lower()
                    likers_dict[url] = {
                        "nombre_usuario": nombre,
                        "username_usuario": username,
                        "link_usuario": url if href else "",
                        "foto_usuario": "",
                        "post_url": page.url
                    }
                    encontrados += 1
                except Exception as e:
                    logger.debug(f"Elemento de like no procesable: {e}")
                    continue

            # Scroll dentro del modal
            reached_bottom = await page.evaluate("""
                () => {
                    const modal = document.querySelector('div[role="dialog"], div[aria-modal="true"]');
                    if (!modal) return true;
                    const scrollable = modal.querySelector('div[style*="overflow"], div[style*="height"], div[style*="max-height"]') || modal;
                    const before = scrollable.scrollTop;
                    scrollable.scrollTop += 600;
                    return (scrollable.scrollTop === before);
                }
            """)
            await page.wait_for_timeout(1200)

            if len(likers_dict) == prev_count:
                no_new_count += 1
            else:
                no_new_count = 0
                prev_count = len(likers_dict)

            if reached_bottom or no_new_count >= 3:
                break

        return encontrados
    except Exception as e:
        logger.warning(f"Error extrayendo likes del modal: {e}")
        return 0

async def scrap_likes_facebook(page, perfil_url):
    """Extraer usuarios que han dado like/reacciones en los posts del perfil"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    print("\n🔄 Navegando al perfil para extraer likes...")
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(5000)

        likers_dict = {}
        posts_procesados = 0
        scroll_attempts = 0
        max_scroll_attempts = 20
        no_new_posts_count = 0
        max_no_new_posts = 3

        posts_selectors = [
            'div[role="article"]',
            'div[data-pagelet="FeedUnit"]',
            'div[data-ft*="top_level_post_id"]'
        ]

        while (posts_procesados < FACEBOOK_CONFIG['max_posts'] and
               scroll_attempts < max_scroll_attempts and
               no_new_posts_count < max_no_new_posts):

            try:
                posts = []
                for selector in posts_selectors:
                    posts = await page.query_selector_all(selector)
                    if posts:
                        break

                if not posts:
                    no_new_posts_count += 1
                    await page.evaluate("window.scrollBy(0, window.innerHeight * 0.5)")
                    await page.wait_for_timeout(2500)
                    scroll_attempts += 1
                    continue

                current_posts_count = posts_procesados

                for post_index in range(posts_procesados, min(len(posts), FACEBOOK_CONFIG['max_posts'])):
                    try:
                        current_posts = await page.query_selector_all(posts_selectors[0])
                        if post_index >= len(current_posts):
                            continue
                        post = current_posts[post_index]

                        is_connected = await post.evaluate("e => e.isConnected")
                        if not is_connected:
                            continue

                        try:
                            await post.scroll_into_view_if_needed()
                            await page.wait_for_timeout(1200)
                        except:
                            await page.evaluate("window.scrollBy(0, 300)")
                            await page.wait_for_timeout(600)

                        likes_button = await find_likes_button(post)
                        if likes_button:
                            try:
                                print("  🖱️ Abriendo modal de likes/reacciones...")
                                try:
                                    await likes_button.scroll_into_view_if_needed()
                                except:
                                    pass
                                click_ok = False
                                try:
                                    await likes_button.click()
                                    click_ok = True
                                except:
                                    # Fallback: click en ancestro clickable via JS
                                    click_ok = await page.evaluate("""
                                        (el) => {
                                            const target = el.closest('div[role="button"], a[role="link"]') || el;
                                            if (target) {
                                                target.click();
                                                return true;
                                            }
                                            return false;
                                        }
                                    """, likes_button)
                                if not click_ok:
                                    # Fallback final: dispatchEvent
                                    await page.evaluate("(el)=>el.dispatchEvent(new MouseEvent('click', {bubbles:true}))", likes_button)
                                await page.wait_for_timeout(2000)

                                modal_found = await wait_for_modal(page)
                                if modal_found:
                                    extraidos = await extract_likes_from_modal(page, likers_dict)
                                    print(f"  📊 Likes extraídos del modal: {extraidos}")
                                    await close_modal(page)
                                else:
                                    print("  ⚠️ No se encontró modal de likes")
                            except Exception as e:
                                logger.debug(f"Click/lectura de likes falló: {e}")
                        else:
                            print(f"  ℹ️ No se encontró recuento/botón de likes en post {post_index+1}")

                        posts_procesados += 1

                        if posts_procesados % FACEBOOK_CONFIG.get('rate_limit_posts_interval', 3) == 0:
                            print("  🔄 Pausa para evitar rate limiting...")
                            await page.wait_for_timeout(FACEBOOK_CONFIG['rate_limit_pause_ms'])

                    except Exception as e:
                        logger.warning(f"Error procesando post (likes) {post_index}: {e}")
                        continue

                if posts_procesados == current_posts_count:
                    no_new_posts_count += 1
                else:
                    no_new_posts_count = 0

                if posts_procesados < FACEBOOK_CONFIG['max_posts']:
                    await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                    await page.wait_for_timeout(2500)
                    scroll_attempts += 1

                    is_at_bottom = await page.evaluate("""
                        () => (window.innerHeight + window.pageYOffset) >= document.body.scrollHeight - 1000
                    """)
                    if is_at_bottom:
                        break

            except Exception as e:
                logger.warning(f"Error en scroll (likes) {scroll_attempts}: {e}")
                no_new_posts_count += 1
                await page.wait_for_timeout(800)

        print(f"✅ Likers extraídos: {len(likers_dict)}")
        return list(likers_dict.values())
    except Exception as e:
        print(f"❌ Error extrayendo likes: {e}")
        return []
        
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