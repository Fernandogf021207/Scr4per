import asyncio
import logging
import json
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from src.scrapers.facebook.config import FACEBOOK_CONFIG
from src.utils.list_parser import build_user_item
from src.utils.url import normalize_input_url, absolute_url_keep_query

logger = logging.getLogger(__name__)


async def _open_reactions_overlay(page) -> bool:
    """Encuentra y abre el disparador de reacciones visible con heurísticas de texto."""
    try:
        return await page.evaluate(
            """
            () => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return (
                        style &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none' &&
                        rect.width > 8 &&
                        rect.height > 8 &&
                        rect.bottom > 0 &&
                        rect.top < window.innerHeight
                    );
                };

                const textFor = (el) => {
                    const aria = el.getAttribute('aria-label') || '';
                    const text = el.textContent || '';
                    return `${aria} ${text}`.toLowerCase().replace(/\s+/g, ' ').trim();
                };

                const hasReactionHint = (text) => {
                    return [
                        'reacci',
                        'reaction',
                        'all reactions',
                        'todas las reacciones',
                        'like',
                        'me gusta',
                    ].some((token) => text.includes(token));
                };

                let best = null;
                let bestScore = -1;
                const candidates = Array.from(document.querySelectorAll('a, button, [role="button"], [aria-label]'));

                for (const el of candidates) {
                    if (!isVisible(el)) continue;
                    if (el.closest('div[role="article"][aria-label*="Comentario"], div[role="article"][aria-label*="Comment"]')) {
                        continue;
                    }

                    const text = textFor(el);
                    if (!hasReactionHint(text)) continue;

                    let score = 0;
                    if (el.getAttribute('aria-label')) score += 3;
                    if (/\d/.test(text)) score += 2;
                    if (text.includes('todas las reacciones') || text.includes('all reactions')) score += 5;
                    if (text.includes('reaction') || text.includes('reacci')) score += 4;
                    if (text.includes('like') || text.includes('me gusta')) score += 1;

                    const rect = el.getBoundingClientRect();
                    if (rect.top < window.innerHeight * 0.85) score += 1;

                    if (score > bestScore) {
                        best = el;
                        bestScore = score;
                    }
                }

                if (!best) return false;
                best.click();
                return true;
            }
            """
        )
    except Exception:
        return False


async def _scroll_visible_overlay(page, max_scrolls: int = 8, delta: int = 900) -> int:
    """Hace scroll sobre el contenedor visible más probable dentro del overlay/modal activo."""
    scrolled_steps = 0
    stagnant_cycles = 0

    for _ in range(max_scrolls):
        info = await page.evaluate(
            """
            (delta) => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return (
                        style &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none' &&
                        rect.width > 40 &&
                        rect.height > 40 &&
                        rect.bottom > 0 &&
                        rect.top < window.innerHeight
                    );
                };

                let best = null;
                let bestScore = -1;

                for (const el of document.querySelectorAll('*')) {
                    if (!isVisible(el)) continue;

                    const style = window.getComputedStyle(el);
                    const scrollHeight = el.scrollHeight || 0;
                    const clientHeight = el.clientHeight || 0;
                    const overflowY = `${style.overflowY || ''} ${style.overflow || ''}`;
                    const canScroll = scrollHeight > clientHeight + 80;
                    if (!canScroll) continue;
                    if (!/(auto|scroll)/.test(overflowY) && !el.closest('[role="dialog"], [aria-modal="true"]')) {
                        continue;
                    }

                    let score = scrollHeight - clientHeight;
                    if (el.closest('[role="dialog"], [aria-modal="true"]')) score += 100000;
                    if (style.position === 'fixed' || style.position === 'sticky') score += 5000;
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 250) score += 500;
                    if (rect.height > 250) score += 500;

                    if (score > bestScore) {
                        best = el;
                        bestScore = score;
                    }
                }

                const target = best || document.scrollingElement || document.documentElement;
                if (!target) {
                    return { found: false, before: 0, after: 0, maxTop: 0 };
                }

                const before = target.scrollTop || 0;
                if (typeof target.scrollBy === 'function') {
                    target.scrollBy(0, delta);
                } else {
                    target.scrollTop = before + delta;
                }
                const after = target.scrollTop || 0;
                const maxTop = Math.max(0, (target.scrollHeight || 0) - (target.clientHeight || 0));

                return { found: true, before, after, maxTop };
            }
            """,
            delta,
        )

        if not info.get('found'):
            break

        scrolled_steps += 1
        if info.get('after', 0) <= info.get('before', 0) + 5:
            stagnant_cycles += 1
            if stagnant_cycles >= 2:
                break
        else:
            stagnant_cycles = 0

        await asyncio.sleep(0.6)

    return scrolled_steps

