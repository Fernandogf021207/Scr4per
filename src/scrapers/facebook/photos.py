import time
import logging
import asyncio
import random
from typing import List, Dict
from src.utils.dom import find_scroll_container, scroll_collect
from src.scrapers.facebook.utils import get_text, get_attr, absolute_url_keep_query, normalize_profile_url
from src.utils.list_parser import build_user_item
from src.utils.url import normalize_post_url, normalize_input_url

logger = logging.getLogger(__name__)

def _ts() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

# Tiempos y parámetros de scroll en reacciones (tunable)
REACTIONS_SCROLL_WAIT_MIN = 300      # ms, espera mínima tras scroll
REACTIONS_SCROLL_WAIT_MAX = 900      # ms, espera máxima tras scroll
REACTIONS_STABILITY_RETRIES = 4      # reintentos de poll para que cargue contenido dinámico
REACTIONS_REEVAL_EVERY = 10          # re-evaluar contenedor cada N scrolls
REACTIONS_BOTTOM_STABLE_TICKS = 3    # ticks seguidos detectando fondo sin cambios antes de cortar
REACTIONS_SCROLL_HEIGHT_EPS = 24     # px de tolerancia para considerar cambio de scrollHeight

async def _find_comments_container(page):
    """Encuentra el contenedor más probable de comentarios aunque no exista un modal.

    Heurística: buscar el elemento con overflowY auto/scroll y mayor (scrollHeight-clientHeight)
    que además contenga artículos/comentarios o texto relacionado. Si no hay, devolver None.
    """
    try:
        handle = await page.evaluate_handle(
            """
            () => {
                const nodes = Array.from(document.querySelectorAll('div, section, main, article, aside'));
                let best = null; let bestScore = 0;
                for (const n of nodes) {
                    const sh = n.scrollHeight || 0;
                    const ch = n.clientHeight || 0;
                    if (sh < ch + 120) continue;
                    const style = getComputedStyle(n);
                    const oy = style.overflowY;
                    if (!(oy === 'auto' || oy === 'scroll')) continue;
                    // señales de comentarios
                    const txt = (n.getAttribute('aria-label') || n.innerText || '').toLowerCase();
                    let score = (sh - ch);
                    if (txt.includes('comentario') || txt.includes('comments')) score += 5000;
                    // si contiene artículos (comentarios) dentro
                    const hasArticles = n.querySelectorAll('[role="article"]').length;
                    if (hasArticles) score += 3000 + hasArticles * 10;
                    if (score > bestScore) { best = n; bestScore = score; }
                }
                return best;
            }
            """
        )
        return handle
    except Exception:
        return None

async def navegar_a_fotos(page, perfil_url: str) -> bool:
    """Navega a la pestaña de fotos intentando rutas conocidas y minimizando carga pesada.

    Estrategias anti-crash:
    - Usar wait_until='domcontentloaded' para no esperar recursos pesados.
    - Ejecutar window.stop() para frenar cargas adicionales (imágenes/videos).
    """
    candidates = ["photos_by", "photos", "photos_all"]
    perfil_url = normalize_input_url('facebook', perfil_url)
    base = perfil_url.rstrip('/')
    for suf in candidates:
        try:
            await page.goto(f"{base}/{suf}/", wait_until="domcontentloaded")
            # Espera dirigida por selector de fotos; no detener cargas aquí para no impedir render
            try:
                await page.wait_for_selector('a[href*="photo.php"], a[href*="/photos/"]', timeout=4000)
                return True
            except Exception:
                pass
        except Exception:
            continue
    return False

async def extraer_urls_fotos(page, max_fotos: int = 5) -> List[str]:
    urls: List[str] = []
    seen = set()
    scrolls = 0
    while len(urls) < max_fotos and scrolls < 20:
        try:
            selectores = [
                'a[href*="photo.php"]',
                'a[href*="/photos/"]',
            ]
            for sel in selectores:
                try:
                    anchors = await page.query_selector_all(sel)
                except Exception:
                    anchors = []
                for a in anchors:
                    href = await get_attr(a, 'href')
                    if not href:
                        continue
                    full = absolute_url_keep_query(href)
                    if full in seen:
                        continue
                    seen.add(full)
                    urls.append(full)
                    if len(urls) >= max_fotos:
                        break
                if len(urls) >= max_fotos:
                    break
            if len(urls) >= max_fotos:
                break
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.9)")
            await page.wait_for_timeout(1200)
            scrolls += 1
        except Exception:
            break
    return urls[:max_fotos]

