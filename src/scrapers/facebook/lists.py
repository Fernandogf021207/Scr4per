import time
import logging
import asyncio
from typing import Dict, List
from src.scrapers.facebook.config import FACEBOOK_CONFIG
from src.scrapers.facebook.utils import normalize_profile_url, get_text, get_attr
from src.scrapers.scrolling import scroll_loop
from src.utils.list_parser import build_user_item
from src.utils.url import normalize_input_url
from src.scrapers.resource_blocking import start_list_blocking

logger = logging.getLogger(__name__)

def _ts() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

async def navegar_a_lista(page, perfil_url: str, lista: str):
    # Map logical list types to actual Facebook paths
    suffix = {
        'friends_all': 'friends',     # real route is /friends
        'followers': 'followers',
        'followed': 'following',      # followed == following
    }.get(lista, lista)
    perfil_url = normalize_input_url('facebook', perfil_url)
    base = perfil_url.rstrip('/')
    target = f"{base}/{suffix}/"
    logger.info(f"{_ts()} facebook.nav start list={lista} url={target}")
    start = time.time()
    for attempt in (1, 2):
        try:
            await page.goto(target, timeout=20_000, wait_until="domcontentloaded")
            try:
                await page.wait_for_selector('div[role="main"]', timeout=3000)
            except Exception:
                pass
            # Check if redirected to login
            current_url = page.url
            if '/login' in current_url or 'login_attempt' in current_url:
                logger.error(f"{_ts()} facebook.nav redirected_to_login list={lista} url={current_url}")
                return None
            logger.info(f"{_ts()} facebook.nav ok list={lista} duration_ms={(time.time()-start)*1000:.0f} attempt={attempt}")
            return page
        except Exception as e:
            msg = str(e)
            logger.error(f"{_ts()} facebook.nav fail list={lista} error={e} attempt={attempt}")
            # If page crashed, try reopening a fresh page once
            if 'Page crashed' in msg or 'Target closed' in msg:
                try:
                    ctx = page.context
                    try:
                        await page.close()
                    except Exception:
                        pass
                    page = await ctx.new_page()
                    continue  # retry with new page
                except Exception:
                    break
            break
    return None