async def login_facebook(page, max_retries: int = 3) -> bool:
    """Implementación limpia de evasión y verificación de sesión con Scrapling."""
    url = "https://www.facebook.com/"
    
    for attempt in range(max_retries):
        try:
            await page.goto(url)
            await page.wait_for_load_state('domcontentloaded')
            
            current_url = page.url.lower()
            if "login.php" in current_url:
                logger.error("Redirigido a login - la sesión (cookies) expiró o es inválida.")
                return False
                
            if "checkpoint" in current_url:
                logger.error("Cuenta en Checkpoint (Bloqueada).")
                return False
                
            nav_present = await page.query_selector('div[role="navigation"], nav')
            if nav_present:
                logger.info("Sesión válida y lista.")
                return True
                
            logger.warning("No se detectó navegación, reintentando...")
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Error en intento {attempt+1}: {e}")
            await asyncio.sleep(2)
            
    return False

async def get_profile_data_scrapling(page, profile_url: str) -> dict:
    """
    Obtiene los datos iniciales de un perfil.
    Usa Scrapling Selector para parsear el HTML ya cargado por Playwright.
    """
    url = normalize_input_url('facebook', profile_url)
    
    # Navegación con Playwright
    await page.goto(url)
    await asyncio.sleep(3) # Esperar a que renderice React
    
    # Extraer contenido HTML ya renderizado
    content = await page.content()
    
    name = "unknown"
    user_id = None
    profile_pic = ""
    
    # Parsear con Scrapling Selector si hay contenido suficiente
    if content and len(content) > 500:
        try:
            from scrapling import Selector
            response = Selector(text=content)
            
            # Nombre con selectores adaptativos
            for sel in ['h1', 'h2[dir="auto"]']:
                element = response.css(sel)
                if element:
                    name = element[0].text
                    if name and name.strip():
                        break
                    
            # Foto de perfil
            pic_elements = response.css('image[aria-label*="profile"], img[alt*="profile"]')
            if pic_elements:
                profile_pic = (pic_elements[0].attrib.get('xlink:href')
                               or pic_elements[0].attrib.get('src') or "")
        except Exception as e:
            logger.warning(f"Scrapling Selector no pudo parsear el HTML: {e}. Usando Playwright puro.")
    
    # Fallback a Playwright si Scrapling no obtuvo el nombre
    if name == "unknown" or not name:
        try:
            el = await page.query_selector('h1')
            if el:
                name = (await el.inner_text()).strip()
        except Exception:
            pass
            
    # Extraer ID mediante regex en el HTML fuente
    import re
    match = re.search(r'"userID"\s*:\s*"(\d+)"', content)
    if not match:
        match = re.search(r'userID:"(\d+)"', content)
    if match:
        user_id = match.group(1)
        
    # Limpieza de URL
    username = url.split('facebook.com/')[-1].strip('/').split('?')[0]
    if user_id and 'profile.php' in username:
        username = user_id
        
    return {
        'username': username,
        'nombre_completo': name,
        'foto_perfil': profile_pic,
        'url_usuario': url,
        'facebook_id': user_id
    }