async def procesar_usuarios_en_modal_reacciones(page, reacciones_dict: Dict[str, dict], photo_url: str):
    try:
        container = await find_scroll_container(page)
        # Colocar el mouse en posición central del contenedor (simulación humana)
        try:
            # Si no hay contenedor aún, intenta apuntar al centro del modal; si tampoco, al centro de la ventana
            dialog = await page.query_selector('div[role="dialog"]')
            bb = None
            if container:
                bb = await container.bounding_box()
            if (not bb) and dialog:
                bb = await dialog.bounding_box()
            if bb:
                await page.mouse.move(bb['x'] + bb['width']/2, bb['y'] + bb['height']/2, steps=10)
            else:
                vw, vh = await page.evaluate('[window.innerWidth, window.innerHeight]')
                await page.mouse.move(vw/2, vh/2, steps=8)
        except Exception:
            pass

        async def process_cb(page_, _container) -> int:
            before = len(reacciones_dict)
            selectores = [
                'div[role="dialog"] a[href^="/"][role="link"]',
                'div[role="dialog"] a[role="link"]',
            ]
            enlaces = []
            for sel in selectores:
                try:
                    enlaces = await page_.query_selector_all(sel)
                except Exception:
                    enlaces = []
                if enlaces:
                    break
            for e in enlaces:
                try:
                    href = await get_attr(e, 'href')
                    if not href:
                        continue
                    url = normalize_profile_url(href)
                    if any(x in url for x in ["/groups/", "/pages/", "/events/"]):
                        continue
                    username = url.split('facebook.com/')[-1].strip('/')
                    if username in ("", "photo.php"):
                        continue
                    if url in reacciones_dict:
                        continue
                    nombre = await get_text(e)
                    foto = ''
                    try:
                        cont = await e.evaluate_handle('el => el.closest("div")')
                        img = await cont.query_selector('img, image') if cont else None
                        src = await get_attr(img, 'src') or await get_attr(img, 'xlink:href')
                        if src and not src.startswith('data:'):
                            foto = src
                    except Exception:
                        pass
                    item = build_user_item('facebook', url, nombre or username, foto or '')
                    item['post_url'] = normalize_post_url('facebook', photo_url)
                    reacciones_dict[url] = item
                except Exception:
                    continue
            return len(reacciones_dict) - before
        # Bucle de scroll dinámico dentro del modal (más profundo)
        scrolls = 0
        no_new = 0
        max_scrolls = 120
        no_new_threshold = 10
        bottom_stable_ticks = 0
        last_scroll_height = 0
        while scrolls < max_scrolls and no_new < no_new_threshold:
            try:
                added = await process_cb(page, container)
            except Exception:
                added = 0
            if added > 0:
                no_new = 0
                bottom_stable_ticks = 0
            else:
                no_new += 1

            # Re-evaluar contenedor periódicamente por si cambia la estructura interna
            if (scrolls % REACTIONS_REEVAL_EVERY == 0) or (container is None):
                try:
                    c2 = await find_scroll_container(page)
                    if c2:
                        container = c2
                except Exception:
                    pass

            # Verificar si estamos al fondo del contenedor (pero no cortar demasiado pronto)
            at_bottom = False
            try:
                at_bottom = await container.evaluate('el => (el.scrollTop + el.clientHeight) >= (el.scrollHeight - 120)') if container else False
            except Exception:
                at_bottom = False
            # Trackear scrollHeight para decidir estabilidad en fondo
            try:
                sh = await container.evaluate('el => el.scrollHeight') if container else 0
            except Exception:
                sh = 0
            if at_bottom:
                if sh and (sh <= last_scroll_height + REACTIONS_SCROLL_HEIGHT_EPS):
                    bottom_stable_ticks += 1
                else:
                    bottom_stable_ticks = 0
            else:
                bottom_stable_ticks = 0
            last_scroll_height = max(last_scroll_height, sh or 0)
            if at_bottom and no_new >= 3 and bottom_stable_ticks >= REACTIONS_BOTTOM_STABLE_TICKS:
                break

            # Scroll dinámico con variación
            delta = 720 + int(random.uniform(-160, 320))
            try:
                if container:
                    # Intento de focus antes de scroll
                    try:
                        await container.evaluate('el => el.focus()')
                    except Exception:
                        pass
                    await container.evaluate('(el, dy) => el.scrollBy({top: dy, left: 0, behavior: "auto"})', delta)
                else:
                    await page.evaluate('(dy) => window.scrollBy(0, dy)', delta)
            except Exception:
                pass

            # Espera adaptativa para que cargue contenido dinámico antes de declarar "no hay más"
            try:
                # Pequeña ventana de polls cortos para detectar aparición de nuevos elementos o cambio de altura
                polls = REACTIONS_STABILITY_RETRIES
                prev_count = len(reacciones_dict)
                prev_sh = last_scroll_height
                for _ in range(polls):
                    await page.wait_for_timeout(int(random.uniform(REACTIONS_SCROLL_WAIT_MIN, REACTIONS_SCROLL_WAIT_MAX)))
                    try:
                        added_poll = await process_cb(page, container)
                    except Exception:
                        added_poll = 0
                    if added_poll > 0:
                        no_new = 0
                        bottom_stable_ticks = 0
                        # actualizar altura si cambió
                        try:
                            prev_sh = await (container.evaluate('el => el.scrollHeight') if container else page.evaluate('() => document.body.scrollHeight'))
                        except Exception:
                            prev_sh = prev_sh
                        break
                    # si la altura de scroll crece, damos oportunidad a más carga
                    try:
                        cur_sh = await (container.evaluate('el => el.scrollHeight') if container else page.evaluate('() => document.body.scrollHeight'))
                    except Exception:
                        cur_sh = prev_sh
                    if cur_sh > (prev_sh + REACTIONS_SCROLL_HEIGHT_EPS):
                        prev_sh = cur_sh
                        bottom_stable_ticks = 0
                        continue
                # si nada nuevo y altura igual, caerá al siguiente ciclo incrementando no_new
            except Exception:
                pass
            scrolls += 1
    except Exception:
        return

