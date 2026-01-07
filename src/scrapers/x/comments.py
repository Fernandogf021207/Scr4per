import time
import logging
from urllib.parse import urljoin
from src.utils.url import normalize_input_url, normalize_post_url
from src.utils.dom import scroll_window
from src.utils.list_parser import build_user_item

logger = logging.getLogger(__name__)

def _ts():
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

async def extraer_comentadores_x(page, max_posts=10, rid: str | None = None):
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.commenters start target_posts={max_posts}{ridp}")
    comentadores_dict = {}
    scroll_attempts = 0; max_scroll_attempts = 30; no_new_content_count = 0; max_no_new_content = 5; posts_encontrados = 0
    try:
        await page.wait_for_selector('article[data-testid="tweet"]', timeout=1800)
    except Exception:
        await page.wait_for_timeout(600)
    while scroll_attempts < max_scroll_attempts and posts_encontrados < max_posts:
        try:
            posts = await page.query_selector_all('article[data-testid="tweet"]')
            if not posts:
                no_new_content_count += 1
                if no_new_content_count >= max_no_new_content:
                    break
                await scroll_window(page, 0); await page.wait_for_timeout(2000); scroll_attempts += 1; continue
            for post_index in range(posts_encontrados, min(len(posts), max_posts)):
                try:
                    posts = await page.query_selector_all('article[data-testid="tweet"]')
                    if post_index >= len(posts): break
                    post = posts[post_index]
                    post_link = await post.query_selector('a[href*="/status/"]')
                    if not post_link: continue
                    post_url = urljoin("https://x.com", await post_link.get_attribute("href"))
                    logger.info(f"{_ts()} x.commenters post start url={post_url}{ridp}")
                    scroll_position = await page.evaluate("window.pageYOffset")
                    await page.goto(post_url); await page.wait_for_timeout(1800)
                    for _ in range(3):
                        await scroll_window(page, 0); await page.wait_for_timeout(900)
                    comment_selectors = [
                        'div[data-testid="tweet"]:has(a[role="link"][href^="/"])',
                        'article[role="article"]:has(div[data-testid="tweetText"])',
                        'div[role="article"]:has(a[href^="/"][role="link"])'
                    ]
                    comentarios_encontrados = False
                    for selector in comment_selectors:
                        comentarios = await page.query_selector_all(selector)
                        if comentarios:
                            comentarios_encontrados = True
                            logger.info(f"{_ts()} x.commenters selector hit count={len(comentarios)} sel='{selector}'{ridp}")
                            for comentario in comentarios:
                                try:
                                    enlace_usuario = await comentario.query_selector('a[role="link"][href^="/"]:not([href*="/status/"])')
                                    if not enlace_usuario: continue
                                    href = await enlace_usuario.get_attribute("href")
                                    if not href or '/status/' in href: continue
                                    url_usuario = f"https://x.com{href}"
                                    item = build_user_item('x', url_usuario, None, None)
                                    url_limpia = item['link_usuario']; username_usuario = item['username_usuario']
                                    if (username_usuario.isdigit() or len(username_usuario) < 2 or len(username_usuario) > 50):
                                        continue
                                    if url_limpia in comentadores_dict:
                                        continue
                                    url_foto = ""; img_selectors = ['img[src*="profile_images"]','img[alt*="avatar"]','div[data-testid="UserAvatar-Container-"] img']
                                    for img_selector in img_selectors:
                                        img_element = await comentario.query_selector(img_selector)
                                        if img_element:
                                            src = await img_element.get_attribute("src")
                                            if src and not src.startswith("data:"):
                                                url_foto = src; break
                                    nombre_completo = username_usuario
                                    nombre_selectors = ['div[dir="ltr"] > span:first-child','span[dir="ltr"]:not(:has(span))','div[data-testid="UserName"] span:first-child']
                                    for nombre_selector in nombre_selectors:
                                        nombre_element = await comentario.query_selector(nombre_selector)
                                        if nombre_element:
                                            texto = await nombre_element.inner_text(); texto = texto.strip()
                                            if texto and not texto.startswith('@') and len(texto) > 1:
                                                nombre_completo = texto; break
                                    item = build_user_item('x', url_usuario, nombre_completo, url_foto)
                                    item['post_url'] = normalize_post_url('x', post_url)
                                    comentadores_dict[url_limpia] = item
                                except Exception:
                                    continue
                            break
                    posts_encontrados += 1
                    await page.go_back(); await page.wait_for_timeout(1200)
                    await page.evaluate(f"window.scrollTo(0, {scroll_position})"); await page.wait_for_timeout(1000)
                except Exception:
                    continue
            await scroll_window(page, 0); await page.wait_for_timeout(2000); scroll_attempts += 1
            if scroll_attempts % 5 == 0:
                await page.wait_for_timeout(2500)
        except Exception:
            no_new_content_count += 1; await page.wait_for_timeout(1000)
    if not comentadores_dict:
        logger.info(f"{_ts()} x.commenters empty_reason=NOT_FOUND_OR_PRIVATE{ridp}")
    logger.info(f"{_ts()} x.commenters done total={len(comentadores_dict)}{ridp}")
    return list(comentadores_dict.values())

async def scrap_comentadores(page, perfil_url, username, max_posts: int = 10, rid: str | None = None):
    ridp = f" rid={rid}" if rid else ""
    logger.info(f"{_ts()} x.commenters root start max_posts={max_posts}{ridp}")
    try:
        perfil_url = normalize_input_url('x', perfil_url)
        await page.goto(perfil_url); await page.wait_for_timeout(1200)
        comentadores = await extraer_comentadores_x(page, max_posts=max_posts, rid=rid)
        logger.info(f"{_ts()} x.commenters root count={len(comentadores)}{ridp}")
        return comentadores
    except Exception as e:
        logger.warning(f"{_ts()} x.commenters root error={e}{ridp}")
        return []