async def scrap_list_network_scrapling(page, profile_url: str, list_type: str) -> List[dict]:
    """
    Scrapea una lista (followers, following, friends) usando:
    1. Scroll + extracción DOM por JS (igual que extraer_usuarios_listado original)
    2. Interception GraphQL como suplemento
    """
    INVALID_PATHS = [
        '/followers', '/following', '/friends', '/videos', '/photo', '/photos',
        '/tv', '/events', '/past_events', '/likes', '/likes_all', '/music',
        '/sports', '/map', '/movies', '/pages', '/groups', '/watch', '/reel',
        '/story', '/games', '/reviews_given', '/reviews_written',
        '/video_movies_watch', '/profile_songs', '/places_recent', '/posts/',
        '/marketplace', '/status/',
    ]

    suffix = {
        'friends_all': 'friends_all',
        'followers': 'followers',
        'followed': 'following'
    }.get(list_type, list_type)

    target_url = f"{normalize_input_url('facebook', profile_url).rstrip('/')}/{suffix}/"
    # Slug del perfil principal para no auto-incluirse
    main_slug = normalize_input_url('facebook', profile_url).rstrip('/').split('facebook.com/')[-1].strip('/')

    extracted_users: dict = {}
    graphql_responses: list = []

    # JS batch extractor — mismo patrón que el scraper original
    _JS_BATCH = '''
    () => {
      const root = document.querySelector('div[role="main"]') || document;
      const anchors = Array.from(root.querySelectorAll('a[href]'));
      const out = [];
      for (const a of anchors) {
        const href = a.getAttribute('href') || '';
        if (!href || href.startsWith('javascript:') || href === '#') continue;
        const text = (a.textContent || '').trim();
        let img = '';
        const cont = a.closest('div');
        const imgel = cont
          ? (cont.querySelector('img, image') || a.querySelector('img, image'))
          : a.querySelector('img, image');
        if (imgel) {
          img = imgel.currentSrc || imgel.src || imgel.getAttribute('xlink:href') || '';
        }
        out.push({ href, text, img });
      }
      return out;
    }
    '''

    def _process_dom_batch(raw_data: list):
        added = 0
        for rec in raw_data:
            try:
                href = rec.get('href') or ''
                if not href:
                    continue
                # Normalizar URL
                if href.startswith('/'):
                    href = 'https://www.facebook.com' + href
                elif not href.startswith('http'):
                    continue
                clean = href.split('?')[0]
                # Filtrar rutas inválidas
                if any(pat in clean for pat in INVALID_PATHS):
                    continue
                slug = clean.split('facebook.com/')[-1].strip('/')
                if slug in ('', 'friends', 'followers', 'following'):
                    continue
                if slug == main_slug:
                    continue
                if clean in extracted_users:
                    continue
                nombre = (rec.get('text') or '').strip() or slug.split('?')[0]
                # Filtrar textos que son "N amigos en común" o similares
                if any(nombre.lower().startswith(p) for p in ('1 amigo', '2 amigos', '3 amigos',
                                                               '1 friend', '2 friends')):
                    continue
                foto = rec.get('img') or ''
                import urllib.parse as _up
                parsed = _up.urlparse(href)
                q = _up.parse_qs(parsed.query)
                final_url = href if ('id' in q or 'profile.php' in clean) else clean
                extracted_users[clean] = build_user_item('facebook', final_url, nombre, foto)
                added += 1
            except Exception:
                continue
        return added

    # Interceptar GraphQL en paralelo como suplemento
    async def intercept_graphql(response):
        if "graphql" in response.url.lower() and response.request.method == "POST":
            try:
                text = await response.text()
                if "node" in text and ("Profile" in text or "User" in text or "name" in text):
                    data = await response.json()
                    graphql_responses.append(data)
            except Exception:
                pass

    page.on("response", intercept_graphql)

    logger.info(f"Navegando a {target_url} con Network Interception...")
    await page.goto(target_url)
    await asyncio.sleep(3)  # carga inicial

    max_scrolls = 60
    no_new = 0
    last_total = 0

    for i in range(max_scrolls):
        # Extraer DOM visible en este scroll
        try:
            raw = await page.evaluate(_JS_BATCH)
            added_dom = _process_dom_batch(raw or [])
        except Exception:
            added_dom = 0

        # Scroll — igual que el original (mouse wheel + window.scrollBy)
        try:
            await page.mouse.wheel(0, 3000)
        except Exception:
            await page.evaluate("window.scrollBy(0, 3000)")
        await asyncio.sleep(0.9)

        current_total = len(extracted_users)
        if current_total == last_total:
            no_new += 1
            if no_new >= 4:
                logger.info("Sin nuevos usuarios. Fin de lista.")
                break
        else:
            no_new = 0

        last_total = current_total
        logger.info(f"Scroll {i+1}: {current_total} usuarios DOM | {len(graphql_responses)} tramos GraphQL")

    page.remove_listener("response", intercept_graphql)

    # Suplementar con GraphQL (puede agregar perfiles con ID numérico que el DOM no muestra)
    for payload in graphql_responses:
        try:
            _extract_users_from_json(payload, extracted_users)
        except Exception:
            pass

    return list(extracted_users.values())