async def abrir_y_scrapear_modal_reacciones(page, reacciones_dict: Dict[str, dict], photo_url: str):
    """Abre modal de reacciones buscando selectores específicos incluyendo 'Todas las reacciones:'"""
    # Política: por foto intentamos abrir SOLO UNA VEZ para evitar reabrir si el usuario lo cerró manualmente.
    attempted_click = False  # True en cuanto disparemos un click de apertura
    # Si el diálogo ya está abierto al entrar, procesar y salir
    try:
        existing = await page.query_selector('div[role="dialog"]')
        if existing:
            await procesar_usuarios_en_modal_reacciones(page, reacciones_dict, photo_url)
            try:
                close_btn = await page.query_selector('div[role="dialog"] [aria-label*="Cerrar"], div[role="dialog"] [aria-label*="Close"]')
                if close_btn:
                    await close_btn.click()
                    await page.wait_for_timeout(300)
            except Exception:
                pass
            return True
    except Exception:
        pass
    # Selector único (basado en HTML provisto): botón con div interno "Todas las reacciones:"
    sel = 'div[role="button"]:has(div.x9f619.x1ja2u2z.xzpqnlu.x1hyvwdk.x14bfe9o.xjm9jq1.x6ikm8r.x10wlt62.x10l6tqk.x1i1rx1s:has-text("Todas las reacciones:"))'
    try:
        elementos = await page.query_selector_all(sel)
        visibles = []
        for e in elementos:
            try:
                if await e.is_visible():
                    visibles.append(e)
            except Exception:
                continue
        if not visibles:
            logger.warning(f"{_ts()} fb.reactions no_button_found url={photo_url}")
            return False
        if attempted_click:
            return False
        elem = visibles[0]
        try:
            await elem.scroll_into_view_if_needed()
        except Exception:
            pass
        attempted_click = True
        opened = False
        for _ in range(2):
            try:
                await elem.click()
            except Exception:
                try:
                    elem = await elem.evaluate_handle('el => el.closest("[role=button]") || el')
                    await elem.click()
                except Exception:
                    pass
            try:
                await page.wait_for_selector('div[role="dialog"]', timeout=2000)
                opened = True
                break
            except Exception:
                await page.wait_for_timeout(300)
        if not opened:
            return False
        # Esperar contenido dentro del modal para evitar spinner
        try:
            await page.wait_for_selector('div[role="dialog"] a[role="link"]', timeout=4000)
        except Exception:
            try:
                close_btn = await page.query_selector('div[role="dialog"] [aria-label*="Cerrar"], div[role="dialog"] [aria-label*="Close"]')
                if close_btn:
                    await close_btn.click()
                    await page.wait_for_timeout(300)
            except Exception:
                pass
            return False
        await procesar_usuarios_en_modal_reacciones(page, reacciones_dict, photo_url)
        try:
            close_btn = await page.query_selector('div[role="dialog"] [aria-label*="Cerrar"], div[role="dialog"] [aria-label*="Close"]')
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(400)
        except Exception:
            pass
        logger.info(f"{_ts()} fb.reactions modal_done count={len(reacciones_dict)}")
        return True
    except Exception:
        pass

    logger.warning(f"{_ts()} fb.reactions no_modal_opened url={photo_url}")
    return False

