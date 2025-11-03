import asyncio
import logging
from urllib.parse import urljoin
from src.utils.common import limpiar_url
from src.utils.url import normalize_input_url
from src.utils.dom import find_scroll_container, scroll_element, scroll_window
from src.utils.list_parser import build_user_item
from src.utils.url import normalize_post_url
import os
import httpx

logger = logging.getLogger(__name__)

async def obtener_foto_perfil_instagram(page):
    """Intentar obtener la foto de perfil del usuario principal de Instagram"""
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
        logger.warning(f"No se pudo obtener foto de perfil: {e}")
        return None

async def obtener_nombre_usuario_instagram(page):
    """Obtener el nombre de usuario y nombre completo de Instagram"""
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
                text = await element.inner_text()
                text = text.strip()
                if text and text != username_from_url:
                    nombre_completo = text
                    break
        
        return {
            'username': username_from_url,
            'nombre_completo': nombre_completo or username_from_url
        }
    except Exception as e:
        logger.warning(f"Error obteniendo nombre de usuario: {e}")
        return {'username': 'unknown', 'nombre_completo': 'unknown'}

async def obtener_datos_usuario_principal(page, perfil_url):
    """Obtener datos del perfil principal"""
    logger.info("Obteniendo datos del perfil principal de Instagram...")
    perfil_url = normalize_input_url('instagram', perfil_url)
    await page.goto(perfil_url)
    await page.wait_for_timeout(5000)
    
    datos_usuario_ig = await obtener_nombre_usuario_instagram(page)
    username = datos_usuario_ig['username']
    nombre_completo = datos_usuario_ig['nombre_completo']
    foto_perfil = await obtener_foto_perfil_instagram(page)
    
    logger.info("Usuario detectado: @%s (%s)", username, nombre_completo)
    
    return {
        'username': username,
        'nombre_completo': nombre_completo,
        'foto_perfil': foto_perfil or "",
        'url_usuario': perfil_url
    }

async def extraer_usuarios_instagram(page, tipo_lista="seguidores", usuario_principal=""):
    """Extraer usuarios de una lista de Instagram (seguidores o seguidos)"""
    logger.info("Cargando %s...", tipo_lista)
    usuarios_dict = {}
    
    # Scroll robusto en el modal para cargar más usuarios
    logger.info("Haciendo scroll en modal de %s...", tipo_lista)

    container = await find_scroll_container(page)

    scroll_attempts = 0
    max_scrolls = 60
    no_new_users_count = 0
    max_no_new_users = 6

    recent_additions = 0
    while scroll_attempts < max_scrolls and no_new_users_count < max_no_new_users:
        try:
            current_user_count = len(usuarios_dict)

            if container:
                await scroll_element(container, 1000)
            else:
                await scroll_window(page, 800)

            # Espera adaptativa: poll hasta 1200ms a ver si aumentan los nodos visibles
            try:
                js_count = '''
                (sels) => {
                  for (const sel of sels) {
                    const nodes = document.querySelectorAll(sel);
                    if (nodes && nodes.length) return nodes.length;
                  }
                  return 0;
                }
                '''
                selectors = [
                    'div[role="dialog"] div[style*="flex-direction: column"] > div',
                    'div[role="dialog"] div > div:has(a[role="link"])',
                    'div[aria-modal="true"] div:has(a[role="link"])',
                    f'div[aria-label="{tipo_lista.capitalize()}"] div:has(a)',
                    'div[role="dialog"] a[role="link"]'
                ]
                base_count = await page.evaluate(js_count, selectors)
                waited = 0
                while waited < 1200:
                    await page.wait_for_timeout(200)
                    new_count = await page.evaluate(js_count, selectors)
                    if new_count > base_count:
                        break
                    waited += 200
            except Exception:
                # Fallback a pequeña espera fija
                await page.wait_for_timeout(400)

            # Procesar usuarios después del scroll
            await procesar_usuarios_en_modal(page, usuarios_dict, usuario_principal, tipo_lista)

            # Verificar si se agregaron nuevos usuarios
            if len(usuarios_dict) > current_user_count:
                no_new_users_count = 0
                recent_additions += 1
                logger.info("%s: %d usuarios encontrados (scroll %d)", tipo_lista, len(usuarios_dict), scroll_attempts + 1)
            else:
                no_new_users_count += 1
                logger.info("Sin nuevos usuarios en scroll %d (intentos: %d)", scroll_attempts + 1, no_new_users_count)

            scroll_attempts += 1

            # Pausa cada 12 scrolls para evitar rate limiting
            if scroll_attempts % 12 == 0:
                logger.info("Pausa breve para evitar rate limiting... (%d usuarios hasta ahora)", len(usuarios_dict))
                await page.wait_for_timeout(1500)

            # Extender dinámicamente el máximo si seguimos añadiendo a última hora
            if scroll_attempts >= max_scrolls - 2 and recent_additions >= 2 and max_scrolls < 120:
                max_scrolls = min(120, max_scrolls + 20)

            # Verificar si llegamos al final del contenedor
            is_at_bottom = False
            try:
                if container:
                    is_at_bottom = await container.evaluate(
                        "el => (el.scrollTop + el.clientHeight) >= (el.scrollHeight - 120)"
                    )
                else:
                    is_at_bottom = await page.evaluate(
                        "() => (window.innerHeight + window.pageYOffset) >= (document.body.scrollHeight - 200)"
                    )
            except Exception:
                is_at_bottom = False

            if is_at_bottom and no_new_users_count >= 3:
                logger.info("Llegamos al final de la lista de %s", tipo_lista)
                break

        except Exception as e:
            logger.warning(f"Error en scroll {scroll_attempts}: {e}")
            no_new_users_count += 1
            await page.wait_for_timeout(1000)

    logger.info("Scroll completado para %s. Total de scrolls: %d", tipo_lista, scroll_attempts)
    logger.info("Usuarios únicos extraídos: %d", len(usuarios_dict))
    
    return list(usuarios_dict.values())