def _extract_users_from_json(data, result_dict: dict, depth: int = 0):
    """
    Busca nodos de usuario en JSON de GraphQL de Facebook.
    Estrategia flexible: cualquier dict que tenga 'name' (str) + 'url' (str con facebook.com)
    y NO sea un contenedor de alto nivel.
    """
    if depth > 15 or not isinstance(data, (dict, list)):
        return

    if isinstance(data, dict):
        name = data.get('name')
        url = data.get('url') or data.get('profile_url')

        # Nodo válido: tiene nombre de persona y URL de Facebook
        if (
            isinstance(name, str) and len(name) > 1
            and isinstance(url, str)
            and 'facebook.com' in url
            and '/groups/' not in url  # excluir grupos
            and '/pages/' not in url    # excluir páginas
        ):
            try:
                clean_url = url.split('?')[0]
                if clean_url not in result_dict:
                    import urllib.parse
                    parsed = urllib.parse.urlparse(url)
                    q = urllib.parse.parse_qs(parsed.query)
                    final_url = url if ('id' in q or 'profile.php' in clean_url) else clean_url
                    pic = ""
                    pp = data.get('profile_picture') or data.get('profilePicture')
                    if isinstance(pp, dict):
                        pic = pp.get('uri') or pp.get('url') or ""
                    result_dict[clean_url] = build_user_item('facebook', final_url, name, pic)
            except Exception:
                pass

        # Recursión sobre todos los valores
        for v in data.values():
            _extract_users_from_json(v, result_dict, depth + 1)

    elif isinstance(data, list):
        for item in data:
            _extract_users_from_json(item, result_dict, depth + 1)