async def abrir_y_scrapear_reacciones_en_comentarios(page, reacciones_dict: Dict[str, dict], photo_url: str):
    try:
        botones_sel = [
            'div[role="button"]:has-text("reacciones")',
            'div[role="button"][aria-label*="reacciones"]',
            'div[role="button"][aria-label*="reactions"]',
            'a[role="button"][aria-label*="reac"]',
        ]
        vistos = set()
        for sel in botones_sel:
            try:
                botones = await page.query_selector_all(sel)
            except Exception:
                botones = []
            for b in botones:
                try:
                    key = await b.inner_text() or await get_attr(b, 'aria-label') or ''
                    if key in vistos:
                        continue
                    vistos.add(key)
                    await b.click()
                    await page.wait_for_timeout(1200)
                    await procesar_usuarios_en_modal_reacciones(page, reacciones_dict, photo_url)
                    try:
                        close_btn = await page.query_selector('div[role="dialog"] [aria-label*="Cerrar"], div[role="dialog"] [aria-label*="Close"]')
                        if close_btn:
                            await close_btn.click()
                            await page.wait_for_timeout(400)
                    except Exception:
                        pass
                except Exception:
                    continue
    except Exception:
        return

async def scrap_reacciones_fotos(page, perfil_url: str, username: str, max_fotos: int = 5, incluir_comentarios: bool = False) -> List[dict]:
    if not await navegar_a_fotos(page, perfil_url):
        return []
    urls = await extraer_urls_fotos(page, max_fotos=max_fotos)
    reacciones: Dict[str, dict] = {}
    for i, photo_url in enumerate(urls, 1):
        try:
            # Usar una página fresca por foto para aislar fallos del renderer
            new_page = await page.context.new_page()
            await new_page.goto(photo_url, wait_until="domcontentloaded")
            await new_page.wait_for_timeout(600)
            opened = await abrir_y_scrapear_modal_reacciones(new_page, reacciones, photo_url)
            if not opened:
                # Handle: si no hay likes en el post principal, intentar reacciones de comentarios (si existen)
                await abrir_y_scrapear_reacciones_en_comentarios(new_page, reacciones, photo_url)
            if incluir_comentarios:
                await abrir_y_scrapear_reacciones_en_comentarios(new_page, reacciones, photo_url)
            if i % 3 == 0:
                await asyncio.sleep(2)
        except Exception:
            # Ignorar fallo de esta foto y continuar con la siguiente
            pass
        finally:
            try:
                await new_page.close()
            except Exception:
                pass
    return list(reacciones.values())

async def procesar_comentarios_en_modal_foto(page, comentarios_dict: Dict[str, dict], photo_url: str):
    try:
        selectores_articulo = [
            'div[role="dialog"] [role="article"][aria-label^="Comentario"]',
            'div[role="dialog"] [role="article"]',
            '[role="article"][aria-label^="Comentario"]',
            '[role="article"]',
        ]
        articulos = []
        for s in selectores_articulo:
            try:
                articulos = await page.query_selector_all(s)
            except Exception:
                articulos = []
            if articulos:
                break
        if not articulos:
            return
        for art in articulos:
            try:
                candidatos = []
                for sel in [
                    'a[role="link"][aria-hidden="false"]',
                    'a[role="link"]',
                    'a[href^="https://www.facebook.com/"]',
                    'a[href^="/"]',
                ]:
                    try:
                        cand = await art.query_selector_all(sel)
                    except Exception:
                        cand = []
                    if cand:
                        candidatos.extend(cand)
                elegido = None
                for e in candidatos:
                    try:
                        href = await get_attr(e, 'href')
                        if not href:
                            continue
                        if ('/photo/?' in href) or ('/photo.php' in href and 'fbid=' in href and 'comment_id' in href):
                            continue
                        url = normalize_profile_url(href)
                        if not url or 'facebook.com' not in url:
                            continue
                        if any(x in url for x in ["/groups/", "/pages/", "/events/"]):
                            continue
                        username = url.split('facebook.com/')[-1].strip('/')
                        if username in ("", "photo.php"):
                            continue
                        elegido = (e, url, username)
                        break
                    except Exception:
                        continue
                if not elegido:
                    continue
                e, url, username = elegido
                if url in comentarios_dict:
                    continue
                nombre = await get_text(e)
                foto = ''
                try:
                    cont = await e.evaluate_handle('el => el.closest("div")')
                    img = await cont.query_selector('img, image') if cont else None
                    src = await get_attr(img, 'src') or await get_attr(img, 'xlink:href')
                    if src and not src.startswith('data:'):
                        foto = src
                except Exception:
                    pass
                item = build_user_item('facebook', url, nombre or username, foto or '')
                item['post_url'] = normalize_post_url('facebook', photo_url)
                comentarios_dict[url] = item
            except Exception:
                continue
    except Exception:
        return