async def procesar_tarjetas_usuario(page, usuarios: Dict[str, dict], usuario_principal: str):
    # Selectores más amplios para capturar diferentes estructuras de lista
    selectores = [
        'div[role="main"] a[href^="/profile.php?id="]',
        'div[role="main"] a[href^="/"][href*="?sk="]',
        'div[role="main"] a[href^="/"]:not([href*="photo"])',
        'div[role="main"] div:has(a[href^="/profile.php"], a[href^="/"])',
        # Additional: followers/following may use different containers
        'div[role="main"] a[role="link"]',
        'div[role="main"] span a[href^="/"]',
        'div[role="article"] a[href^="/"]',
    ]
    total_links_found = 0
    for sel in selectores:
        try:
            links = await page.query_selector_all(sel)
            total_links_found += len(links)
        except Exception:
            links = []
        for a in links:
            try:
                href = await get_attr(a, 'href')
                if not href:
                    continue
                url = normalize_profile_url(href)
                if not url:
                    continue
                invalid_paths = [
                    'photo', 'groups', 'events', 'pages', 'watch', 'marketplace', 'reel',
                    'reviews_given', 'reviews_written', 'video_movies_watch', 'profile_songs',
                    'places_recent', 'posts/'
                ]
                if any(f"/{pat}" in url for pat in invalid_paths):
                    continue
                slug = url.split('facebook.com/')[-1].strip('/')
                if slug in ('', 'friends', 'followers', 'following'):
                    continue
                if slug == usuario_principal:
                    continue
                if url in usuarios:
                    continue
                nombre = await get_text(a) or ''
                if not nombre:
                    try:
                        cont = await a.evaluate_handle('el => el.closest("div")')
                        nombre_el = await cont.query_selector('span, strong, h2, h3') if cont else None
                        nombre = await get_text(nombre_el)
                    except Exception:
                        nombre = ''
                foto = ''
                try:
                    cont = await a.evaluate_handle('el => el.closest("div")')
                    img = await cont.query_selector('img, image') if cont else None
                    src = await get_attr(img, 'src') or await get_attr(img, 'xlink:href')
                    if src and not src.startswith('data:'):
                        foto = src
                except Exception:
                    pass
                username = slug.split('?')[0]
                usuarios[url] = build_user_item('facebook', url, nombre or username, foto or '')
            except Exception:
                continue
    if total_links_found == 0:
        logger.warning(f"{_ts()} facebook.list no_links_found user={usuario_principal}")
        # Debug: save screenshot and HTML for manual inspection
        try:
            import os
            debug_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'logs', 'debug_fb')
            os.makedirs(debug_dir, exist_ok=True)
            screenshot_path = os.path.join(debug_dir, f'empty_{usuario_principal}_{int(time.time())}.png')
            await page.screenshot(path=screenshot_path)
            html_path = screenshot_path.replace('.png', '.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(await page.content())
            logger.info(f"{_ts()} facebook.list debug_saved screenshot={screenshot_path}")
        except Exception as dbg_err:
            logger.warning(f"{_ts()} facebook.list debug_save_error err={dbg_err}")

async def extraer_usuarios_listado(page, tipo_lista: str, usuario_principal: str) -> List[dict]:
    usuarios: Dict[str, dict] = {}
    cfg = FACEBOOK_CONFIG.get('scroll', {})
    max_scrolls_cfg = int(cfg.get('max_scrolls', 100))
    max_scrolls = min(max_scrolls_cfg, 60)
    blocker = await start_list_blocking(page, 'facebook', phase=f'list.{tipo_lista}')
    
    # Debug: capture page state on first iteration
    try:
        main_content = await page.query_selector('div[role="main"]')
        if main_content:
            html_sample = await main_content.inner_html()
            logger.info(f"{_ts()} facebook.list debug type={tipo_lista} main_html_length={len(html_sample)} first_200_chars={html_sample[:200]}")
        else:
            logger.warning(f"{_ts()} facebook.list debug type={tipo_lista} NO_MAIN_DIV url={page.url}")
    except Exception as dbg_err:
        logger.warning(f"{_ts()} facebook.list debug_error type={tipo_lista} err={dbg_err}")
    
    iter_state = {'count': 0}
    # Heurísticas anti early-bottom para followers/followed
    MIN_SCROLLS_FOR_DIRECT_BOTTOM = 8
    MIN_TOTAL_FOR_DIRECT_BOTTOM = 120
    BOTTOM_MARGIN = 700
    bottom_state = {'candidate': False, 'candidate_iter': 0, 'candidate_total': 0, 'candidate_sh': 0}
    async def process_once() -> int:
        before = len(usuarios)
        await procesar_tarjetas_usuario(page, usuarios, usuario_principal)
        return len(usuarios) - before
    async def do_scroll():
        try:
            await page.evaluate("window.scrollBy(0, document.documentElement.clientHeight * 0.7)")
        except Exception:
            pass
    async def bottom_check() -> bool:
        if iter_state['count'] < 2:
            return False
        try:
            is_bottom, metrics = await page.evaluate(
                f"() => [ (window.innerHeight + window.pageYOffset) >= (document.body.scrollHeight - {BOTTOM_MARGIN}), {{sh: document.body.scrollHeight}} ]"
            )
        except Exception:
            return False
        if not is_bottom:
            if bottom_state['candidate']:
                bottom_state['candidate'] = False
            return False
        total_actual = len(usuarios)
        needs_double = (iter_state['count'] < MIN_SCROLLS_FOR_DIRECT_BOTTOM) or (total_actual < MIN_TOTAL_FOR_DIRECT_BOTTOM)
        if not needs_double:
            return True
        sh = metrics.get('sh', 0)
        if not bottom_state['candidate']:
            bottom_state.update({'candidate': True, 'candidate_iter': iter_state['count'], 'candidate_total': total_actual, 'candidate_sh': sh})
            logger.info(f"{_ts()} facebook.list bottom_defer type={tipo_lista} iter={iter_state['count']} total={total_actual} sh={sh}")
            return False
        stable_total = total_actual == bottom_state['candidate_total']
        stable_sh = sh == bottom_state['candidate_sh']
        if stable_total and stable_sh:
            logger.info(f"{_ts()} facebook.list bottom_confirmed type={tipo_lista} iter={iter_state['count']} total={total_actual}")
            return True
        bottom_state.update({'candidate_iter': iter_state['count'], 'candidate_total': total_actual, 'candidate_sh': sh})
        logger.info(f"{_ts()} facebook.list bottom_retry type={tipo_lista} iter={iter_state['count']} total={total_actual} sh={sh}")
        return False
    stats = await scroll_loop(
        process_once=process_once,
        do_scroll=do_scroll,
        max_scrolls=max_scrolls,
        pause_ms=900,
        stagnation_limit=4,
        empty_limit=2,
        bottom_check=bottom_check,
        adaptive=False,
        adaptive_decay_threshold=0.35,
        log_prefix=f"facebook.list type={tipo_lista}",
        timeout_ms=30000,
    )
    try:
        await blocker.stop()
    except Exception:
        pass
    if stats['reason'] == 'timeout':
        logger.warning(f"{_ts()} facebook.list error.code=TIMEOUT type={tipo_lista} duration_ms={stats['duration_ms']}")
    if len(usuarios) == 0:
        logger.warning(f"{_ts()} facebook.list error.code=EMPTY_LIST type={tipo_lista} reason={stats['reason']}")
    logger.info(f"{_ts()} facebook.list done type={tipo_lista} total={len(usuarios)} duration_ms={stats['duration_ms']} reason={stats['reason']}")
    return list(usuarios.values())

async def extraer_amigos_facebook(page, usuario_principal: str) -> List[dict]:
    """Extrae amigos reutilizando scroll_loop para evitar esperas fijas largas.
    Early-exit por: empty, stagnation, bottom, timeout.
    Timeout fijo por ahora: 30s (alineado a otras listas).
    """
    logger.info(f"{_ts()} facebook.list start type=friends_all")
    amigos_dict: Dict[str, dict] = {}
    invalid_segments = [
        "/followers", "/following", "/friends", "/videos", "/photo", "/photos",
        "/tv", "/events", "/past_events", "/likes", "/likes_all",
        "/music", "/sports", "/map", "/movies", "/pages",
        "/groups", "/watch", "/reel", "/story", "/video_tv_shows_watch",
        "/games", "/reviews_given", "/reviews_written", "/video_movies_watch",
        "/profile_songs", "/places_recent", "/posts/"
    ]

    blocker = await start_list_blocking(page, 'facebook', phase='list.friends_all')
    iter_state = {'count': 0, 'last_sh': 0}

    # Heurísticas anti early-exit similares a Instagram
    MIN_SCROLLS_FOR_DIRECT_BOTTOM = 10       # exigir al menos 10 scrolls antes de aceptar bottom directo
    MIN_TOTAL_FOR_DIRECT_BOTTOM = 180        # si total < 180 requerir doble confirmación
    BOTTOM_MARGIN = 700                      # margen px para considerar near-bottom
    MAX_SCROLLS_FRIENDS = 80                 # permitir más iteraciones para listas grandes (~1000)
    TIMEOUT_MS_FRIENDS = 120000               # más tiempo para cargar grandes volúmenes
    DOUBLE_CONFIRM_STABLE_SH = True          # requerir scrollHeight estable
    bottom_state = {
        'candidate': False,
        'candidate_iter': 0,
        'candidate_total': 0,
        'candidate_sh': 0,
    }

    async def process_once() -> int:
        before = len(amigos_dict)
        try:
            tarjetas = await page.query_selector_all('div[role="main"] div:has(a[tabindex="0"])')
        except Exception:
            tarjetas = []
        for tarjeta in tarjetas:
            try:
                a_nombre = await tarjeta.query_selector('a[tabindex="0"]')
                a_img = await tarjeta.query_selector('a[tabindex="-1"] img')
                nombre = (await get_text(a_nombre)) or ""
                perfil = await get_attr(a_nombre, "href") if a_nombre else None
                imagen = await get_attr(a_img, "src") if a_img else None
                if not perfil:
                    continue
                perfil_limpio = normalize_profile_url(perfil)
                if not perfil_limpio:
                    continue
                low = (nombre or "").lower().strip()
                if low.startswith(("1 amigo", "2 amigos", "3 amigos")):
                    continue
                if any(seg in perfil_limpio for seg in invalid_segments):
                    continue
                slug = perfil_limpio.split('facebook.com/')[-1].strip('/')
                if slug == usuario_principal:
                    continue
                if perfil_limpio in amigos_dict:
                    continue
                username = slug.split('?')[0]
                amigos_dict[perfil_limpio] = build_user_item('facebook', perfil_limpio, nombre or username, imagen or '')
            except Exception:
                continue
        iter_state['count'] += 1
        return len(amigos_dict) - before

    async def do_scroll():
        try:
            await page.evaluate("window.scrollBy(0, document.documentElement.clientHeight * 0.8)")
        except Exception:
            try:
                await page.mouse.wheel(0, 2500)
            except Exception:
                pass

    async def bottom_check() -> bool:
        # Evitar bottom muy temprano
        if iter_state['count'] < 3:
            return False
        try:
            is_bottom, metrics = await page.evaluate(f"() => [ (window.innerHeight + window.pageYOffset) >= (document.body.scrollHeight - {BOTTOM_MARGIN}), {{sh: document.body.scrollHeight, y: window.pageYOffset, ih: window.innerHeight}} ]")
        except Exception:
            return False
        if not is_bottom:
            if bottom_state['candidate']:
                bottom_state['candidate'] = False
            return False
        total_actual = len(amigos_dict)
        sh = metrics.get('sh', 0)
        logger.info(f"{_ts()} facebook.list bottom_candidate type=friends_all iter={iter_state['count']} total={total_actual} sh={sh} metrics={metrics}")
        needs_double = (iter_state['count'] < MIN_SCROLLS_FOR_DIRECT_BOTTOM) or (total_actual < MIN_TOTAL_FOR_DIRECT_BOTTOM)
        if not needs_double:
            return True
        if not bottom_state['candidate']:
            bottom_state.update({'candidate': True, 'candidate_iter': iter_state['count'], 'candidate_total': total_actual, 'candidate_sh': sh})
            logger.info(f"{_ts()} facebook.list bottom_defer first_candidate iter={iter_state['count']} total={total_actual} sh={sh} min_scrolls={MIN_SCROLLS_FOR_DIRECT_BOTTOM} min_total={MIN_TOTAL_FOR_DIRECT_BOTTOM}")
            return False
        # Segunda detección: verificar estabilidad
        stable_total = total_actual == bottom_state['candidate_total']
        stable_sh = sh == bottom_state['candidate_sh'] if DOUBLE_CONFIRM_STABLE_SH else True
        if stable_total and stable_sh:
            logger.info(f"{_ts()} facebook.list bottom_confirmed iter={iter_state['count']} total={total_actual} stable_total={stable_total} stable_sh={stable_sh}")
            return True
        # Hubo crecimiento -> rearmar candidato
        bottom_state.update({'candidate_iter': iter_state['count'], 'candidate_total': total_actual, 'candidate_sh': sh})
        logger.info(f"{_ts()} facebook.list bottom_retry growth_detected iter={iter_state['count']} total={total_actual} sh={sh}")
        return False

    stats = await scroll_loop(
        process_once=process_once,
        do_scroll=do_scroll,
        max_scrolls=MAX_SCROLLS_FRIENDS,
        pause_ms=900,
        stagnation_limit=4,
        empty_limit=2,
        bottom_check=bottom_check,
        adaptive=False,  # no reducir max scrolls para listas grandes
        adaptive_decay_threshold=0.35,
        log_prefix="facebook.list type=friends_all",
        timeout_ms=TIMEOUT_MS_FRIENDS,
    )
    try:
        await blocker.stop()
    except Exception:
        pass

    if stats['reason'] == 'timeout':
        logger.warning(f"{_ts()} facebook.list error.code=TIMEOUT type=friends_all duration_ms={stats['duration_ms']}")
    if len(amigos_dict) == 0:
        logger.warning(f"{_ts()} facebook.friends_all error.code=EMPTY_LIST reason={stats['reason']}")
    logger.info(f"{_ts()} facebook.list done type=friends_all total={len(amigos_dict)} duration_ms={stats['duration_ms']} reason={stats['reason']} scrolls={stats.get('iterations')}" )
    return list(amigos_dict.values())

async def scrap_friends_all(page, perfil_url: str, username: str) -> List[dict]:
    nav_page = await navegar_a_lista(page, perfil_url, 'friends_all')
    if not nav_page:
        return []
    return await extraer_amigos_facebook(nav_page, username)

async def scrap_followers(page, perfil_url: str, username: str) -> List[dict]:
    nav_page = await navegar_a_lista(page, perfil_url, 'followers')
    if not nav_page:
        return []
    return await extraer_usuarios_listado(nav_page, 'followers', username)

async def scrap_followed(page, perfil_url: str, username: str) -> List[dict]:
    nav_page = await navegar_a_lista(page, perfil_url, 'followed')
    if not nav_page:
        return []
    return await extraer_usuarios_listado(nav_page, 'followed', username)

async def scrap_lista_facebook(page, perfil_url: str, tipo: str) -> List[dict]:
    perfil_url = normalize_input_url('facebook', perfil_url)
    if tipo == 'friends_all':
        return await scrap_friends_all(page, perfil_url, tipo)
    if tipo == 'followers':
        return await scrap_followers(page, perfil_url, tipo)
    if tipo == 'followed':
        return await scrap_followed(page, perfil_url, tipo)
    return []
