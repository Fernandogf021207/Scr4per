import asyncio
import logging
from typing import Dict, List, Optional

from src.utils.list_parser import build_user_item
from src.utils.url import normalize_input_url

logger = logging.getLogger(__name__)


_IGNORED_PATH_PREFIXES = (
    '/p/',
    '/reel/',
    '/explore/',
    '/accounts/',
    '/stories/',
    '/direct/',
)


async def _dismiss_common_popups(page) -> None:
    """Intenta cerrar interstitials/popups comunes que bloquean clicks en Instagram."""
    selectors = [
        'button:has-text("Ahora no")',
        'button:has-text("Not now")',
        'button:has-text("Aceptar")',
        'button:has-text("Allow all cookies")',
        'button:has-text("Permitir cookies")',
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                await el.click(timeout=1000)
                await asyncio.sleep(0.2)
        except Exception:
            continue


async def _modal_has_loading_indicator(page) -> bool:
    """Detecta si el modal/lista sigue cargando resultados (spinner/progressbar/texto)."""
    try:
        return bool(
            await page.evaluate(
                """
                () => {
                    const scope = document.querySelector('div[role="dialog"], div[aria-modal="true"]') || document;
                    const loadingSelectors = [
                        '[role="progressbar"]',
                        'svg[aria-label*="Loading"]',
                        'svg[aria-label*="Cargando"]',
                        'div[aria-busy="true"]',
                    ];
                    for (const sel of loadingSelectors) {
                        const node = scope.querySelector(sel);
                        if (node) return true;
                    }
                    const text = (scope.textContent || '').toLowerCase();
                    if (text.includes('loading') || text.includes('cargando')) return true;
                    return false;
                }
                """
            )
        )
    except Exception:
        return False


def _username_from_url(url: str) -> str:
    if not url:
        return 'unknown'
    clean = url.split('?', 1)[0].rstrip('/')
    if not clean:
        return 'unknown'
    parts = clean.split('/')
    if not parts:
        return 'unknown'
    username = parts[-1] or (parts[-2] if len(parts) >= 2 else 'unknown')
    return username or 'unknown'


def _iter_dicts(obj):
    """Recorre recursivamente payloads JSON y produce todos los dicts."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_dicts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_dicts(item)


def _looks_like_instagram_username(username: str) -> bool:
    if not username:
        return False
    import re

    return bool(re.match(r'^[A-Za-z0-9._]{1,30}$', username))


def _extract_likers_from_graphql_payload(payload, owner_username: str, post_url: str) -> Dict[str, dict]:
    """Extrae candidatos de 'likers' desde respuestas GraphQL de Instagram."""
    out: Dict[str, dict] = {}
    owner_l = (owner_username or '').lower()

    for node in _iter_dicts(payload):
        username = node.get('username')
        if not isinstance(username, str):
            continue
        username = username.strip()
        if not _looks_like_instagram_username(username):
            continue
        if username.lower() == owner_l:
            continue

        # Heurística: objeto de usuario real (evita ruido de nodos no-user)
        if not any(k in node for k in ('profile_pic_url', 'profile_pic_url_hd', 'full_name', 'is_private', 'is_verified', 'id')):
            continue

        full_name = node.get('full_name') if isinstance(node.get('full_name'), str) else None
        photo = node.get('profile_pic_url') or node.get('profile_pic_url_hd') or ''
        profile_url = f"https://www.instagram.com/{username}/"
        item = build_user_item('instagram', profile_url, full_name or username, photo)
        item['post_url'] = normalize_input_url('instagram', post_url)
        item['reaction_type'] = 'like'
        key = item.get('link_usuario')
        if key:
            out[key] = item

    return out


async def _capture_likers_from_response(response, owner_username: str, post_url: str, likers_out: Dict[str, dict]):
    """Procesa una respuesta de red y agrega usuarios likers detectados por GraphQL."""
    try:
        url = (response.url or '').lower()
        if 'graphql' not in url and 'api/v1' not in url:
            return
        try:
            data = await response.json()
        except Exception:
            return
        found = _extract_likers_from_graphql_payload(data, owner_username, post_url)
        for k, v in found.items():
            if k not in likers_out:
                likers_out[k] = v
    except Exception:
        return


async def login_instagram(page, max_retries: int = 3) -> bool:
    """Valida que la sesion siga activa sin depender de selectores fragiles."""
    target = 'https://www.instagram.com/'

    for attempt in range(1, max_retries + 1):
        try:
            await page.goto(target, wait_until='domcontentloaded')
            await page.wait_for_load_state('networkidle', timeout=10000)

            current = (page.url or '').lower()
            if '/accounts/login' in current:
                logger.error('Sesion de Instagram expirada: redireccion a login.')
                return False
            if '/challenge/' in current or '/checkpoint/' in current:
                logger.error('Cuenta bloqueada o en challenge/checkpoint.')
                return False

            # Criterios positivos: avatar en nav o barra principal.
            nav_ok = await page.evaluate(
                """
                () => {
                    const selectors = [
                        'nav a[href="/"]',
                        'svg[aria-label="Home"]',
                        'svg[aria-label="Inicio"]',
                        'a[href*="/accounts/edit/"]',
                        'img[alt*="profile picture"]',
                        'img[alt*="foto del perfil"]'
                    ];
                    return selectors.some((sel) => document.querySelector(sel));
                }
                """
            )
            if nav_ok:
                logger.info('Sesion Instagram valida.')
                return True

            logger.warning('No hubo indicador claro de sesion. Reintento %d/%d', attempt, max_retries)
        except Exception as exc:
            logger.warning('Intento %d fallo validando sesion: %s', attempt, exc)

        await asyncio.sleep(1)

    return False


async def _wait_profile_ready(page, timeout_ms: int = 12000) -> None:
    await page.wait_for_load_state('domcontentloaded')
    await page.wait_for_function(
        """
        () => {
            const hasHeader = !!document.querySelector('header');
            const hasUserLink = !!document.querySelector('a[href^="/"]');
            return hasHeader && hasUserLink;
        }
        """,
        timeout=timeout_ms,
    )


async def get_profile_data_scrapling(page, profile_url: str) -> Dict[str, str]:
    """
    Extrae datos de perfil usando HTML renderizado + Scrapling Selector.
    Mantiene fallback a Playwright para robustez.
    """
    normalized = normalize_input_url('instagram', profile_url)
    await page.goto(normalized, wait_until='domcontentloaded')
    await _wait_profile_ready(page)

    username = _username_from_url(normalized)
    display_name: Optional[str] = None
    photo_url = ''

    html = await page.content()
    if html and len(html) > 300:
        try:
            from scrapling import Selector

            dom = Selector(text=html)
            name_candidates = dom.css('header h2, header h1, h1, h2')
            for node in name_candidates:
                text = (getattr(node, 'text', None) or '').strip()
                if text and text.lower() != username.lower():
                    display_name = text
                    break

            img_candidates = dom.css('header img, img[alt*="profile"], img[alt*="perfil"]')
            for node in img_candidates:
                src = (node.attrib.get('src') or node.attrib.get('data-src') or '').strip()
                if src and not src.startswith('data:'):
                    photo_url = src
                    break
        except Exception as exc:
            logger.debug('Fallback a Playwright por error en Scrapling: %s', exc)

    if not display_name:
        display_name = await page.evaluate(
            """
            (uname) => {
                const candidates = document.querySelectorAll('header h2, header h1, h1, h2');
                for (const el of candidates) {
                    const t = (el.textContent || '').trim();
                    if (t && t.toLowerCase() !== uname.toLowerCase()) return t;
                }
                return uname;
            }
            """,
            username,
        )

    if not photo_url:
        try:
            photo_url = await page.evaluate(
                """
                () => {
                    const img = document.querySelector('header img, img[alt*="profile"], img[alt*="perfil"]');
                    if (!img) return '';
                    return img.currentSrc || img.src || '';
                }
                """
            )
        except Exception:
            photo_url = ''

    return {
        'username': username,
        'nombre_completo': display_name or username,
        'foto_perfil': photo_url or '',
        'url_usuario': normalized,
    }


async def _open_relationship_modal(page, list_type: str) -> bool:
    href_fragment = '/followers/' if list_type == 'followers' else '/following/'
    for _ in range(3):
        await _dismiss_common_popups(page)

        clicked = await page.evaluate(
            """
            (fragment) => {
                const links = Array.from(document.querySelectorAll('header a[href], a[href]'));
                const target = links.find((a) => {
                    const href = a.getAttribute('href') || '';
                    return href.includes(fragment);
                });
                if (!target) return false;
                target.scrollIntoView({block: 'center'});
                target.click();
                return true;
            }
            """,
            href_fragment,
        )
        if not clicked:
            try:
                alt = await page.query_selector(f'header a[href*="{href_fragment}"]')
                if alt:
                    await alt.click(timeout=1200)
                    clicked = True
            except Exception:
                clicked = False

        if clicked:
            try:
                await page.wait_for_function(
                    """
                    () => !!document.querySelector('div[role="dialog"], div[aria-modal="true"]')
                    """,
                    timeout=5000,
                )
                await page.wait_for_function(
                    """
                    () => {
                        const dialog = document.querySelector('div[role="dialog"], div[aria-modal="true"]');
                        if (!dialog) return false;
                        return !!dialog.querySelector('a[href^="/"]');
                    }
                    """,
                    timeout=4000,
                )
                return True
            except Exception:
                # Si el modal existe pero aun sin contenido, de todas formas dejamos avanzar
                modal_exists = await page.evaluate(
                    """() => !!document.querySelector('div[role="dialog"], div[aria-modal="true"]')"""
                )
                if modal_exists:
                    return True

        await asyncio.sleep(0.6)

    # Fallback: en algunos layouts Instagram navega a una vista de lista sin modal
    try:
        fallback_opened = await page.evaluate(
            """
            (fragment) => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                const target = links.find((a) => (a.getAttribute('href') || '').includes(fragment));
                if (!target) return false;
                const href = target.getAttribute('href') || '';
                if (!href) return false;
                window.location.href = href;
                return true;
            }
            """,
            href_fragment,
        )
        if fallback_opened:
            await page.wait_for_load_state('domcontentloaded')
            await asyncio.sleep(1.2)
            has_any_user_link = await page.evaluate(
                """
                () => !!document.querySelector('a[href^="/"]')
                """
            )
            return bool(has_any_user_link)
    except Exception:
        pass

    return False


async def _extract_modal_users(page, owner_username: str, users: Dict[str, dict]) -> int:
    batch = await page.evaluate(
        """
        () => {
            const dialog = document.querySelector('div[role="dialog"], div[aria-modal="true"]');
            const scope = dialog || document;
            const links = Array.from(scope.querySelectorAll('a[href^="/"]'));
            const out = [];
            for (const a of links) {
                const href = (a.getAttribute('href') || '').trim();
                if (!href || !href.startsWith('/')) continue;
                const txt = (a.textContent || '').trim();
                const row = a.closest('li, div');
                const img = row ? row.querySelector('img') : null;
                const src = img ? (img.currentSrc || img.src || '') : '';
                out.push({ href, text: txt, src });
            }
            return out;
        }
        """
    )

    added = 0
    for rec in batch or []:
        href = rec.get('href') or ''
        if not href.startswith('/'):
            continue
        if href.startswith(_IGNORED_PATH_PREFIXES):
            continue

        full_url = f"https://www.instagram.com{href.split('?', 1)[0]}"
        item = build_user_item('instagram', full_url, rec.get('text') or None, rec.get('src') or '')
        username = item.get('username_usuario') or ''
        if not username or username == owner_username:
            continue
        key = item.get('link_usuario')
        if not key or key in users:
            continue
        users[key] = item
        added += 1

    return added


async def _scroll_dialog_container(page) -> bool:
    """Hace scroll al contenedor del modal y devuelve True si se movio."""
    moved = await page.evaluate(
        """
        () => {
            const dialog = document.querySelector('div[role="dialog"], div[aria-modal="true"]');
            if (!dialog) {
                const before = window.pageYOffset;
                window.scrollBy(0, Math.floor(window.innerHeight * 0.85));
                return window.pageYOffset > before;
            }

            let target = null;
            let best = -1;
            for (const el of dialog.querySelectorAll('*')) {
                const sh = el.scrollHeight || 0;
                const ch = el.clientHeight || 0;
                if (sh <= ch + 20) continue;
                if (sh - ch > best) {
                    best = sh - ch;
                    target = el;
                }
            }

            if (!target) return false;
            const before = target.scrollTop || 0;
            target.scrollTop = before + Math.max(500, Math.floor(target.clientHeight * 0.8));
            const after = target.scrollTop || 0;
            return after > before;
        }
        """
    )
    return bool(moved)


async def scrap_list_network_scrapling(page, profile_url: str, list_type: str) -> List[dict]:
    """
    Extrae followers/following desde modal con parseo dinamico.
    list_type esperado: 'followers' o 'following'.
    """
    if list_type not in ('followers', 'following'):
        logger.warning('list_type invalido para Instagram: %s', list_type)
        return []

    profile = await get_profile_data_scrapling(page, profile_url)
    owner_username = profile.get('username') or ''

    if not await _open_relationship_modal(page, list_type):
        logger.warning('No fue posible abrir modal de %s', list_type)
        return []

    users: Dict[str, dict] = {}
    no_new = 0
    loading_wait_cycles = 0

    for _ in range(70):
        before = len(users)
        await _extract_modal_users(page, owner_username, users)
        grew = len(users) > before

        is_loading = await _modal_has_loading_indicator(page)

        scrolled = await _scroll_dialog_container(page)
        if not scrolled and not grew:
            if is_loading and loading_wait_cycles < 8:
                loading_wait_cycles += 1
                await asyncio.sleep(1.0)
                continue
            break

        if grew:
            no_new = 0
            loading_wait_cycles = 0
        else:
            if is_loading and loading_wait_cycles < 8:
                loading_wait_cycles += 1
                await asyncio.sleep(1.0)
                continue
            no_new += 1
            if no_new >= 5:
                break

        await asyncio.sleep(0.25)

    logger.info('Extraidos %d usuarios de %s via Scrapling', len(users), list_type)
    return list(users.values())


# ---------------------------------------------------------------------------
# Post Engagement Scraping
# ---------------------------------------------------------------------------

async def _extract_posts_from_profile(page, max_posts: int = 5) -> List[str]:
    """
    Recoge URLs de posts (/p/ y /reel/) del grid del perfil actual.
    Scroll adaptativo hasta alcanzar max_posts o estancamiento.
    """
    urls: set = set()
    no_new = 0

    _JS_POSTS = """
    () => {
        const anchors = Array.from(document.querySelectorAll('article a[href], a[href]'));
        const out = [];
        for (const a of anchors) {
            const href = a.getAttribute('href') || '';
            if (href.startsWith('/p/') || href.startsWith('/reel/')) {
                out.push(href);
            }
        }
        return out;
    }
    """

    try:
        await page.wait_for_function(
            """
            () => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                return links.some((a) => {
                    const h = a.getAttribute('href') || '';
                    return h.startsWith('/p/') || h.startsWith('/reel/');
                });
            }
            """,
            timeout=8000,
        )
    except Exception:
        pass

    for _ in range(15):
        before = len(urls)
        try:
            hrefs = await page.evaluate(_JS_POSTS)
            for h in hrefs or []:
                full = f"https://www.instagram.com{h.split('?', 1)[0]}"
                urls.add(full)
                if len(urls) >= max_posts:
                    break
        except Exception as exc:
            logger.debug('Error recolectando posts: %s', exc)

        if len(urls) >= max_posts:
            break

        if len(urls) > before:
            no_new = 0
        else:
            no_new += 1
            if no_new >= 3:
                break

        # Verificar si llegamos al fondo
        at_bottom = await page.evaluate(
            """
            () => (window.innerHeight + window.pageYOffset) >= document.body.scrollHeight - 300
            """
        )
        if at_bottom:
            break

        await page.evaluate("window.scrollBy(0, window.innerHeight * 0.85)")
        await asyncio.sleep(1.2)

    if not urls:
        # Fallback robusto: extraer URLs de posts/reels embebidas en HTML/scripts.
        try:
            import re

            html = await page.content()
            matches = re.findall(r'/(?:p|reel)/[A-Za-z0-9_-]+/?', html or '')
            for m in matches:
                urls.add(f"https://www.instagram.com{m.rstrip('/')}/")
                if len(urls) >= max_posts:
                    break
        except Exception as exc:
            logger.debug('Fallback regex de posts fallo: %s', exc)

    result = list(urls)[:max_posts]
    if not result:
        try:
            is_private = await page.evaluate(
                """
                () => {
                    const t = (document.body && document.body.innerText ? document.body.innerText : '').toLowerCase();
                    return t.includes('this account is private') || t.includes('esta cuenta es privada');
                }
                """
            )
            if is_private:
                logger.warning('No hay posts visibles porque el perfil parece privado.')
        except Exception:
            pass
    logger.info('Posts encontrados en perfil: %d', len(result))
    return result


async def _open_liked_by_modal(page, post_url: str) -> bool:
    """
    Navega al post y abre el modal de liked_by.
    Usa evaluacion JS para detectar y clicar el enlace sin depender de texto exacto.
    Devuelve True si el modal fue abierto exitosamente.
    """
    try:
        await page.goto(post_url, wait_until='domcontentloaded')
        await page.wait_for_load_state('networkidle', timeout=8000)
    except Exception:
        pass

    await _dismiss_common_popups(page)

    # Buscar enlace /liked_by/ o boton de likes por heuristica semantica
    clicked = await page.evaluate(
        r"""
        () => {
            // Primero intentar enlace directo /liked_by/
            const likedByLink = Array.from(document.querySelectorAll('a[href]')).find(
                (a) => (a.getAttribute('href') || '').includes('/liked_by/')
            );
            if (likedByLink) { likedByLink.click(); return true; }

            // Fallback: boton/span con conteo de likes visible
            const isVisible = (el) => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && r.top < window.innerHeight;
            };
            const candidates = Array.from(
                document.querySelectorAll('a, button, [role="button"], span')
            );
            for (const el of candidates) {
                if (!isVisible(el)) continue;
                const txt = (el.textContent || el.getAttribute('aria-label') || '').toLowerCase();
                if (
                    (txt.includes('like') || txt.includes('me gusta') || txt.includes('gusta')) &&
                    /\d/.test(txt)
                ) {
                    el.click();
                    return true;
                }
            }
            return false;
        }
        """
    )

    if not clicked:
        # Segundo intento: abrir lista de likes navegando a /liked_by/ del post actual.
        try:
            liked_url = await page.evaluate(
                """
                () => {
                    const canonical = document.querySelector('link[rel="canonical"]');
                    const href = canonical ? (canonical.getAttribute('href') || '') : '';
                    if (!href) return '';
                    const clean = href.split('?')[0].replace(/\/+$/, '');
                    if (!/\/p\//.test(clean) && !/\/reel\//.test(clean)) return '';
                    return `${clean}/liked_by/`;
                }
                """
            )
            if liked_url:
                await page.goto(liked_url, wait_until='domcontentloaded')
                await asyncio.sleep(1.0)
                has_links = await page.evaluate(
                    """
                    () => {
                        const scope = document.querySelector('div[role="dialog"], div[aria-modal="true"]') || document;
                        return !!scope.querySelector('a[href^="/"]');
                    }
                    """
                )
                if has_links:
                    return True
        except Exception:
            pass

        logger.debug('No se encontro disparador de liked_by en %s', post_url)
        return False

    try:
        await page.wait_for_function(
            """() => !!document.querySelector('div[role="dialog"], div[aria-modal="true"]')""",
            timeout=5000,
        )
        await page.wait_for_function(
            """
            () => {
                const dialog = document.querySelector('div[role="dialog"], div[aria-modal="true"]');
                if (!dialog) return false;
                return !!dialog.querySelector('a[href^="/"]');
            }
            """,
            timeout=3500,
        )
        return True
    except Exception:
        logger.debug('Modal de liked_by no aparecio en %s', post_url)
        return False


async def _extract_likers_from_modal(page, users: Dict[str, dict]) -> int:
    """
    Lee usuarios del modal de liked_by abierto actualmente.
    Reutiliza logica de _extract_modal_users sin filtrar por owner.
    """
    batch = await page.evaluate(
        """
        () => {
            const dialog = document.querySelector('div[role="dialog"], div[aria-modal="true"]');
            if (!dialog) return [];
            const links = Array.from(dialog.querySelectorAll('a[href^="/"]'));
            const out = [];
            for (const a of links) {
                const href = (a.getAttribute('href') || '').trim();
                if (!href || !href.startsWith('/')) continue;
                const txt = (a.textContent || '').trim();
                const row = a.closest('li, div');
                const img = row ? row.querySelector('img') : null;
                const src = img ? (img.currentSrc || img.src || '') : '';
                out.push({ href, text: txt, src });
            }
            return out;
        }
        """
    )

    added = 0
    for rec in batch or []:
        href = rec.get('href') or ''
        if not href.startswith('/'):
            continue
        if any(href.startswith(pfx) for pfx in _IGNORED_PATH_PREFIXES):
            continue

        full_url = f"https://www.instagram.com{href.split('?', 1)[0]}"
        item = build_user_item('instagram', full_url, rec.get('text') or None, rec.get('src') or '')
        key = item.get('link_usuario')
        if not key or key in users:
            continue
        item['reaction_type'] = 'like'
        users[key] = item
        added += 1

    return added


async def _extract_comments_from_post(page, post_url: str) -> List[dict]:
    """
    Navega al post y extrae autores de comentarios visibles.
    Usa JS batch sobre article/section para evitar selectores fragiles.
    Hace scroll para cargar mas comentarios antes de extraer.
    """
    try:
        await page.goto(post_url, wait_until='domcontentloaded')
        await page.wait_for_load_state('networkidle', timeout=8000)
    except Exception:
        pass

    users: Dict[str, dict] = {}
    no_new = 0

    _JS_COMMENTS = r"""
    () => {
        const IGNORED = ['/p/', '/reel/', '/explore/', '/accounts/', '/stories/', '/direct/'];
        const containers = Array.from(document.querySelectorAll(
            'article, section, div[role="article"], ul'
        ));
        const out = [];
        const seen = new Set();
        for (const cont of containers) {
            const links = Array.from(cont.querySelectorAll('a[href^="/"]'));
            for (const a of links) {
                const href = (a.getAttribute('href') || '').trim();
                if (!href || seen.has(href)) continue;
                if (IGNORED.some((pfx) => href.startsWith(pfx))) continue;
                const clean = href.split('?')[0].replace(/\/+$/, '');
                const parts = clean.split('/').filter(Boolean);
                if (parts.length !== 1) continue;
                seen.add(href);
                const row = a.closest('li, div, span');
                const img = row ? row.querySelector('img') : null;
                const src = img ? (img.currentSrc || img.src || '') : '';
                out.push({ href, text: (a.textContent || '').trim(), src });
            }
        }
        return out;
    }
    """

    for _ in range(10):
        before = len(users)
        try:
            batch = await page.evaluate(_JS_COMMENTS)
            for rec in batch or []:
                href = rec.get('href') or ''
                if not href.startswith('/'):
                    continue
                full_url = f"https://www.instagram.com{href.split('?', 1)[0]}"
                item = build_user_item('instagram', full_url, rec.get('text') or None, rec.get('src') or '')
                key = item.get('link_usuario')
                if not key or key in users:
                    continue
                users[key] = item
        except Exception as exc:
            logger.debug('Error extrayendo comentarios: %s', exc)

        if len(users) > before:
            no_new = 0
        else:
            no_new += 1
            if no_new >= 3:
                break

        # Scroll en el area de comentarios o en la pagina
        scrolled = await page.evaluate(
            r"""
            () => {
                const art = document.querySelector('article');
                if (art) {
                    const sections = Array.from(art.querySelectorAll('*'));
                    let best = null, bestDiff = 0;
                    for (const el of sections) {
                        const diff = el.scrollHeight - el.clientHeight;
                        if (diff > bestDiff) { bestDiff = diff; best = el; }
                    }
                    if (best && bestDiff > 50) {
                        const before = best.scrollTop;
                        best.scrollTop += 400;
                        return best.scrollTop > before;
                    }
                }
                const before = window.pageYOffset;
                window.scrollBy(0, 400);
                return window.pageYOffset > before;
            }
            """
        )
        if not scrolled and no_new >= 2:
            break
        await asyncio.sleep(0.9)

    logger.info('Comentaristas extraidos del post: %d', len(users))
    return list(users.values())


async def scrap_post_engagements_scrapling(
    page, profile_url: str, username: str, max_posts: int = 5
) -> Dict[str, List[dict]]:
    """
    Extrae reacciones (liked_by) y comentaristas de los ultimos posts del perfil.

    Retorna:
        { 'reactions': [...], 'comments': [...] }
    """
    profile = await get_profile_data_scrapling(page, profile_url)
    owner_username = profile.get('username') or username

    logger.info('Buscando posts del perfil %s...', owner_username)
    post_urls = await _extract_posts_from_profile(page, max_posts=max_posts)

    if not post_urls:
        logger.warning('No se encontraron posts para %s', owner_username)
        return {'reactions': [], 'comments': []}

    all_reactions: Dict[str, dict] = {}
    all_comments: Dict[str, dict] = {}

    for idx, post_url in enumerate(post_urls, 1):
        logger.info('Procesando post [%d/%d]: %s', idx, len(post_urls), post_url)

        # --- Reacciones (liked_by) ---
        try:
            network_likers: Dict[str, dict] = {}
            pending_tasks = set()

            def _on_response(resp):
                task = asyncio.create_task(
                    _capture_likers_from_response(resp, owner_username, post_url, network_likers)
                )
                pending_tasks.add(task)

                def _done(_):
                    pending_tasks.discard(task)

                task.add_done_callback(_done)

            page.on('response', _on_response)

            modal_opened = await _open_liked_by_modal(page, post_url)
            if modal_opened:
                no_new_likers = 0
                loading_wait_cycles = 0
                for _ in range(40):
                    before = len(all_reactions)
                    await _extract_likers_from_modal(page, all_reactions)
                    grew = len(all_reactions) > before
                    is_loading = await _modal_has_loading_indicator(page)

                    scrolled = await _scroll_dialog_container(page)
                    if not scrolled and not grew:
                        if is_loading and loading_wait_cycles < 6:
                            loading_wait_cycles += 1
                            await asyncio.sleep(1.0)
                            continue
                        break
                    if grew:
                        no_new_likers = 0
                        loading_wait_cycles = 0
                    else:
                        if is_loading and loading_wait_cycles < 6:
                            loading_wait_cycles += 1
                            await asyncio.sleep(1.0)
                            continue
                        no_new_likers += 1
                        if no_new_likers >= 4:
                            break
                    await asyncio.sleep(0.3)

                # Asegurar parseo de red antes de cerrar modal
                if pending_tasks:
                    await asyncio.gather(*list(pending_tasks), return_exceptions=True)

                for key, item in network_likers.items():
                    if key not in all_reactions:
                        all_reactions[key] = item

                # Cerrar modal con Escape
                try:
                    await page.keyboard.press('Escape')
                    await asyncio.sleep(0.4)
                except Exception:
                    pass
            else:
                logger.debug('Modal liked_by no disponible para %s', post_url)

            try:
                page.remove_listener('response', _on_response)
            except Exception:
                pass
        except Exception as exc:
            logger.warning('Error extrayendo likes de %s: %s', post_url, exc)

        # --- Comentarios ---
        try:
            comments = await _extract_comments_from_post(page, post_url)
            for item in comments:
                key = item.get('link_usuario')
                if key and key not in all_comments:
                    all_comments[key] = item
        except Exception as exc:
            logger.warning('Error extrayendo comentarios de %s: %s', post_url, exc)

        # Pausa entre posts
        if idx < len(post_urls):
            await asyncio.sleep(1.5)

    logger.info(
        'Engagements totales — reacciones: %d | comentaristas: %d',
        len(all_reactions), len(all_comments)
    )
    return {
        'reactions': list(all_reactions.values()),
        'comments': list(all_comments.values()),
    }


# ---------------------------------------------------------------------------
# CSV Export
# ---------------------------------------------------------------------------

def export_to_csv(results: dict, output_path: str) -> str:
    """
    Exporta los resultados de scraping de Instagram a CSV usando pandas.

    Parametros:
        results (dict): Claves opcionales:
            - 'profile':   dict con datos del perfil principal
            - 'followers': list[dict] de seguidores
            - 'following': list[dict] de seguidos
            - 'reactions': list[dict] de usuarios que dieron like en posts
            - 'comments':  list[dict] de usuarios que comentaron en posts
        output_path (str): Ruta de destino del archivo CSV.

    Retorna:
        str: Ruta final del archivo generado.
    """
    import pandas as pd

    rows = []

    profile = results.get('profile') or {}
    if profile:
        rows.append({
            'tipo': 'PERFIL',
            'username': profile.get('username', ''),
            'nombre_completo': profile.get('nombre_completo', ''),
            'url_perfil': profile.get('url_usuario', ''),
            'foto': profile.get('foto_perfil', ''),
            'interaccion': '',
        })

    def _add_users(user_list: List[dict], tipo: str):
        for u in user_list:
            rows.append({
                'tipo': tipo,
                'username': u.get('username_usuario', ''),
                'nombre_completo': u.get('nombre_completo_usuario', ''),
                'url_perfil': u.get('link_usuario', ''),
                'foto': u.get('url_foto', ''),
                'interaccion': u.get('reaction_type', ''),
            })

    _add_users(results.get('followers', []), 'SEGUIDOR')
    _add_users(results.get('following', []), 'SEGUIDO')
    _add_users(results.get('reactions', []), 'REACCION_POST')
    _add_users(results.get('comments', []), 'COMENTARIO_POST')

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    logger.info('CSV exportado exitosamente: %s (%d filas)', output_path, len(df))
    return output_path
