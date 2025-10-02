import time
import logging
from src.utils.url import normalize_input_url
from src.utils.dom import scroll_window
from src.utils.list_parser import build_user_item
from src.utils.url import normalize_post_url
from src.scrapers.resource_blocking import start_list_blocking
from src.scrapers.scrolling import scroll_loop
from src.scrapers.selector_registry import get_selectors, registry_version
from src.scrapers.errors import classify_page_state, ErrorCode
from .utils import procesar_usuarios_en_pagina

logger = logging.getLogger(__name__)

def _ts():
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

async def extraer_usuarios_lista(page, tipo_lista="seguidores", rid: str | None = None):
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.list start type={tipo_lista}{ridp}")
    usuarios_dict = {}
    blocker = await start_list_blocking(page, 'x', phase=f'list.{tipo_lista}')
    async def process_once() -> int:
        before = len(usuarios_dict)
        await procesar_usuarios_en_pagina(page, usuarios_dict)
        return len(usuarios_dict) - before
    async def do_scroll():
        try:
            await scroll_window(page, 0)
        except Exception:
            pass
    async def bottom_check() -> bool:
        try:
            return await page.evaluate("() => (window.innerHeight + window.pageYOffset) >= (document.body.scrollHeight - 1000)")
        except Exception:
            return False
    stats = await scroll_loop(
        process_once=process_once,
        do_scroll=do_scroll,
        max_scrolls=40,
        pause_ms=1000,
        stagnation_limit=4,
        empty_limit=2,
        bottom_check=bottom_check,
        adaptive=True,
        adaptive_decay_threshold=0.35,
        log_prefix=f"x.list type={tipo_lista}{ridp}",
        timeout_ms=32000,
    )
    await blocker.stop()
    if stats['reason'] == 'timeout':
        logger.warning(f"{_ts()} x.list error.code=TIMEOUT type={tipo_lista} duration_ms={stats['duration_ms']}{ridp}")
    if len(usuarios_dict) == 0:
        logger.warning(f"{_ts()} x.list error.code=EMPTY_LIST type={tipo_lista} reason={stats['reason']}{ridp}")
    logger.info(f"{_ts()} x.list end type={tipo_lista} total={len(usuarios_dict)} duration_ms={stats['duration_ms']} reason={stats['reason']} scrolls={stats['iterations']}{ridp}")
    return list(usuarios_dict.values())

async def scrap_seguidores(page, perfil_url, username, rid: str | None = None):
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.followers start{ridp} registry_ver={registry_version('x')}")
    try:
        perfil_url = normalize_input_url('x', perfil_url)
        followers_url = f"{perfil_url.rstrip('/')}/followers"
        await page.goto(followers_url, timeout=12_000)
        await page.wait_for_timeout(1200)
        selectors_items = get_selectors('x', 'lists.list_item')
        found_any = False
        for sel in selectors_items:
            try:
                el = await page.query_selector(sel)
                if el:
                    found_any = True; break
            except Exception: continue
        if not found_any:
            try:
                body_text = await page.inner_text('body')
            except Exception:
                body_text = ''
            code = classify_page_state('x', body_text) or ErrorCode.SELECTOR_MISS
            logger.warning(f"{_ts()} x.followers no_items code={code.value}{ridp}")
        seguidores = await extraer_usuarios_lista(page, "seguidores", rid=rid)
        if len(seguidores) == 0:
            logger.warning(f"{_ts()} x.followers error.code=EMPTY_LIST{ridp}")
        logger.info(f"{_ts()} x.followers count={len(seguidores)}{ridp}")
        return seguidores
    except Exception as e:
        logger.warning(f"{_ts()} x.followers error={e}{ridp}")
        return []

async def scrap_seguidos(page, perfil_url, username, rid: str | None = None):
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.following start{ridp} registry_ver={registry_version('x')}")
    try:
        perfil_url = normalize_input_url('x', perfil_url)
        following_url = f"{perfil_url.rstrip('/')}/following"
        await page.goto(following_url, timeout=12_000)
        await page.wait_for_timeout(1200)
        selectors_items = get_selectors('x', 'lists.list_item')
        found_any = False
        for sel in selectors_items:
            try:
                el = await page.query_selector(sel)
                if el:
                    found_any = True; break
            except Exception: continue
        if not found_any:
            try:
                body_text = await page.inner_text('body')
            except Exception:
                body_text = ''
            code = classify_page_state('x', body_text) or ErrorCode.SELECTOR_MISS
            logger.warning(f"{_ts()} x.following no_items code={code.value}{ridp}")
        seguidos = await extraer_usuarios_lista(page, "seguidos", rid=rid)
        if len(seguidos) == 0:
            logger.warning(f"{_ts()} x.following error.code=EMPTY_LIST{ridp}")
        logger.info(f"{_ts()} x.following count={len(seguidos)}{ridp}")
        return seguidos
    except Exception as e:
        logger.warning(f"{_ts()} x.following error={e}{ridp}")
        return []