async def procesar_usuarios_en_modal(page, usuarios_dict, usuario_principal, tipo_lista):
    """Procesar usuarios visibles en el modal actual"""
    try:
        # Selectores específicos para elementos de usuarios en el modal
        selectores_contenedor = [
            'div[role="dialog"] div[style*="flex-direction: column"] > div',
            'div[role="dialog"] div > div:has(a[role="link"])',
            'div[aria-modal="true"] div:has(a[role="link"])',
            f'div[aria-label="{tipo_lista.capitalize()}"] div:has(a)',
            'div[role="dialog"] a[role="link"]'
        ]
        
        data = None
        for selector in selectores_contenedor:
            try:
                # Extraer en una sola evaluación para reducir round-trips
                js = '''
                (sel) => {
                  const nodes = Array.from(document.querySelectorAll(sel));
                  const out = [];
                  for (const el of nodes) {
                    let a = el.querySelector("a[role='link']") || el.querySelector("a[href^='/']");
                    if (!a) continue;
                    const href = a.getAttribute("href") || "";
                    if (!href.startsWith("/")) continue;
                    const img = el.querySelector("img");
                    const src = img ? (img.currentSrc || img.src || "") : "";
                    const text = (el.textContent || "").trim();
                    const name = text.split("\\n")[0] || null;
                    out.push({ href, name, src });
                  }
                  return out;
                }
                '''
                data = await page.evaluate(js, selector)
                if data and len(data) > 0:
                    logger.info("Encontrados %d elementos con selector: %s", len(data), selector)
                    break
            except Exception:
                data = None
                continue

        if not data:
            logger.info("No se encontraron usuarios en este scroll")
            return

        for rec in data:
            try:
                href = rec.get('href') or ''
                if not href or not href.startswith('/'):
                    continue
                url_usuario_abs = f"https://www.instagram.com{href}"
                nombre_completo_usuario = rec.get('name')
                url_foto = rec.get('src') or ""
                item = build_user_item('instagram', url_usuario_abs, nombre_completo_usuario, url_foto)
                url_limpia = item['link_usuario']
                username_usuario = item['username_usuario']

                if username_usuario == usuario_principal:
                    continue
                if url_limpia in usuarios_dict:
                    continue
                usuarios_dict[url_limpia] = item
            except Exception as e:
                logger.warning(f"Error procesando usuario individual: {e}")
                continue
                
    except Exception as e:
        logger.warning(f"Error procesando usuarios en modal: {e}")

