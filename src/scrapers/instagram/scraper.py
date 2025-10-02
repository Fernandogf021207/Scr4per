import asyncio
import logging
import time
from urllib.parse import urljoin
from src.utils.common import limpiar_url
from src.utils.url import normalize_input_url
from src.utils.dom import find_scroll_container, scroll_element, scroll_window
from src.utils.list_parser import build_user_item
from src.utils.url import normalize_post_url
import os
import httpx
from src.scrapers.resource_blocking import start_list_blocking  # added
from src.scrapers.scrolling import scroll_loop  # added
from src.scrapers.concurrency import run_limited  # added
from src.scrapers.selector_registry import get_selectors, registry_version  # added
from src.scrapers.errors import classify_page_state, ErrorCode, ScrapeError  # added

logger = logging.getLogger(__name__)

def _ts() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

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
    """Obtener datos del perfil principal (instrumentado)."""
    logger.info(f"{_ts()} instagram.profile start")
    perfil_url = normalize_input_url('instagram', perfil_url)
    t0 = time.time()
    await page.goto(perfil_url)
    try:
        await page.wait_for_selector('header', timeout=1800)
    except Exception:
        await page.wait_for_timeout(600)
    datos_usuario_ig = await obtener_nombre_usuario_instagram(page)
    username = datos_usuario_ig['username']
    nombre_completo = datos_usuario_ig['nombre_completo']
    foto_perfil = await obtener_foto_perfil_instagram(page)
    logger.info(f"{_ts()} instagram.profile detected username={username} name={nombre_completo} duration_ms={(time.time()-t0)*1000:.0f}")
    return {
        'username': username,
        'nombre_completo': nombre_completo,
        'foto_perfil': foto_perfil or "",
        'url_usuario': perfil_url
    }

async def extraer_usuarios_instagram(page, tipo_lista="seguidores", usuario_principal=""):
    """Extraer usuarios de una lista usando scroll_loop (Fase2: migración).

    Ajuste: evitar bottom false-positive en listas largas que sólo cargan un chunk inicial.
    Estrategia: exigir al menos 3 iteraciones antes de permitir bottom_check y reducir margen.
    """
    logger.info(f"{_ts()} instagram.list start type={tipo_lista}")
    usuarios_dict = {}
    blocker = await start_list_blocking(page, 'instagram', phase=f'list.{tipo_lista}')
    t0 = time.time()

    container = await find_scroll_container(page)
    iter_state = {'count': 0}

    async def process_once() -> int:
        before = len(usuarios_dict)
        await procesar_usuarios_en_modal(page, usuarios_dict, usuario_principal, tipo_lista)
        iter_state['count'] += 1
        return len(usuarios_dict) - before

    async def do_scroll():
        try:
            if container:
                await scroll_element(container, 900)
            else:
                await scroll_window(page, 800)
        except Exception:
            pass

    async def bottom_check() -> bool:
        # No considerar bottom hasta al menos 3 iteraciones (1er chunk + 2 cargas adicionales potenciales)
        if iter_state['count'] < 3:
            return False
        try:
            if container:
                is_bottom, metrics = await page.evaluate("""
                    el => {
                        const st = el.scrollTop; const ch = el.clientHeight; const sh = el.scrollHeight;
                        return [ (st + ch) >= (sh - 150), {st, ch, sh} ];
                    }
                """, container)
            else:
                is_bottom, metrics = await page.evaluate("""
                    () => {
                        const st = window.pageYOffset || document.documentElement.scrollTop; 
                        const ch = window.innerHeight; 
                        const sh = document.documentElement.scrollHeight || document.body.scrollHeight;
                        return [ (st + ch) >= (sh - 200), {st, ch, sh} ];
                    }
                """)
            if is_bottom:
                logger.info(f"{_ts()} instagram.list bottom_candidate iter={iter_state['count']} metrics={metrics} total={len(usuarios_dict)}")
            return is_bottom
        except Exception:
            return False

    stats = await scroll_loop(
        process_once=process_once,
        do_scroll=do_scroll,
        max_scrolls=40,
        pause_ms=900,
        stagnation_limit=6,  # subir umbral para dar chance a nuevas cargas
        empty_limit=2,
        bottom_check=bottom_check,
        adaptive=True,
        adaptive_decay_threshold=0.30,
        log_prefix=f"instagram.list type={tipo_lista}",
        timeout_ms=35000,
    )

    await blocker.stop()
    # Señal heurística: si total < 30 y reason=bottom en pocas iteraciones -> posible truncamiento
    if stats['reason'] == 'bottom' and stats.get('iterations', 0) <= 4 and len(usuarios_dict) < 30:
        logger.warning(f"{_ts()} instagram.list suspicion=EARLY_BOTTOM type={tipo_lista} total={len(usuarios_dict)} iter={stats.get('iterations')} reason={stats['reason']}")
    if stats['reason'] == 'timeout':
        logger.warning(f"{_ts()} instagram.list error.code=TIMEOUT type={tipo_lista} duration_ms={stats['duration_ms']}")
    if len(usuarios_dict) == 0:
        logger.warning(f"{_ts()} instagram.list error.code=EMPTY_LIST type={tipo_lista} reason={stats['reason']}")
    logger.info(f"{_ts()} instagram.list end type={tipo_lista} total={len(usuarios_dict)} duration_ms={stats['duration_ms']} reason={stats['reason']} scrolls={stats['iterations']} started_at={(t0):.0f}")
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
        
        elementos_usuarios = []
        for selector in selectores_contenedor:
            try:
                elementos = await page.query_selector_all(selector)
                if elementos:
                    # Filtrar elementos que realmente contienen información de usuario
                    elementos_validos = []
                    for elemento in elementos:
                        try:
                            # Verificar que tiene enlace de perfil
                            enlace = await elemento.query_selector('a[role="link"]') or elemento
                            if enlace:
                                href = await enlace.get_attribute("href")
                                if href and href.startswith('/') and len(href.split('/')) >= 2:
                                    elementos_validos.append(elemento)
                        except:
                            continue
                    
                    if elementos_validos:
                        elementos_usuarios = elementos_validos
                        logger.info(f"{_ts()} instagram.list selector hit selector='{selector}' elements={len(elementos_usuarios)}")
                        break
            except:
                continue
        
        if not elementos_usuarios:
            logger.info(f"{_ts()} instagram.list empty_scroll")
            return

        # Procesar cada elemento de usuario
        for elemento in elementos_usuarios:
            try:
                enlace = await elemento.query_selector('a[role="link"]') or elemento
                if not enlace:
                    continue

                href = await enlace.get_attribute("href")
                if not href or not href.startswith('/'):
                    continue

                # Construir URL absoluta y normalizada con builder
                url_usuario_abs = f"https://www.instagram.com{href}"
                texto_elemento = await elemento.inner_text()
                lineas = texto_elemento.strip().split('\n')
                nombre_completo_usuario = lineas[0] if lineas and lineas[0] else None
                img_element = await elemento.query_selector('img')
                url_foto = await img_element.get_attribute("src") if img_element else ""
                item = build_user_item('instagram', url_usuario_abs, nombre_completo_usuario, url_foto)
                url_limpia = item['link_usuario']
                username_usuario = item['username_usuario']

                # Evitar procesar el usuario principal
                if username_usuario == usuario_principal:
                    continue

                # Evitar duplicados
                if url_limpia in usuarios_dict:
                    continue

                usuarios_dict[url_limpia] = item

            except Exception as e:
                logger.warning(f"Error procesando usuario individual: {e}")
                continue
                
    except Exception as e:
        logger.warning(f"Error procesando usuarios en modal: {e}")