async def scrap_photo_engagements_scrapling(page, profile_url: str, max_photos: int = 5) -> Dict[str, List[dict]]:
    """
    Extrae fotos del perfil e intercepta GraphQL por foto para obtener
    reacciones Y comentarios de cada una.
    """
    url = normalize_input_url('facebook', profile_url)
    photos_url = f"{url.rstrip('/')}/photos/"
    
    logger.info("Navegando a la sección de fotos para extraer enlaces...")
    await page.goto(photos_url)
    await asyncio.sleep(2)
    
    content = await page.content()
    response = None
    if content and len(content) > 500:
        try:
            from scrapling import Selector
            response = Selector(text=content)
        except Exception as e:
            logger.warning(f"Scrapling Selector fallo en fotos: {e}")
        
    photo_links = []
    
    if response is not None:
        elements = response.css('a[href*="photo.php"], a[href*="/photos/"]')
        for el in elements:
            href = el.attrib.get('href')
            if href:
                full_url = absolute_url_keep_query(href)
                if full_url not in photo_links:
                    photo_links.append(full_url)
                if len(photo_links) >= max_photos:
                    break
    
    if not photo_links:
        try:
            anchors = await page.query_selector_all('a[href*="photo.php"], a[href*="/photos/"]')
            for a in anchors:
                href = await a.get_attribute('href')
                if href:
                    full_url = absolute_url_keep_query(href)
                    if full_url not in photo_links:
                        photo_links.append(full_url)
                    if len(photo_links) >= max_photos:
                        break
        except Exception as e:
            logger.warning(f"Fallback Playwright para fotos fallo: {e}")
    
    if not photo_links:
        logger.warning(f"No se encontraron fotos en {photos_url}")
        return {'reactions': [], 'comments': []}
        
    logger.info(f"Se encontraron {len(photo_links)} fotos para procesar.")

    # Acumuladores globales
    all_reactions: dict = {}
    all_comments: dict = {}

    for idx, p_url in enumerate(photo_links):
        logger.info(f"Procesando Foto [{idx+1}/{len(photo_links)}]: {p_url}")
        
        # Buffer GraphQL POR FOTO para poder atribuir correctamente
        photo_graphql: list = []

        async def intercept_photo(resp):
            if "graphql" in resp.url.lower() and resp.request.method == "POST":
                try:
                    text = await resp.text()
                    if any(k in text for k in ("reactor", "comment", "Feedback", "reaction", "Comment")):
                        data = await resp.json()
                        photo_graphql.append(data)
                except Exception:
                    pass

        page.on("response", intercept_photo)
        try:
            await page.goto(p_url)
            await asyncio.sleep(2)

            # --- Reacciones: abrir modal de likes ---
            try:
                opened_overlay = await _open_reactions_overlay(page)
                if not opened_overlay:
                    like_btn = await page.query_selector(
                        'span[aria-label], '
                        'a[aria-label*="reacci"], '
                        'a[aria-label*="Like"], '
                        '[role="button"][aria-label*="reacci"], '
                        '[role="button"][aria-label*="reaction"]'
                    )
                    if like_btn:
                        await like_btn.click()
                        opened_overlay = True

                if opened_overlay:
                    await asyncio.sleep(1.5)
                    scrolled = await _scroll_visible_overlay(page)
                    logger.info(f"Overlay de reacciones abierto: {scrolled} scrolls ejecutados")
            except Exception as e:
                logger.debug(f"Modal likes no disponible: {e}")

            # --- Comentarios: scroll de la página ---
            for _ in range(4):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(0.6)

            # Cerrar modal si quedó abierto
            try:
                await page.keyboard.press('Escape')
                await asyncio.sleep(0.3)
            except Exception:
                pass

        except Exception as e:
            import traceback
            logger.error(f"Error procesando foto {p_url}: {e}\n{traceback.format_exc()}")
        finally:
            page.remove_listener("response", intercept_photo)

        # Parsear lo interceptado en esta foto
        photo_reactions: dict = {}
        photo_comments: dict = {}
        for payload in photo_graphql:
            _extract_engagements_from_json(payload, photo_reactions, photo_comments)

        # --- Fallback DOM para autores de comentarios ---
        # Los comentarios en Facebook están en div[role="article"] con un a[href] de perfil
        if not photo_comments:
            try:
                comment_authors = await page.evaluate('''
                    () => {
                        const articles = document.querySelectorAll('div[role="article"]');
                        const out = [];
                        for (const art of articles) {
                            // El autor es el primer enlace de perfil dentro del artículo
                            const links = art.querySelectorAll('a[href*="facebook.com/"], a[href^="/"]');
                            for (const a of links) {
                                const href = a.getAttribute("href") || "";
                                if (!href || href.includes("/photo") || href.includes("/groups/")) continue;
                                const txt = (a.textContent || "").trim();
                                if (!txt) continue;
                                // Obtener foto del avatar
                                const img = art.querySelector("img");
                                const imgSrc = img ? (img.currentSrc || img.src || "") : "";
                                out.push({ href, text: txt, img: imgSrc });
                                break; // solo el primer autor por artículo
                            }
                        }
                        return out;
                    }
                ''')
                for rec in (comment_authors or []):
                    href = rec.get('href') or ''
                    if not href:
                        continue
                    if href.startswith('/'):
                        href = 'https://www.facebook.com' + href
                    clean = href.split('?')[0]
                    if clean in photo_comments:
                        continue
                    nombre = (rec.get('text') or '').strip()
                    foto = rec.get('img') or ''
                    user_item = build_user_item('facebook', clean, nombre, foto)
                    user_item['interaction_type'] = 'comment'
                    photo_comments[clean] = user_item
            except Exception as e:
                logger.debug(f"Fallback DOM comentarios fallo: {e}")

        logger.info(f"  Foto {idx+1}: {len(photo_reactions)} reacciones, {len(photo_comments)} comentarios")
        all_reactions.update(photo_reactions)
        all_comments.update(photo_comments)


    return {
        'reactions': list(all_reactions.values()),
        'comments': list(all_comments.values())
    }