async def navegar_a_lista_instagram(page, perfil_url, tipo_lista="followers"):
    """Navegar a la lista de seguidores o seguidos en Instagram"""
    try:
        perfil_url = normalize_input_url('instagram', perfil_url)
        await page.goto(perfil_url)
        await page.wait_for_timeout(3000)

        if tipo_lista == "followers":
            selectores_enlace = [
                'a[href*="/followers/"]',
                'a:has-text("seguidores")',
                'a:has-text("followers")',
                'header a[href*="followers"]'
            ]
            nombre_lista = "seguidores"
        else:
            selectores_enlace = [
                'a[href*="/following/"]',
                'a:has-text("seguidos")',
                'a:has-text("following")',
                'header a[href*="following"]'
            ]
            nombre_lista = "seguidos"

        logger.info("Buscando enlace de %s...", nombre_lista)

        enlace_lista = None
        for selector in selectores_enlace:
            enlace_lista = await page.query_selector(selector)
            if enlace_lista:
                break

        if not enlace_lista:
            logger.warning("No se pudo encontrar el enlace de %s. ¿El perfil es público?", nombre_lista)
            return False

        logger.info("Haciendo clic en %s...", nombre_lista)
        await enlace_lista.click()
        await page.wait_for_timeout(3000)
        return True

    except Exception as e:
        logger.warning("Error navegando a %s: %s", nombre_lista, e)
        return False

async def scrap_seguidores(page, perfil_url, username):
    """Scrapear seguidores del usuario"""
    logger.info("Extrayendo seguidores...")
    try:
        if await navegar_a_lista_instagram(page, perfil_url, "followers"):
            seguidores = await extraer_usuarios_instagram(page, "seguidores", username)
            logger.info("Seguidores encontrados: %d", len(seguidores))
            return seguidores
        else:
            logger.warning("No se pudieron extraer seguidores")
            return []
    except Exception as e:
        logger.warning("Error extrayendo seguidores: %s", e)
        return []

async def scrap_seguidos(page, perfil_url, username):
    """Scrapear seguidos del usuario"""
    logger.info("Extrayendo seguidos...")
    try:
        if await navegar_a_lista_instagram(page, perfil_url, "following"):
            seguidos = await extraer_usuarios_instagram(page, "seguidos", username)
            logger.info("Seguidos encontrados: %d", len(seguidos))
            return seguidos
        else:
            logger.warning("No se pudieron extraer seguidos")
            return []
    except Exception as e:
        logger.warning("Error extrayendo seguidos: %s", e)
        return []