async def scrap_comentarios_fotos(page, perfil_url: str, username: str, max_fotos: int = 5) -> List[dict]:
    if not await navegar_a_fotos(page, perfil_url):
        return []
    urls = await extraer_urls_fotos(page, max_fotos=max_fotos)
    comentarios: Dict[str, dict] = {}
    for i, photo_url in enumerate(urls, 1):
        try:
            new_page = await page.context.new_page()
            await new_page.goto(photo_url, wait_until="domcontentloaded")
            await new_page.wait_for_timeout(600)

            # Asegurar modal si existe, sino trabajaremos con layout de página
            try:
                await new_page.wait_for_selector('div[role="dialog"]', timeout=1500)
            except Exception:
                pass

            # Encontrar contenedor scrollable: prioriza modal; si no, buscar mejor contenedor de comentarios en página
            container = await find_scroll_container(new_page)
            if not container:
                container = await _find_comments_container(new_page)

            # Bucle de carga y scroll de comentarios
            scrolls = 0
            no_new = 0
            max_scrolls = 60
            no_new_threshold = 10
            while scrolls < max_scrolls and no_new < no_new_threshold:
                # Intentar expandir comentarios/respuestas
                try:
                    botones = [
                        'div[role="button"]:has-text("Ver más comentarios")',
                        'div[role="button"]:has-text("View more comments")',
                        'div[role="button"]:has-text("Cargar más comentarios")',
                        'div[role="button"][aria-label*="comentarios"]',
                        'span:has-text("Ver más comentarios")',
                        'span:has-text("Mostrar más comentarios")',
                        'span:has-text("View more comments")',
                        'div[role="button"]:has-text("Ver más")',
                        'div[role="button"]:has-text("Mostrar más")',
                        'div[role="button"]:has-text("Ver respuestas")',
                        'div[role="button"]:has-text("Mostrar respuestas")',
                    ]
                    clicked_any = False
                    for bsel in botones:
                        b = await new_page.query_selector(bsel)
                        if b:
                            try:
                                role_btn = await b.evaluate_handle('el => el.closest("[role=\\"button\\"]") || el')
                                await role_btn.click()
                            except Exception:
                                await b.click()
                            clicked_any = True
                            await new_page.wait_for_timeout(500)
                            break
                    if clicked_any:
                        await new_page.wait_for_timeout(400)
                except Exception:
                    pass

                before = len(comentarios)
                await procesar_comentarios_en_modal_foto(new_page, comentarios, photo_url)
                added = len(comentarios) - before
                if added > 0:
                    no_new = 0
                else:
                    no_new += 1

                # Re-evaluar contenedor de scroll periódicamente
                if (scrolls % 8 == 0) or (container is None):
                    try:
                        c2 = await find_scroll_container(new_page)
                        if c2:
                            container = c2
                    except Exception:
                        pass

                # Scroll dentro del contenedor
                try:
                    delta = 720 + int(random.uniform(-160, 320))
                    if container:
                        try:
                            await container.evaluate('el => el.focus()')
                        except Exception:
                            pass
                        await container.evaluate('(el, dy) => el.scrollBy({top: dy, left: 0, behavior: "auto"})', delta)
                    else:
                        await new_page.evaluate('(dy) => window.scrollBy(0, dy)', delta)
                except Exception:
                    pass

                try:
                    await new_page.wait_for_timeout(650 + int(random.uniform(-250, 350)))
                except Exception:
                    pass
                scrolls += 1

            if i % 3 == 0:
                await asyncio.sleep(2)
        except Exception:
            pass
        finally:
            try:
                await new_page.close()
            except Exception:
                pass
    return list(comentarios.values())