async def navegar_a_lista_instagram(page, perfil_url, tipo_lista="followers"):
    """Navegar a la lista de seguidores o seguidos en Instagram (refactor v2 con registry + error codes)."""
    phase = 'nav_list'
    platform = 'instagram'
    try:
        perfil_url = normalize_input_url('instagram', perfil_url)
        await page.goto(perfil_url, timeout=10_000)
        try:
            await page.wait_for_selector('header', timeout=3000)
        except Exception:
            pass
        await page.wait_for_timeout(800)

        if tipo_lista == "followers":
            selectores_enlace = get_selectors(platform, 'lists.followers_link')
            nombre_lista = "seguidores"
        else:
            selectores_enlace = get_selectors(platform, 'lists.following_link')
            nombre_lista = "seguidos"
        logger.info(f"{_ts()} instagram.nav finding list={nombre_lista} registry_ver={registry_version(platform)}")
        enlace_lista = None
        for selector in selectores_enlace:
            try:
                enlace_lista = await page.query_selector(selector)
                if enlace_lista:
                    break
            except Exception:
                continue
        if not enlace_lista:
            # Clasificar estado de la página
            try:
                body_text = await page.inner_text('body')
            except Exception:
                body_text = ''
            state = classify_page_state(platform, body_text) or ErrorCode.SELECTOR_MISS
            logger.warning(f"{_ts()} instagram.nav link_not_found list={nombre_lista} code={state.value}")
            return False
        logger.info(f"{_ts()} instagram.nav clicking list={nombre_lista}")
        await enlace_lista.click()
        # Esperar apertura de dialog (timeout fase)
        try:
            await page.wait_for_selector('div[role="dialog"]', timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(1200)
        return True
    except Exception as e:
        logger.warning(f"{_ts()} instagram.nav error list={tipo_lista} error={e}")
        return False

async def scrap_seguidores(page, perfil_url, username):
    """Scrapear seguidores (instrumentado)."""
    logger.info(f"{_ts()} instagram.followers start")
    try:
        if await navegar_a_lista_instagram(page, perfil_url, "followers"):
            seguidores = await extraer_usuarios_instagram(page, "seguidores", username)
            if len(seguidores) == 0:
                logger.warning(f"{_ts()} instagram.followers error.code=EMPTY_LIST")
            logger.info(f"{_ts()} instagram.followers count={len(seguidores)}")
            return seguidores
        else:
            logger.info(f"{_ts()} instagram.followers none")
            return []
    except Exception as e:
        logger.warning(f"{_ts()} instagram.followers error={e}")
        return []

async def scrap_seguidos(page, perfil_url, username):
    """Scrapear seguidos (instrumentado)."""
    logger.info(f"{_ts()} instagram.following start")
    try:
        if await navegar_a_lista_instagram(page, perfil_url, "following"):
            seguidos = await extraer_usuarios_instagram(page, "seguidos", username)
            if len(seguidos) == 0:
                logger.warning(f"{_ts()} instagram.following error.code=EMPTY_LIST")
            logger.info(f"{_ts()} instagram.following count={len(seguidos)}")
            return seguidos
        else:
            logger.info(f"{_ts()} instagram.following none")
            return []
    except Exception as e:
        logger.warning(f"{_ts()} instagram.following error={e}")
        return []

async def extraer_posts_del_perfil(page, max_posts=10):
    """Extraer URLs de posts (instrumentado)."""
    logger.info(f"{_ts()} instagram.posts start target={max_posts}")
    
    try:
        urls_posts = set()
        scroll_attempts = 0
        max_scrolls = 8
        no_new_posts_count = 0
        max_no_new_posts = 2
        
        while len(urls_posts) < max_posts and scroll_attempts < max_scrolls and no_new_posts_count < max_no_new_posts:
            current_posts_count = len(urls_posts)
            
            # Scroll manual en la página del perfil
            await page.evaluate("""
                () => {
                    window.scrollBy(0, window.innerHeight * 0.8);
                }
            """)
            
            await page.wait_for_timeout(1100)
            
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
                logger.info(f"{_ts()} instagram.posts progress count={len(urls_posts)} scroll={scroll_attempts + 1}")
            else:
                no_new_posts_count += 1
                logger.info(f"{_ts()} instagram.posts no_new scroll={scroll_attempts + 1} seq={no_new_posts_count}")
            
            scroll_attempts += 1
            
            # Verificar si llegamos al final de la página
            is_at_bottom = await page.evaluate("""
                () => {
                    return (window.innerHeight + window.pageYOffset) >= document.body.scrollHeight - 1000;
                }
            """)
            
            if is_at_bottom:
                logger.info(f"{_ts()} instagram.posts end_bottom count={len(urls_posts)}")
                break
        
        urls_posts = list(urls_posts)[:max_posts]
        logger.info(f"{_ts()} instagram.posts final_count={len(urls_posts)}")
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
    """Scrapea usuarios que dieron like (liked_by) en los últimos posts (concurrencia limitada)."""
    try:
        perfil_url = normalize_input_url('instagram', perfil_url)
        await page.goto(perfil_url)
        await page.wait_for_timeout(1500)
        posts = await extraer_posts_del_perfil(page, max_posts=max_posts)
        logger.info(f"{_ts()} instagram.likes posts_found={len(posts)} target={max_posts}")
        if not posts:
            return []

        start = time.time()
        # Para cada post generamos una tarea diferida que abre y extrae likes en un contexto secuencial.
        # NOTA: El mismo 'page' no puede navegar en paralelo, idealmente se usarían nuevas pages/contextos.
        # Aquí aplicamos concurrencia cooperativa simulada: ejecutamos en secuencia porque compartimos page.
        # Si en el futuro se habilita crear nuevas pages, sustituir por apertura de new_page por tarea.

        async def process_post(post_url: str):
            try:
                await page.goto(post_url)
                await page.wait_for_timeout(2000)
                likes = await _abrir_liked_by_y_extraer_usuarios(page, post_url)
                logger.info(f"{_ts()} instagram.likes post_done url={post_url} likes={len(likes)}")
                return likes
            except Exception as e:
                logger.warning(f"instagram.likes post_error url={post_url} error={e}")
                return []

        # Debido a limitación de un solo page, el limit >1 no ofrece beneficio real; dejamos estructura para futuro multi-page.
        tasks_callables = [lambda u=pu: process_post(u) for pu in posts]
        results = await run_limited(tasks_callables, limit=1, label='ig.likes')
        aggregated = []
        for r in results:
            if r and r.ok and r.value:
                aggregated.extend(r.value)
        logger.info(f"{_ts()} instagram.likes done total_likes={len(aggregated)} duration_ms={(time.time()-start)*1000:.0f}")
        return aggregated
    except Exception:
        return []

async def extraer_comentarios_post(page, url_post, post_id):
    """Extraer comentarios de un post (instrumentado)."""
    logger.info(f"{_ts()} instagram.post_comments start post_id={post_id}")
    
    try:
        await page.goto(url_post)
        await page.wait_for_timeout(3000)
        
        comentarios_dict = {}
        
        # Primero intentar cargar más comentarios con botones
            # print("instagram: post_comments load_more")
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
                            # print(f"  ✓ Botón 'cargar más' clickeado")
                        break
                if not button_clicked:
                    break
            except Exception as e:
                logger.warning(f"No se pudo cargar más comentarios con botón: {e}")
                break
        
        # Scroll manual para cargar más comentarios
            # print("instagram: post_comments scroll")
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
                logger.info(f"{_ts()} instagram.post_comments count={len(comentarios_dict)} scroll={scroll_attempts + 1}")
            else:
                no_new_comments_count += 1
                logger.info(f"{_ts()} instagram.post_comments no_new scroll={scroll_attempts + 1}")
            
            scroll_attempts += 1
            
            # Pausa cada 5 scrolls
            if scroll_attempts % 5 == 0:
                await page.wait_for_timeout(2000)
        
        comentarios = list(comentarios_dict.values())
        logger.info(f"{_ts()} instagram.post_comments unique={len(comentarios)} post_id={post_id}")
        return comentarios
        
    except Exception as e:
        logger.error(f"Error extrayendo comentarios del post: {e}")
        return []

async def extraer_comentarios_en_modal(page, url_post, post_id):
    """Extraer comentarios cuando se abren en un modal (instrumentado)."""
    logger.info(f"{_ts()} instagram.modal_comments start post_id={post_id}")
    
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
                        logger.info(f"{_ts()} instagram.modal_comments open")
                        modal_abierto = True
                        break
            except Exception as e:
                logger.debug(f"No se pudo hacer click en botón de comentarios: {e}")
                continue
        
        if not modal_abierto:
            logger.info(f"{_ts()} instagram.modal_comments open_fail")
            return []
        
        # Hacer scroll manual dentro del modal
            # print("instagram: modal_comments scroll")
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
                logger.info(f"{_ts()} instagram.modal_comments count={len(comentarios_dict)} scroll={scroll_attempts + 1}")
            else:
                no_new_comments_count += 1
                logger.info(f"{_ts()} instagram.modal_comments no_new scroll={scroll_attempts + 1}")
            
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
        logger.info(f"{_ts()} instagram.modal_comments unique={len(comentarios)}")
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
                        logger.info(f"{_ts()} instagram.modal_comments selector hit selector='{selector}' count={len(elementos_comentarios)}")
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
                if username in ['p', 'reel', 'tv', 'stories', 'explore'] or username == "":
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
                        logger.info(f"{_ts()} instagram.post_comments selector hit selector='{selector}' count={len(elementos_comentarios)}")
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
    """Scrapear usuarios que comentaron los posts del usuario (estructura concurrente)."""
    logger.info(f"{_ts()} instagram.comments batch_start max_posts={max_posts}")
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(3000)
        urls_posts = await extraer_posts_del_perfil(page, max_posts)
        logger.info(f"{_ts()} instagram.comments posts_found={len(urls_posts)}")
        if not urls_posts:
            return []

        async def process_post(idx: int, url_post: str):
            logger.info(f"{_ts()} instagram.comments post start idx={idx}/{len(urls_posts)}")
            comentarios_post = await extraer_comentarios_post(page, url_post, idx)
            if not comentarios_post:
                logger.info(f"{_ts()} instagram.comments modal_fallback idx={idx}")
                comentarios_post = await extraer_comentarios_en_modal(page, url_post, idx)
            await asyncio.sleep(1.2 if idx % 3 else 2.5)
            return comentarios_post

        from src.scrapers.concurrency import run_limited
        callables = [lambda i=i, u=u: process_post(i+1, u) for i, u in enumerate(urls_posts)]
        # Limit 1 dado que compartimos 'page'; mantener interfaz para futura expansión multi-page.
        results = await run_limited(callables, limit=1, label='ig.comments')
        agg = []
        for r in results:
            if r and r.ok and r.value:
                agg.extend(r.value)
        logger.info(f"{_ts()} instagram.comments total={len(agg)} posts={len(urls_posts)}")
        return agg
    except Exception as e:
        logger.warning(f"{_ts()} instagram.comments error={e}")
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
        logger.info(f"{_ts()} instagram.list invalid_type")
        return []