async def extraer_posts_del_perfil(page, max_posts=10):
    """Extraer URLs de posts del perfil principal con scroll manual mejorado"""
    logger.info("Buscando posts en el perfil...")
    
    try:
        urls_posts = set()
        scroll_attempts = 0
        max_scrolls = 10
        no_new_posts_count = 0
        max_no_new_posts = 3
        
        while len(urls_posts) < max_posts and scroll_attempts < max_scrolls and no_new_posts_count < max_no_new_posts:
            current_posts_count = len(urls_posts)
            
            # Scroll manual en la página del perfil
            await page.evaluate("""
                () => {
                    window.scrollBy(0, window.innerHeight * 0.8);
                }
            """)
            
            await page.wait_for_timeout(2000)
            
            # Buscar posts después del scroll
            selectores_posts = [
                'article a[href*="/p/"]',
                'article a[href*="/reel/"]',
                'a[href*="/p/"]',
                'a[href*="/reel/"]',
                'div a[href*="/p/"]',
                'div a[href*="/reel/"]'
            ]
            
            for selector in selectores_posts:
                try:
                    elementos_posts = await page.query_selector_all(selector)
                    for elemento in elementos_posts:
                        if len(urls_posts) >= max_posts:
                            break
                        try:
                            href = await elemento.get_attribute("href")
                            if href:
                                if href.startswith('/'):
                                    url_completa = f"https://www.instagram.com{href}"
                                else:
                                    url_completa = href
                                
                                # Verificar que es un post o reel válido
                                if '/p/' in url_completa or '/reel/' in url_completa:
                                    urls_posts.add(url_completa)
                        except:
                            continue
                except:
                    continue
            
            # Verificar progreso
            if len(urls_posts) > current_posts_count:
                no_new_posts_count = 0
                logger.info("Posts encontrados: %d (scroll %d)", len(urls_posts), scroll_attempts + 1)
            else:
                no_new_posts_count += 1
                logger.info("Sin nuevos posts en scroll %d", scroll_attempts + 1)
            
            scroll_attempts += 1
            
            # Verificar si llegamos al final de la página
            is_at_bottom = await page.evaluate("""
                () => {
                    return (window.innerHeight + window.pageYOffset) >= document.body.scrollHeight - 1000;
                }
            """)
            
            if is_at_bottom:
                logger.info("Llegamos al final del perfil")
                break
        
        urls_posts = list(urls_posts)[:max_posts]
        logger.info("Posts finales encontrados: %d", len(urls_posts))
        return urls_posts
        
    except Exception as e:
        logger.error(f"Error extrayendo posts: {e}")
        return []

async def _abrir_liked_by_y_extraer_usuarios(page, post_url: str):
    """Abre el listado de liked_by de un post y retorna usuarios que dieron like."""
    try:
        await page.goto(post_url)
        await page.wait_for_timeout(2000)
        # Buscar enlace liked_by
        a = await page.query_selector('a[href*="/liked_by/"]')
        if not a:
            # Algunos layouts muestran un botón o span clicable cerca del contador de likes
            for sel in [
                'a:has-text("likes")',
                'a:has-text("Me gusta")',
                'div[role="button"]:has-text("likes")',
                'div[role="button"]:has-text("Me gusta")'
            ]:
                a = await page.query_selector(sel)
                if a:
                    break
        if not a:
            return []
        await a.click()
        await page.wait_for_timeout(1500)

        # Reutilizar scroll de modal como en listas
        usuarios_dict = {}

        # identificar contenedor scrolleable
        container = await find_scroll_container(page)

        scrolls = 0
        no_new = 0
        while scrolls < 50 and no_new < 6:
            before = len(usuarios_dict)
            # Procesar usuarios visibles en el modal reutilizando el procesador de listas
            try:
                await procesar_usuarios_en_modal(page, usuarios_dict, usuario_principal="", tipo_lista="liked_by")
            except Exception:
                pass

            if len(usuarios_dict) == before:
                no_new += 1
            else:
                no_new = 0

            # Scroll
            if container:
                await scroll_element(container, 800)
            else:
                await scroll_window(page, 600)
            await page.wait_for_timeout(900)
            scrolls += 1

        # Enriquecer con post_url y reaction_type
        res = []
        for v in usuarios_dict.values():
            v = dict(v)
            v["post_url"] = normalize_post_url('instagram', post_url)
            v["reaction_type"] = "like"
            res.append(v)
        return res
    except Exception:
        return []

async def scrap_reacciones_instagram(page, perfil_url: str, username: str, max_posts: int = 5):
    """Scrapea usuarios que dieron like (liked_by) en los últimos posts."""
    try:
        perfil_url = normalize_input_url('instagram', perfil_url)
        await page.goto(perfil_url)
        await page.wait_for_timeout(1500)
        posts = await extraer_posts_del_perfil(page, max_posts=max_posts)
        resultados = []
        for i, post in enumerate(posts, 1):
            likes = await _abrir_liked_by_y_extraer_usuarios(page, post)
            resultados.extend(likes)
            if i % 3 == 0:
                await page.wait_for_timeout(1200)
        return resultados
    except Exception:
        return []