def _extract_engagements_from_json(data, reactions_dict: dict, comments_dict: dict):
    """
    Parsea JSON de Graphql y clasifica usuarios como Reactores o Comentadores.
    """
    if isinstance(data, dict):
        # Detectar Reactores (Likes, Love, etc)
        if 'node' in data and isinstance(data['node'], dict):
            node = data['node']
            if node.get('__typename') == 'User':
                # Si el nodo padre o hermano tiene indicios de reacción:
                user_item = _build_user_from_graphql_node(node)
                if user_item:
                    url = user_item['link_usuario']
                    # Lo guardamos temporalmente en reacciones a menos que encontremos explícito el tipo de feedback
                    if url not in reactions_dict:
                        user_item['interaction_type'] = 'reaction'
                        reactions_dict[url] = user_item
                        
        # Detectar Comentarios específicos
        if data.get('__typename') == 'Comment' and 'author' in data:
            author_node = data.get('author')
            if isinstance(author_node, dict):
                user_item = _build_user_from_graphql_node(author_node)
                if user_item:
                    url = user_item['link_usuario']
                    
                    if url not in comments_dict:
                        user_item['interaction_type'] = 'comment'
                        # Extraemos el texto del comentario
                        body = data.get('body')
                        if body and isinstance(body, dict):
                            user_item['comment_text'] = body.get('text')
                        comments_dict[url] = user_item
                        
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                _extract_engagements_from_json(v, reactions_dict, comments_dict)
                
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                _extract_engagements_from_json(item, reactions_dict, comments_dict)

def _build_user_from_graphql_node(node: dict) -> Optional[dict]:
    try:
        name = node.get('name')
        url = node.get('url')
        pic = ""
        profile_picture = node.get('profile_picture')
        if profile_picture and isinstance(profile_picture, dict):
            pic = profile_picture.get('uri') or ""
            
        if url and name:
            clean_url = url.split('?')[0]
            import urllib.parse
            parsed_url = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed_url.query)
            
            is_profile = 'id' in query or 'profile.php' in clean_url
            final_url = url if is_profile else clean_url
                
            return build_user_item('facebook', final_url, name, pic)
    except Exception:
        pass
    return None


def export_to_csv(results: dict, output_path: str) -> str:
    """
    Exporta los resultados de scraping a CSV usando pandas.

    Parámetros:
        results (dict): Diccionario con las siguientes claves opcionales:
            - 'profile':    dict con datos del perfil principal
            - 'friends':    list[dict] de amigos
            - 'followers':  list[dict] de seguidores
            - 'followed':   list[dict] de seguidos
            - 'reactions':  list[dict] de usuarios que reaccionaron a fotos
            - 'comments':   list[dict] de usuarios que comentaron en fotos
        output_path (str): Ruta de destino del archivo CSV.

    Retorna:
        str: Ruta final del archivo generado.
    """
    import pandas as pd

    rows = []

    # Perfil principal
    profile = results.get('profile') or {}
    if profile:
        rows.append({
            'tipo': 'PERFIL',
            'username': profile.get('username', ''),
            'nombre_completo': profile.get('nombre_completo', ''),
            'url_perfil': profile.get('url_usuario', ''),
            'foto': profile.get('foto_perfil', ''),
            'facebook_id': profile.get('facebook_id', ''),
            'interaccion': '',
            'texto_comentario': '',
        })

    # Función auxiliar para convertir filas de usuarios
    def _add_users(user_list: List[dict], tipo: str):
        for u in user_list:
            rows.append({
                'tipo': tipo,
                'username': u.get('username_usuario', ''),
                'nombre_completo': u.get('nombre_completo_usuario', ''),
                'url_perfil': u.get('link_usuario', ''),
                'foto': u.get('url_foto', ''),
                'facebook_id': '',
                'interaccion': u.get('interaction_type', ''),
                'texto_comentario': u.get('comment_text', ''),
            })

    _add_users(results.get('friends', []), 'AMIGO')
    _add_users(results.get('followers', []), 'SEGUIDOR')
    _add_users(results.get('followed', []), 'SEGUIDO')
    _add_users(results.get('reactions', []), 'REACCION_FOTO')
    _add_users(results.get('comments', []), 'COMENTARIO_FOTO')

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')  # utf-8-sig para que Excel lo abra bien
    logger.info(f"CSV exportado exitosamente: {output_path} ({len(df)} filas)")
    return output_path
