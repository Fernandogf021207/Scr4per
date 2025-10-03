import time
import logging
from src.utils.dom import find_scroll_container, scroll_element, scroll_window
from src.utils.list_parser import build_user_item
from src.utils.url import normalize_input_url
from src.scrapers.resource_blocking import start_list_blocking
from src.scrapers.scrolling import scroll_loop
from src.scrapers.selector_registry import get_selectors, registry_version
from src.scrapers.errors import classify_page_state, ErrorCode

logger = logging.getLogger(__name__)

def _ts() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

async def procesar_usuarios_en_modal(page, usuarios_dict, usuario_principal, tipo_lista):
    try:
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
                    elementos_validos = []
                    for elemento in elementos:
                        try:
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
        for elemento in elementos_usuarios:
            try:
                enlace = await elemento.query_selector('a[role="link"]') or elemento
                if not enlace:
                    continue
                href = await enlace.get_attribute("href")
                if not href or not href.startswith('/'):
                    continue
                url_usuario_abs = f"https://www.instagram.com{href}"
                texto_elemento = await elemento.inner_text()
                lineas = texto_elemento.strip().split('\n')
                nombre_completo_usuario = lineas[0] if lineas and lineas[0] else None
                img_element = await elemento.query_selector('img')
                url_foto = await img_element.get_attribute("src") if img_element else ""
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

async def extraer_usuarios_instagram(page, tipo_lista="seguidores", usuario_principal=""):
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

    # Estado para doble confirmación de bottom
    bottom_state = {
        'candidate': False,
        'candidate_iter': 0,
        'candidate_total': 0,
        'candidate_sh': 0,
    }
    # Parámetros heurísticos (se pueden mover a config posteriormente)
    EARLY_BOTTOM_MIN_SCROLLS = 7   # exigir al menos este número de scrolls antes de aceptar bottom si total aún bajo
    EARLY_BOTTOM_MIN_TOTAL = 80    # si total < este umbral, pedir doble confirmación
    BOTTOM_MARGIN_CONTAINER = 150
    BOTTOM_MARGIN_WINDOW = 200

    async def bottom_check() -> bool:
        if iter_state['count'] < 3:
            return False
        try:
            if container:
                is_bottom, metrics = await page.evaluate("""
                    el => { const st = el.scrollTop; const ch = el.clientHeight; const sh = el.scrollHeight; return [ (st + ch) >= (sh - %d), {st, ch, sh} ]; }
                """ % BOTTOM_MARGIN_CONTAINER, container)
            else:
                is_bottom, metrics = await page.evaluate("""
                    () => { const st = window.pageYOffset || document.documentElement.scrollTop; const ch = window.innerHeight; const sh = document.documentElement.scrollHeight || document.body.scrollHeight; return [ (st + ch) >= (sh - %d), {st, ch, sh} ]; }
                """ % BOTTOM_MARGIN_WINDOW)
            if not is_bottom:
                # Reset estado si el scroll volvió a crecer
                if bottom_state['candidate']:
                    bottom_state['candidate'] = False
                return False
            # Tenemos un candidato a bottom
            total_actual = len(usuarios_dict)
            logger.info(f"{_ts()} instagram.list bottom_candidate iter={iter_state['count']} metrics={metrics} total={total_actual}")
            # Condiciones para exigir doble confirmación
            needs_double = (iter_state['count'] < EARLY_BOTTOM_MIN_SCROLLS) or (total_actual < EARLY_BOTTOM_MIN_TOTAL)
            if not needs_double:
                # Ya pasamos umbrales, aceptar bottom directamente
                return True
            # Primera vez que vemos bottom en condiciones tempranas
            if not bottom_state['candidate']:
                bottom_state.update({
                    'candidate': True,
                    'candidate_iter': iter_state['count'],
                    'candidate_total': total_actual,
                    'candidate_sh': metrics.get('sh', 0),
                })
                logger.info(f"{_ts()} instagram.list bottom_defer first_candidate iter={iter_state['count']} total={total_actual} sh={metrics.get('sh')} min_scrolls={EARLY_BOTTOM_MIN_SCROLLS} min_total={EARLY_BOTTOM_MIN_TOTAL}")
                return False
            # Segunda detección: verificar si nada cambió (altura y total estables)
            stable_height = metrics.get('sh', 0) == bottom_state['candidate_sh']
            stable_total = total_actual == bottom_state['candidate_total']
            if stable_height and stable_total:
                logger.info(f"{_ts()} instagram.list bottom_confirmed iter={iter_state['count']} total={total_actual} stable_height={stable_height} stable_total={stable_total}")
                return True
            # Hubo crecimiento: refrescar candidato y continuar
            bottom_state.update({
                'candidate_iter': iter_state['count'],
                'candidate_total': total_actual,
                'candidate_sh': metrics.get('sh', 0),
            })
            logger.info(f"{_ts()} instagram.list bottom_retry growth_detected iter={iter_state['count']} total={total_actual} sh={metrics.get('sh')}")
            return False
        except Exception:
            return False

    stats = await scroll_loop(
        process_once=process_once,
        do_scroll=do_scroll,
        max_scrolls=40,
        pause_ms=900,
        stagnation_limit=6,
        empty_limit=2,
        bottom_check=bottom_check,
        adaptive=True,
        adaptive_decay_threshold=0.30,
        log_prefix=f"instagram.list type={tipo_lista}",
        timeout_ms=35000,
    )

    await blocker.stop()
    if stats['reason'] == 'bottom' and stats.get('iterations', 0) <= 4 and len(usuarios_dict) < 30:
        logger.warning(f"{_ts()} instagram.list suspicion=EARLY_BOTTOM type={tipo_lista} total={len(usuarios_dict)} iter={stats.get('iterations')} reason={stats['reason']}")
    if stats['reason'] == 'timeout':
        logger.warning(f"{_ts()} instagram.list error.code=TIMEOUT type={tipo_lista} duration_ms={stats['duration_ms']}")
    if len(usuarios_dict) == 0:
        logger.warning(f"{_ts()} instagram.list error.code=EMPTY_LIST type={tipo_lista} reason={stats['reason']}")
    logger.info(f"{_ts()} instagram.list end type={tipo_lista} total={len(usuarios_dict)} duration_ms={stats['duration_ms']} reason={stats['reason']} scrolls={stats['iterations']} started_at={(t0):.0f}")
    return list(usuarios_dict.values())

async def navegar_a_lista_instagram(page, perfil_url, tipo_lista="followers"):
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
            try:
                body_text = await page.inner_text('body')
            except Exception:
                body_text = ''
            state = classify_page_state(platform, body_text) or ErrorCode.SELECTOR_MISS
            logger.warning(f"{_ts()} instagram.nav link_not_found list={nombre_lista} code={state.value}")
            return False
        logger.info(f"{_ts()} instagram.nav clicking list={nombre_lista}")
        await enlace_lista.click()
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