async def extraer_comentarios_post(page, url_post, post_id):
    """Extraer comentarios de un post específico con scroll manual mejorado"""
    logger.info("Extrayendo comentarios del post %s...", post_id)
    
    try:
        await page.goto(url_post)
        await page.wait_for_timeout(3000)
        
        comentarios_dict = {}
        
        # Primero intentar cargar más comentarios con botones
        logger.info("Intentando cargar más comentarios...")
        for _ in range(3):
            try:
                botones_cargar = [
                    'button:has-text("Cargar más comentarios")',
                    'button:has-text("Load more comments")',
                    'button[aria-label="Load more comments"]',
                    'span:has-text("Cargar más comentarios")',
                    'button:has-text("Ver más comentarios")',
                    'button:has-text("View more comments")'
                ]
                
                button_clicked = False
                for selector_boton in botones_cargar:
                    boton = await page.query_selector(selector_boton)
                    if boton:
                        await boton.click()
                        button_clicked = True
                        await page.wait_for_timeout(2000)
                        logger.info("Botón 'cargar más' clickeado")
                        break
                if not button_clicked:
                    break
            except Exception as e:
                logger.warning(f"No se pudo cargar más comentarios con botón: {e}")
                break
        
        # Scroll manual para cargar más comentarios
        logger.info("Haciendo scroll para cargar comentarios...")
        scroll_attempts = 0
        max_scrolls = 15
        no_new_comments_count = 0
        max_no_new_comments = 3
        
        while scroll_attempts < max_scrolls and no_new_comments_count < max_no_new_comments:
            current_comments_count = len(comentarios_dict)
            
            # Scroll manual específico en el área de comentarios
            await page.evaluate("""
                () => {
                    // Buscar el contenedor de comentarios
                    const commentSection = document.querySelector('article section') ||
                                         document.querySelector('div[role="button"] section') ||
                                         document.querySelector('section');
                    
                    if (commentSection) {
                        // Buscar el área scrolleable de comentarios
                        const scrollableArea = commentSection.querySelector('div[style*="overflow"]') ||
                                             commentSection.querySelector('div[style*="max-height"]') ||
                                             commentSection;
                        
                        // Hacer scroll hacia abajo
                        scrollableArea.scrollTop += 300;
                    } else {
                        // Fallback: scroll en la página
                        window.scrollBy(0, 300);
                    }
                }
            """)
            
            await page.wait_for_timeout(1500)
            
            # Procesar comentarios después del scroll
            await procesar_comentarios_en_post(page, comentarios_dict, url_post)
            
            # Verificar progreso
            if len(comentarios_dict) > current_comments_count:
                no_new_comments_count = 0
                logger.info("Comentarios encontrados: %d (scroll %d)", len(comentarios_dict), scroll_attempts + 1)
            else:
                no_new_comments_count += 1
                logger.info("Sin nuevos comentarios en scroll %d", scroll_attempts + 1)
            
            scroll_attempts += 1
            
            # Pausa cada 5 scrolls
            if scroll_attempts % 5 == 0:
                await page.wait_for_timeout(2000)
        
        comentarios = list(comentarios_dict.values())
        logger.info("Comentarios únicos encontrados en post %s: %d", post_id, len(comentarios))
        return comentarios
        
    except Exception as e:
        logger.error(f"Error extrayendo comentarios del post: {e}")
        return []

