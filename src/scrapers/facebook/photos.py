import time
import logging
import asyncio
from typing import List, Dict
from src.utils.dom import find_scroll_container, scroll_collect
from src.scrapers.facebook.utils import get_text, get_attr, absolute_url_keep_query, normalize_profile_url
from src.utils.list_parser import build_user_item
from src.utils.url import normalize_post_url, normalize_input_url

logger = logging.getLogger(__name__)

def _ts() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

async def navegar_a_fotos(page, perfil_url: str) -> bool:
    candidates = ["photos_by", "photos", "photos_all"]
    perfil_url = normalize_input_url('facebook', perfil_url)
    base = perfil_url.rstrip('/')
    for suf in candidates:
        try:
            await page.goto(f"{base}/{suf}/")
            await page.wait_for_timeout(2500)
            has_photos = await page.query_selector('a[href*="photo.php"], a[href*="/photos/"] img, img[src*="scontent"]')
            if has_photos:
                return True
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
        await scroll_collect(
            page,
            process_cb,
            container=container,
            max_scrolls=50,
            pause_ms=900,
            no_new_threshold=6,
        )
    except Exception:
        return

async def abrir_y_scrapear_modal_reacciones(page, reacciones_dict: Dict[str, dict], photo_url: str):
    botones = [
        'div[role="button"]:has-text("Ver quién reaccionó")',
        'div[role="button"]:has-text("See who reacted")',
        'a[role="button"]:has-text("reaccion")',
        'div[role="button"][aria-label*="reaccion"]',
        'div[role="button"][aria-label*="react"]',
    ]
    for sel in botones:
        try:
            btn = await page.query_selector(sel)
            if btn:
                await btn.click()
                await page.wait_for_timeout(1500)
                await procesar_usuarios_en_modal_reacciones(page, reacciones_dict, photo_url)
                try:
                    close_btn = await page.query_selector('div[role="dialog"] [aria-label*="Cerrar"], div[role="dialog"] [aria-label*="Close"]')
                    if close_btn:
                        await close_btn.click()
                        await page.wait_for_timeout(500)
                except Exception:
                    pass
                return True
        except Exception:
            continue
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
            await page.goto(photo_url)
            await page.wait_for_timeout(2500)
            await abrir_y_scrapear_modal_reacciones(page, reacciones, photo_url)
            if incluir_comentarios:
                await abrir_y_scrapear_reacciones_en_comentarios(page, reacciones, photo_url)
            if i % 3 == 0:
                await asyncio.sleep(2)
        except Exception:
            continue
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
            await page.goto(photo_url)
            await page.wait_for_timeout(2000)
            for _ in range(15):
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
                    for bsel in botones:
                        b = await page.query_selector(bsel)
                        if b:
                            try:
                                role_btn = await b.evaluate_handle('el => el.closest("[role=\\"button\\"]") || el')
                                await role_btn.click()
                            except Exception:
                                await b.click()
                            await page.wait_for_timeout(900)
                            break
                except Exception:
                    pass
                try:
                    await page.evaluate("""
                        () => {
                            const modal = document.querySelector('div[role="dialog"]');
                            let el = modal;
                            if (modal) {
                                let best = modal;
                                const nodes = modal.querySelectorAll('div, section, main, article');
                                nodes.forEach(n => {
                                    const sh = n.scrollHeight || 0;
                                    const ch = n.clientHeight || 0;
                                    const st = getComputedStyle(n).overflowY;
                                    if (sh > ch + 50 && (st === 'auto' || st === 'scroll')) {
                                        best = n;
                                    }
                                });
                                el = best;
                            }
                            (el || document.scrollingElement || document.body).scrollTop += 800;
                        }
                    """)
                except Exception:
                    pass
                await page.wait_for_timeout(800)
                await procesar_comentarios_en_modal_foto(page, comentarios, photo_url)
            if i % 3 == 0:
                await asyncio.sleep(2)
        except Exception:
            continue
    return list(comentarios.values())
