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

async def navegar_a_lista(page, perfil_url: str, lista: str) -> bool:
    suffix = {
        'friends_all': 'friends_all',
        'followers': 'followers',
        'followed': 'following',
    }.get(lista, lista)
    perfil_url = normalize_input_url('facebook', perfil_url)
    base = perfil_url.rstrip('/')
    target = f"{base}/{suffix}/"
    logger.info(f"{_ts()} facebook.nav start list={lista}")
    start = time.time()
    try:
        await page.goto(target, timeout=15_000)
        try:
            await page.wait_for_selector('div[role="main"]', timeout=2500)
        except Exception:
            pass
        logger.info(f"{_ts()} facebook.nav ok list={lista} duration_ms={(time.time()-start)*1000:.0f}")
        return True
    except Exception as e:
        logger.error(f"{_ts()} facebook.nav fail list={lista} error={e}")
        return False

async def procesar_tarjetas_usuario(page, usuarios: Dict[str, dict], usuario_principal: str):
    selectores = [
        'div[role="main"] a[href^="/profile.php?id="]',
        'div[role="main"] a[href^="/"][href*="?sk="]',
        'div[role="main"] a[href^="/"]:not([href*="photo"])',
        'div[role="main"] div:has(a[href^="/profile.php"], a[href^="/"])',
    ]
    for sel in selectores:
        try:
            links = await page.query_selector_all(sel)
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

async def extraer_usuarios_listado(page, tipo_lista: str, usuario_principal: str) -> List[dict]:
    usuarios: Dict[str, dict] = {}
    cfg = FACEBOOK_CONFIG.get('scroll', {})
    max_scrolls_cfg = int(cfg.get('max_scrolls', 60))
    max_scrolls = min(max_scrolls_cfg, 40)
    blocker = await start_list_blocking(page, 'facebook', phase=f'list.{tipo_lista}')
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
        try:
            return await page.evaluate("() => (window.innerHeight + window.pageYOffset) >= (document.body.scrollHeight - 800)")
        except Exception:
            return False
    stats = await scroll_loop(
        process_once=process_once,
        do_scroll=do_scroll,
        max_scrolls=max_scrolls,
        pause_ms=900,
        stagnation_limit=3,
        empty_limit=2,
        bottom_check=bottom_check,
        adaptive=True,
        adaptive_decay_threshold=0.35,
        log_prefix=f"facebook.list type={tipo_lista}",
        timeout_ms=30000,
    )
    await blocker.stop()
    if stats['reason'] == 'timeout':
        logger.warning(f"{_ts()} facebook.list error.code=TIMEOUT type={tipo_lista} duration_ms={stats['duration_ms']}")
    if len(usuarios) == 0:
        logger.warning(f"{_ts()} facebook.list error.code=EMPTY_LIST type={tipo_lista} reason={stats['reason']}")
    logger.info(f"{_ts()} facebook.list done type={tipo_lista} total={len(usuarios)} duration_ms={stats['duration_ms']} reason={stats['reason']}")
    return list(usuarios.values())

async def extraer_amigos_facebook(page, usuario_principal: str) -> List[dict]:
    try:
        for _ in range(50):
            try:
                await page.mouse.wheel(0, 3000)
            except Exception:
                try:
                    await page.evaluate("window.scrollBy(0, 3000)")
                except Exception:
                    pass
            await asyncio.sleep(2)
    except Exception:
        pass
    amigos_dict: Dict[str, dict] = {}
    try:
        tarjetas = await page.query_selector_all('div[role="main"] div:has(a[tabindex="0"])')
    except Exception:
        tarjetas = []
    invalid_segments = [
        "/followers", "/following", "/friends", "/videos", "/photo", "/photos",
        "/tv", "/events", "/past_events", "/likes", "/likes_all",
        "/music", "/sports", "/map", "/movies", "/pages",
        "/groups", "/watch", "/reel", "/story", "/video_tv_shows_watch",
        "/games", "/reviews_given", "/reviews_written", "/video_movies_watch",
        "/profile_songs", "/places_recent", "/posts/"
    ]
    for tarjeta in tarjetas:
        try:
            a_nombre = await tarjeta.query_selector('a[tabindex="0"]')
            a_img = await tarjeta.query_selector('a[tabindex="-1"] img')
            nombre = (await get_text(a_nombre)) or "Sin nombre"
            perfil = await get_attr(a_nombre, "href") if a_nombre else None
            imagen = await get_attr(a_img, "src") if a_img else None
            if not perfil:
                continue
            perfil_limpio = normalize_profile_url(perfil)
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
            amigos_dict[perfil_limpio] = build_user_item('facebook', perfil_limpio, nombre, imagen or '')
        except Exception:
            continue
    res = list(amigos_dict.values())
    if len(res) == 0:
        logger.warning(f"{_ts()} facebook.friends_all error.code=EMPTY_LIST")
    return res

async def scrap_friends_all(page, perfil_url: str, username: str) -> List[dict]:
    if not await navegar_a_lista(page, perfil_url, 'friends_all'):
        return []
    return await extraer_amigos_facebook(page, username)

async def scrap_followers(page, perfil_url: str, username: str) -> List[dict]:
    if not await navegar_a_lista(page, perfil_url, 'followers'):
        return []
    return await extraer_usuarios_listado(page, 'followers', username)

async def scrap_followed(page, perfil_url: str, username: str) -> List[dict]:
    if not await navegar_a_lista(page, perfil_url, 'followed'):
        return []
    return await extraer_usuarios_listado(page, 'followed', username)

async def scrap_lista_facebook(page, perfil_url: str, tipo: str) -> List[dict]:
    perfil_url = normalize_input_url('facebook', perfil_url)
    if tipo == 'friends_all':
        return await scrap_friends_all(page, perfil_url, tipo)
    if tipo == 'followers':
        return await scrap_followers(page, perfil_url, tipo)
    if tipo == 'followed':
        return await scrap_followed(page, perfil_url, tipo)
    return []