async def extraer_comentarios_en_modal(page, url_post, post_id):
    """Extraer comentarios cuando se abren en un modal"""
    logger.info("Buscando comentarios en modal para post %s...", post_id)
    
    try:
        comentarios_dict = {}
        
        # Buscar y hacer click en el botón de comentarios
        botones_comentarios = [
            'svg[aria-label="Comentar"]',
            'svg[aria-label="Comment"]',
            'button[aria-label="Comentar"]',
            'button[aria-label="Comment"]',
            '[role="button"]:has(svg[aria-label*="omment"])',
            'div[role="button"]:has(svg[fill="#262626"])',
            'button:has(svg[height="24"][width="24"])',
            'svg[height="24"][viewBox="0 0 24 24"]:has(path[d*="20.656"])'
        ]
        
        modal_abierto = False
        for selector_boton in botones_comentarios:
            try:
                boton_comentarios = await page.query_selector(selector_boton)
                if boton_comentarios:
                    await boton_comentarios.click()
                    await page.wait_for_timeout(2000)
                    
                    # Verificar si se abrió un modal
                    modal = await page.query_selector('div[role="dialog"]')
                    if modal:
                        logger.info("Modal de comentarios abierto")
                        modal_abierto = True
                        break
            except Exception as e:
                logger.debug(f"No se pudo hacer click en botón de comentarios: {e}")
                continue
        
        if not modal_abierto:
            logger.warning("No se pudo abrir modal de comentarios")
            return []
        
        # Hacer scroll manual dentro del modal
        logger.info("Haciendo scroll en modal de comentarios...")
        scroll_attempts = 0
        max_scrolls = 20
        no_new_comments_count = 0
        max_no_new_comments = 3
        
        while scroll_attempts < max_scrolls and no_new_comments_count < max_no_new_comments:
            current_comments_count = len(comentarios_dict)
            
            # Scroll específico en el modal
            await page.evaluate("""
                () => {
                    // Buscar el modal de comentarios
                    const modal = document.querySelector('div[role="dialog"]');
                    if (modal) {
                        // Buscar el área scrolleable dentro del modal
                        const scrollableArea = modal.querySelector('div[style*="overflow"]') ||
                                             modal.querySelector('div[style*="max-height"]') ||
                                             modal.querySelector('div[style*="height"]') ||
                                             modal;
                        
                        // Hacer scroll hacia abajo en el modal
                        scrollableArea.scrollTop += 400;
                    }
                }
            """)
            
            await page.wait_for_timeout(1500)
            
            # Procesar comentarios en el modal
            await procesar_comentarios_en_modal(page, comentarios_dict, url_post)
            
            # Verificar progreso
            if len(comentarios_dict) > current_comments_count:
                no_new_comments_count = 0
                logger.info("Comentarios en modal: %d (scroll %d)", len(comentarios_dict), scroll_attempts + 1)
            else:
                no_new_comments_count += 1
                logger.info("Sin nuevos comentarios en modal (scroll %d)", scroll_attempts + 1)
            
            scroll_attempts += 1
            
            # Pausa cada 5 scrolls
            if scroll_attempts % 5 == 0:
                await page.wait_for_timeout(2000)
        
        # Cerrar modal
        try:
            boton_cerrar = await page.query_selector('div[role="dialog"] button[aria-label*="Cerrar"], div[role="dialog"] button[aria-label*="Close"], div[role="dialog"] svg[aria-label*="Cerrar"], div[role="dialog"] svg[aria-label*="Close"]')
            if boton_cerrar:
                await boton_cerrar.click()
                await page.wait_for_timeout(1000)
        except Exception as e:
            logger.debug(f"No se pudo cerrar modal: {e}")
        
        comentarios = list(comentarios_dict.values())
        logger.info("Comentarios únicos encontrados en modal: %d", len(comentarios))
        return comentarios
        
    except Exception as e:
        logger.error(f"Error extrayendo comentarios en modal: {e}")
        return []

