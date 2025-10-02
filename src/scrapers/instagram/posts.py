import time
import logging
import asyncio
from src.utils.url import normalize_input_url, normalize_post_url
from src.utils.dom import find_scroll_container, scroll_element, scroll_window
from src.utils.list_parser import build_user_item
from src.scrapers.resource_blocking import start_list_blocking
from src.scrapers.concurrency import run_limited

logger = logging.getLogger(__name__)

def _ts() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

async def extraer_posts_del_perfil(page, max_posts=10):
    logger.info(f"{_ts()} instagram.posts start target={max_posts}")
    try:
        urls_posts = set()
        scroll_attempts = 0
        max_scrolls = 8
        no_new_posts_count = 0
        max_no_new_posts = 2
        while len(urls_posts) < max_posts and scroll_attempts < max_scrolls and no_new_posts_count < max_no_new_posts:
            current_posts_count = len(urls_posts)
            await page.evaluate("() => { window.scrollBy(0, window.innerHeight * 0.8); }")
            await page.wait_for_timeout(1100)
            selectores_posts = [
                'article a[href*="/p/"]', 'article a[href*="/reel/"]',
                'a[href*="/p/"]', 'a[href*="/reel/"]', 'div a[href*="/p/"]', 'div a[href*="/reel/"]'
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
                                url_completa = f"https://www.instagram.com{href}" if href.startswith('/') else href
                                if '/p/' in url_completa or '/reel/' in url_completa:
                                    urls_posts.add(url_completa)
                        except:
                            continue
                except:
                    continue
            if len(urls_posts) > current_posts_count:
                no_new_posts_count = 0
                logger.info(f"{_ts()} instagram.posts progress count={len(urls_posts)} scroll={scroll_attempts + 1}")
            else:
                no_new_posts_count += 1
                logger.info(f"{_ts()} instagram.posts no_new scroll={scroll_attempts + 1} seq={no_new_posts_count}")
            scroll_attempts += 1
            is_at_bottom = await page.evaluate("() => (window.innerHeight + window.pageYOffset) >= document.body.scrollHeight - 1000;")
            if is_at_bottom:
                logger.info(f"{_ts()} instagram.posts end_bottom count={len(urls_posts)}")
                break
        urls_posts = list(urls_posts)[:max_posts]
        logger.info(f"{_ts()} instagram.posts final_count={len(urls_posts)}")
        return urls_posts
    except Exception as e:
        logger.error(f"Error extrayendo posts: {e}")
        return []

async def scrap_reacciones_instagram(page, perfil_url: str, username: str, max_posts: int = 5):
    try:
        perfil_url = normalize_input_url('instagram', perfil_url)
        await page.goto(perfil_url)
        await page.wait_for_timeout(1500)
        posts = await extraer_posts_del_perfil(page, max_posts=max_posts)
        logger.info(f"{_ts()} instagram.likes posts_found={len(posts)} target={max_posts}")
        if not posts:
            return []
        start = time.time()
        async def _abrir_liked_by_y_extraer_usuarios(post_url: str):
            try:
                await page.goto(post_url)
                await page.wait_for_timeout(2000)
                a = await page.query_selector('a[href*="/liked_by/"]')
                if not a:
                    for sel in ['a:has-text("likes")','a:has-text("Me gusta")','div[role="button"]:has-text("likes")','div[role="button"]:has-text("Me gusta")']:
                        a = await page.query_selector(sel)
                        if a: break
                if not a:
                    return []
                await a.click(); await page.wait_for_timeout(1500)
                usuarios_dict = {}
                container = await find_scroll_container(page)
                scrolls = 0; no_new = 0
                while scrolls < 50 and no_new < 6:
                    before = len(usuarios_dict)
                    try:
                        from .lists import procesar_usuarios_en_modal
                        await procesar_usuarios_en_modal(page, usuarios_dict, usuario_principal="", tipo_lista="liked_by")
                    except Exception: pass
                    if len(usuarios_dict) == before: no_new += 1
                    else: no_new = 0
                    if container: await scroll_element(container, 800)
                    else: await scroll_window(page, 600)
                    await page.wait_for_timeout(900); scrolls += 1
                res = []
                for v in usuarios_dict.values():
                    v = dict(v); v['post_url'] = normalize_post_url('instagram', post_url); v['reaction_type'] = 'like'; res.append(v)
                return res
            except Exception:
                return []
        tasks_callables = [lambda u=pu: _abrir_liked_by_y_extraer_usuarios(u) for pu in posts]
        results = await run_limited(tasks_callables, limit=1, label='ig.likes')
        aggregated = []
        for r in results:
            if r and r.ok and r.value: aggregated.extend(r.value)
        logger.info(f"{_ts()} instagram.likes done total_likes={len(aggregated)} duration_ms={(time.time()-start)*1000:.0f}")
        return aggregated
    except Exception:
        return []

async def scrap_comentadores_instagram(page, perfil_url, username, max_posts=5):
    logger.info(f"{_ts()} instagram.comments batch_start max_posts={max_posts}")
    try:
        await page.goto(perfil_url); await page.wait_for_timeout(3000)
        urls_posts = await extraer_posts_del_perfil(page, max_posts)
        logger.info(f"{_ts()} instagram.comments posts_found={len(urls_posts)}")
        if not urls_posts: return []
        async def extraer_comentarios_post(url_post, post_id):
            logger.info(f"{_ts()} instagram.post_comments start post_id={post_id}")
            comentarios_dict = {}
            try:
                await page.goto(url_post); await page.wait_for_timeout(3000)
                for _ in range(3):
                    try:
                        botones_cargar = ['button:has-text("Cargar más comentarios")','button:has-text("Load more comments")','button[aria-label="Load more comments"]','span:has-text("Cargar más comentarios")','button:has-text("Ver más comentarios")','button:has-text("View more comments")']
                        for selector_boton in botones_cargar:
                            boton = await page.query_selector(selector_boton)
                            if boton:
                                await boton.click(); await page.wait_for_timeout(2000); break
                    except: break
                scroll_attempts=0; max_scrolls=15; no_new=0
                while scroll_attempts < max_scrolls and no_new < 3:
                    before=len(comentarios_dict)
                    await page.evaluate("() => { const cs = document.querySelector('article section') || document.querySelector('div[role=\"button\"] section') || document.querySelector('section'); if (cs){ const sa = cs.querySelector('div[style*=\"overflow\"]') || cs.querySelector('div[style*=\"max-height\"]') || cs; sa.scrollTop += 300; } else { window.scrollBy(0,300); } }")
                    await page.wait_for_timeout(1500)
                    # Procesar comentarios visibles: heurística simple buscando anchors de usuario
                    try:
                        elementos = await page.query_selector_all('article a[href^="/"][href$="/"]')
                    except Exception:
                        elementos = []
                    for elemento in elementos:
                        try:
                            href = await elemento.get_attribute('href')
                            if not href or not href.startswith('/') or not href.endswith('/'):
                                continue
                            username = href.strip('/').split('/')[0]
                            if username in ['p','reel','tv','stories','explore'] or username == '':
                                continue
                            if username in comentarios_dict:
                                continue
                            nombre_mostrado = await elemento.inner_text() or username
                            url_perfil = f"https://www.instagram.com/{username}/"
                            comentarios_dict[username] = build_user_item('instagram', url_perfil, nombre_mostrado, '')
                        except Exception:
                            continue
                    if len(comentarios_dict)==before: no_new+=1
                    else: no_new=0
                    scroll_attempts+=1
                    if scroll_attempts %5==0: await page.wait_for_timeout(2000)
                res=[]
                for k,v in comentarios_dict.items():
                    v=dict(v); v['post_url']=normalize_post_url('instagram', url_post); res.append(v)
                return res
            except Exception:
                return []
        callables = [lambda i=i,u=u: extraer_comentarios_post(u,i+1) for i,u in enumerate(urls_posts)]
        results= await run_limited(callables, limit=1, label='ig.comments')
        agg=[]
        for r in results:
            if r and r.ok and r.value: agg.extend(r.value)
        logger.info(f"{_ts()} instagram.comments total={len(agg)} posts={len(urls_posts)}")
        return agg
    except Exception as e:
        logger.warning(f"{_ts()} instagram.comments error={e}")
        return []