async def procesar_comentarios_en_modal(page, comentarios_dict, url_post):
    """Procesar comentarios visibles en el modal actual"""
    try:
        # Selectores específicos para modal de comentarios
        selectores_modal = [
            'div[role="dialog"] span[dir="auto"] a[href^="/"]',
            'div[role="dialog"] div div span a[href^="/"][href$="/"]',
            'div[role="dialog"] section div span a',
            'div[role="dialog"] a[href^="/"][role="link"]',
            'div[role="dialog"] h3 a[href^="/"]',
            'div[role="dialog"] div[style*="flex"] a[href^="/"]'
        ]
        
        elementos_comentarios = []
        for selector in selectores_modal:
            try:
                elementos = await page.query_selector_all(selector)
                if elementos:
                    # Filtrar elementos válidos
                    elementos_validos = []
                    for elemento in elementos:
                        try:
                            href = await elemento.get_attribute("href")
                            if href and href.startswith('/') and href.endswith('/'):
                                username = href.strip('/').split('/')[0]
                                # Evitar links que no son de usuarios
                                if username not in ['p', 'reel', 'tv', 'stories', 'explore', 'accounts']:
                                    elementos_validos.append(elemento)
                        except:
                            continue
                    
                    if elementos_validos:
                        elementos_comentarios = elementos_validos
                        logger.info("Encontrados %d comentarios en modal con selector: %s", len(elementos_comentarios), selector)
                        break
            except:
                continue
        
        if not elementos_comentarios:
            return
        
        # Procesar cada comentario en el modal
        for elemento in elementos_comentarios:
            try:
                href = await elemento.get_attribute("href")
                if not href or not href.startswith('/'):
                    continue
                
                username = href.strip('/').split('/')[0]
                if username in ['p', 'reel', 'tv', 'stories', 'explore', 'accounts'] or username == "":
                    continue
                
                # Evitar duplicados
                if username in comentarios_dict:
                    continue
                
                nombre_mostrado = await elemento.inner_text()
                url_perfil = f"https://www.instagram.com/{username}/"
                
                # Buscar imagen de perfil en el modal
                url_foto = ""
                try:
                    contenedor_padre = await elemento.evaluate_handle("""
                        element => {
                            let current = element.parentElement;
                            let attempts = 0;
                            while (current && attempts < 6) {
                                const img = current.querySelector('img[src*="profile"]') || 
                                          current.querySelector('img:not([src*="data:"])');
                                if (img && img.src && !img.src.startsWith('data:')) {
                                    return current;
                                }
                                current = current.parentElement;
                                attempts++;
                            }
                            return element.parentElement;
                        }
                    """)
                    
                    if contenedor_padre:
                        img_element = await contenedor_padre.query_selector('img')
                        if img_element:
                            url_foto = await img_element.get_attribute("src") or ""
                except Exception as img_error:
                    logger.debug(f"No se pudo obtener imagen para {username} en modal: {img_error}")
                
                item = build_user_item('instagram', url_perfil, nombre_mostrado or username, url_foto)
                item['post_url'] = normalize_post_url('instagram', url_post)
                comentarios_dict[username] = item
                
            except Exception as e:
                logger.warning(f"Error procesando comentario en modal: {e}")
                continue
                
    except Exception as e:
        logger.warning(f"Error procesando comentarios en modal: {e}")

async def procesar_comentarios_en_post(page, comentarios_dict, url_post):
    """Procesar comentarios visibles en el post actual"""
    try:
        # Selectores mejorados para encontrar comentarios
        selectores_comentarios = [
            'article section div div div div span[dir="auto"] a',
            'section div span[dir="auto"] a[href^="/"]',
            'div[role="button"] span[dir="auto"] a',
            'span:has(a[href^="/"][href$="/"])',
            'article a[href^="/"][href$="/"]',
            'section a[href^="/"][href$="/"]',
            # Selectores más específicos
            'div[style*="padding"] a[href^="/"]',
            'span a[href^="/"][role="link"]'
        ]
        
        elementos_comentarios = []
        for selector in selectores_comentarios:
            try:
                elementos = await page.query_selector_all(selector)
                if elementos:
                    # Filtrar elementos que parecen ser comentarios reales
                    elementos_validos = []
                    for elemento in elementos:
                        try:
                            href = await elemento.get_attribute("href")
                            if href and href.startswith('/') and href.endswith('/'):
                                username = href.strip('/').split('/')[0]
                                # Evitar links de posts, reels, etc.
                                if username not in ['p', 'reel', 'tv', 'stories', 'explore']:
                                    elementos_validos.append(elemento)
                        except:
                            continue
                    
                    if elementos_validos:
                        elementos_comentarios = elementos_validos
                        logger.info("Encontrados %d comentarios con selector: %s", len(elementos_comentarios), selector)
                        break
            except:
                continue
        
        if not elementos_comentarios:
            return
        
        # Procesar cada comentario
        for elemento in elementos_comentarios:
            try:
                href = await elemento.get_attribute("href")
                if not href or not href.startswith('/'):
                    continue
                
                username = href.strip('/').split('/')[0]
                if username in ['p', 'reel', 'tv', 'stories', 'explore'] or username == "":
                    continue
                
                # Evitar duplicados
                if username in comentarios_dict:
                    continue
                
                nombre_mostrado = await elemento.inner_text()
                url_perfil = f"https://www.instagram.com/{username}/"
                
                # Buscar imagen de perfil del comentarista
                url_foto = ""
                try:
                    # Buscar en el contenedor padre
                    contenedor_padre = await elemento.evaluate_handle("""
                        element => {
                            // Buscar hacia arriba en el DOM hasta encontrar un contenedor con imagen
                            let current = element.parentElement;
                            let attempts = 0;
                            while (current && attempts < 5) {
                                const img = current.querySelector('img');
                                if (img && img.src && !img.src.startsWith('data:')) {
                                    return current;
                                }
                                current = current.parentElement;
                                attempts++;
                            }
                            return element.parentElement;
                        }
                    """)
                    
                    if contenedor_padre:
                        img_element = await contenedor_padre.query_selector('img')
                        if img_element:
                            url_foto = await img_element.get_attribute("src") or ""
                except Exception as img_error:
                    logger.debug(f"No se pudo obtener imagen para {username}: {img_error}")
                
                item = build_user_item('instagram', url_perfil, nombre_mostrado or username, url_foto)
                item['post_url'] = normalize_post_url('instagram', url_post)
                comentarios_dict[username] = item
                
            except Exception as e:
                logger.warning(f"Error procesando comentario individual: {e}")
                continue
                
    except Exception as e:
        logger.warning(f"Error procesando comentarios: {e}")

async def scrap_comentadores_instagram(page, perfil_url, username, max_posts=5):
    """Scrapear usuarios que comentaron los posts del usuario"""
    logger.info("Extrayendo comentarios de los últimos %d posts...", max_posts)
    
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(3000)
        
        urls_posts = await extraer_posts_del_perfil(page, max_posts)
        
        comentarios = []
        for i, url_post in enumerate(urls_posts, 1):
            logger.info("Procesando comentarios del post %d/%d", i, len(urls_posts))
            
            # Intentar extracción normal primero
            comentarios_post = await extraer_comentarios_post(page, url_post, i)
            
            # Si no hay comentarios, intentar con modal
            if not comentarios_post:
                logger.info("Intentando extracción en modal...")
                comentarios_post = await extraer_comentarios_en_modal(page, url_post, i)
            
            comentarios.extend(comentarios_post)
            
            # Rate limiting cada 3 posts
            if i % 3 == 0:
                logger.info("Pausa de rate limiting después de %d posts...", i)
                await asyncio.sleep(3)
            else:
                await asyncio.sleep(2)
        
        logger.info("Total de comentarios únicos encontrados: %d", len(comentarios))
        return comentarios
        
    except Exception as e:
        logger.exception(f"Error extrayendo comentadores: {e}")
        return []

# Funciones alias para mantener compatibilidad
async def scrap_lista_usuarios(page, perfil_url, tipo):
    """Función alias para mantener compatibilidad"""
    username = await obtener_nombre_usuario_instagram(page)
    username_str = username.get('username', '')
    
    if tipo == "seguidores":
        return await scrap_seguidores(page, perfil_url, username_str)
    elif tipo == "seguidos":
        return await scrap_seguidos(page, perfil_url, username_str)
    else:
        logger.warning("Tipo de lista inválido")
        return []
