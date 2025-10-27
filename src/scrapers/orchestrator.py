from __future__ import annotations
"""Central orchestration layer for multi-root scraping.

Encapsula:
 - Validación de requests
 - Ciclo de Playwright (una sola instancia)
 - Creación de contexts por plataforma usando storage_state
 - Uso de adapters (PlatformScraper) registrados
 - Ingesta en Aggregator (perfiles + relaciones + actividades)
 - Persistencia opcional a la base de datos

Mantiene compatibilidad: la forma del payload final coincide con Aggregator.build_payload().
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Optional, Type
import asyncio
import logging
import time
import re

from playwright.async_api import async_playwright

from src.scrapers.base import PlatformScraper
from src.utils.images import local_or_proxy_photo_url
from api.services.aggregation import Aggregator, make_profile, normalize_username, valid_username
from api.repositories import upsert_profile, add_relationship
from api.db import get_conn

logger = logging.getLogger(__name__)


REL_FOLLOWER = 'seguidor'
REL_FOLLOWING = 'seguido'
REL_FRIEND = 'amigo'


@dataclass
class ScrapeRequest:
    platform: str
    username: str
    max_photos: int = 5


class ScrapeOrchestrator:
    def __init__(
        self,
        *,
        scraper_registry: Dict[str, Type[PlatformScraper]],
        storage_state_resolver: Callable[[str], Optional[Dict[str, Any]]],
        max_roots: int = 5,
        persist: bool = True,
        headless: bool = True,
        max_concurrency: int = 1,
        download_photos: bool = True,
        photo_mode: str = 'download',  # 'download' | 'proxy' | 'external'
    ) -> None:
        self.scraper_registry = scraper_registry
        self.storage_state_resolver = storage_state_resolver
        self.max_roots = max_roots
        self.persist = persist
        self.headless = headless
        self.max_concurrency = max_concurrency
        self.download_photos = download_photos
        self.photo_mode = photo_mode

    # ---------------------------- Public API ---------------------------------
    async def run(self, raw_requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        norm = self._normalize_and_validate(raw_requests)
        agg = Aggregator()
        timings: Dict[str, Dict[str, Any]] = {}
        async with async_playwright() as pw:
            # Launch with aggressive anti-crash flags and stealth to avoid Facebook detection
            browser = await pw.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",  # Hide automation
                    "--disable-dev-shm-usage",  # Prevent shared memory issues
                    "--no-sandbox",  # Required for some environments
                    "--disable-setuid-sandbox",
                    "--disable-gpu",  # Prevent GPU crashes
                    "--disable-software-rasterizer",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-breakpad",
                    "--disable-component-extensions-with-background-pages",
                    "--disable-features=TranslateUI,BlinkGenPropertyTrees",
                    "--disable-ipc-flooding-protection",
                    "--disable-renderer-backgrounding",
                    "--enable-features=NetworkService,NetworkServiceInProcess",
                    "--force-color-profile=srgb",
                    "--metrics-recording-only",
                    "--no-first-run",
                    "--safebrowsing-disable-auto-update",
                    "--password-store=basic",
                    "--use-mock-keychain",
                    "--disable-accelerated-2d-canvas",
                    "--disable-accelerated-jpeg-decoding",
                    "--disable-accelerated-mjpeg-decode",
                    "--disable-accelerated-video-decode",
                ]
            )
            sem = asyncio.Semaphore(self.max_concurrency)

            async def runner(req: ScrapeRequest):
                async with sem:
                    key = f"{req.platform}:{req.username}"
                    started = time.time()
                    await self._process_one(agg, browser, req)
                    elapsed = time.time() - started
                    timings[key] = {"seconds": round(elapsed, 3)}

            try:
                # Lanzar concurrente si max_concurrency > 1
                if self.max_concurrency > 1:
                    await asyncio.gather(*(runner(r) for r in norm))
                else:
                    for r in norm:
                        await runner(r)
            finally:
                await browser.close()

        payload = agg.build_payload(roots_requested=len(norm))
        # Inyectar métricas de roots (opcional: se puede mover a meta detallada)
        if isinstance(payload, dict) and 'meta' in payload:
            payload['meta']['roots_timings'] = timings
            payload['meta']['max_concurrency'] = self.max_concurrency
        return payload

    # --------------------------- Internal Helpers ----------------------------
    def _normalize_and_validate(self, raw_requests: List[Dict[str, Any]]) -> List[ScrapeRequest]:
        if not raw_requests:
            raise ValueError("No roots provided")
        if len(raw_requests) > self.max_roots:
            raise ValueError(f"Max {self.max_roots} roots")
        norm: List[ScrapeRequest] = []
        for r in raw_requests:
            platform = (r.get('platform') or '').lower().strip()
            username = normalize_username(r.get('username'))
            max_photos = r.get('max_photos') or r.get('max_fotos') or 5
            if not valid_username(username):
                raise ValueError(f"Invalid username: {username}")
            norm.append(ScrapeRequest(platform=platform, username=username, max_photos=max_photos))
        return norm

    async def _process_one(self, agg: Aggregator, browser, req: ScrapeRequest) -> None:
        platform = req.platform
        scraper_cls = self.scraper_registry.get(platform)
        if not scraper_cls:
            agg.warnings.append({"code": "PLATFORM_UNSUPPORTED", "message": platform})
            return
        storage_state = self.storage_state_resolver(platform)
        if not storage_state:
            agg.warnings.append({"code": "ROOT_SKIPPED", "message": f"Missing storage_state for {platform}"})
            return
        
        # Helper to create fresh context+page
        async def create_context_and_page():
            context = await browser.new_context(
                storage_state=storage_state,
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='en-US',
            )
            # Stealth: hide webdriver flag
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            """)
            page = await context.new_page()
            return context, page
        
        context, page = await create_context_and_page()
        scraper: PlatformScraper = scraper_cls(page, platform)
        username = req.username
        try:
            await scraper.prepare_page()
            root_profile = await scraper.get_root_profile(username)
            # Normalizar/descargar foto de perfil root si procede
            if self.download_photos and root_profile.get('photo_url'):
                try:
                    root_profile['photo_url'] = await local_or_proxy_photo_url(
                        root_profile['photo_url'], root_profile.get('username'), mode=self.photo_mode, page=page, on_failure='empty'
                    )
                except Exception:
                    root_profile['photo_url'] = ''
            
            # Facebook-specific: recreate context for each list to avoid crashes
            if platform == 'facebook':
                followers = await self._fb_list_with_fresh_context(browser, storage_state, scraper_cls, username, 'followers')
                following = await self._fb_list_with_fresh_context(browser, storage_state, scraper_cls, username, 'following')
                friends = await self._fb_list_with_fresh_context(browser, storage_state, scraper_cls, username, 'friends')
                # Enable photos scraping for Facebook if max_photos > 0
                if req.max_photos > 0:
                    commenters = await self._fb_list_with_fresh_context(browser, storage_state, scraper_cls, username, 'commenters', req.max_photos)
                    reactors = await self._fb_list_with_fresh_context(browser, storage_state, scraper_cls, username, 'reactors', req.max_photos)
                else:
                    commenters = []
                    reactors = []
            else:
                followers = await scraper.get_followers(username)
                following = await scraper.get_following(username)
                friends = await scraper.get_friends(username)
                commenters = await scraper.get_commenters(username, req.max_photos)
                reactors = await scraper.get_reactors(username, req.max_photos)

            # Ingest root
            agg.add_root(make_profile(platform, root_profile['username'], root_profile.get('full_name'), root_profile.get('profile_url'), root_profile.get('photo_url'), (platform, username)))
            # Post-proceso de fotos en listas si se habilita
            if self.download_photos:
                followers = await self._ensure_photos_batch(followers, platform, page)
                following = await self._ensure_photos_batch(following, platform, page)
                friends = await self._ensure_photos_batch(friends, platform, page)
                commenters = await self._ensure_photos_batch(commenters, platform, page)
                reactors = await self._ensure_photos_batch(reactors, platform, page)

            self._ingest_list(agg, platform, username, followers, direction='followers')
            self._ingest_list(agg, platform, username, following, direction='following')
            self._ingest_list(agg, platform, username, friends, direction='friends')
            self._ingest_activity_list(agg, platform, username, commenters, rel_type='comentó')
            self._ingest_activity_list(agg, platform, username, reactors, rel_type='reaccionó')

            if self.persist:
                self._persist(platform, username, root_profile, followers, following, friends, commenters, reactors)
        except Exception as e:  # noqa: BLE001
            agg.warnings.append({"code": "PARTIAL_FAILURE", "message": f"{platform}:{username} {str(e)}"})
            logger.exception("orchestrator.scrape_error platform=%s username=%s", platform, username)
        finally:
            await context.close()

    async def _fb_list_with_fresh_context(self, browser, storage_state, scraper_cls, username: str, list_type: str, max_items: int = 0) -> List[dict]:
        """Execute a single Facebook list extraction with a fresh context to prevent crashes."""
        logger.info(f"orchestrator.fb_fresh_context list={list_type} username={username}")
        ctx = None
        try:
            ctx = await browser.new_context(
                storage_state=storage_state,
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='en-US',
            )
            await ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            """)
            pg = await ctx.new_page()
            scraper = scraper_cls(pg, 'facebook')
            
            if list_type == 'followers':
                result = await scraper.get_followers(username)
            elif list_type == 'following':
                result = await scraper.get_following(username)
            elif list_type == 'friends':
                result = await scraper.get_friends(username)
            elif list_type == 'commenters':
                result = await scraper.get_commenters(username, max_items)
            elif list_type == 'reactors':
                result = await scraper.get_reactors(username, max_items)
            else:
                result = []
            
            return result
        except Exception as e:
            logger.error(f"orchestrator.fb_fresh_context_error list={list_type} username={username} error={e}")
            return []
        finally:
            if ctx:
                try:
                    await ctx.close()
                except Exception:
                    pass

    # ------------------- Normalization & Ingestion ---------------------------
    def _normalize_user_item(self, platform: str, raw: Dict[str, Any]) -> Dict[str, Any]:  # noqa: D401
        from src.utils.url import extract_username_from_url, normalize_input_url
        if not isinstance(raw, dict):
            return {}
        username = raw.get('username') or raw.get('username_usuario') or raw.get('user') or raw.get('handle')
        full_name = raw.get('full_name') or raw.get('nombre_completo') or raw.get('nombre_usuario') or raw.get('name')
        profile_url = raw.get('profile_url') or raw.get('url_usuario') or raw.get('link_usuario') or raw.get('href')
        photo_url = raw.get('photo_url') or raw.get('foto_perfil') or raw.get('foto_usuario') or raw.get('image')
        if (not username) and profile_url:
            username = extract_username_from_url(platform, profile_url)
        if profile_url:
            profile_url = normalize_input_url(platform, profile_url)
        username = (username or '').strip().lstrip('@')
        full_name = full_name or username
        return {
            'username': username,
            'full_name': full_name,
            'profile_url': profile_url,
            'photo_url': photo_url,
        }

    def _ingest_list(self, agg: Aggregator, platform: str, root_username: str, items: List[Dict[str, Any]], *, direction: str):
        if not items:
            return
        for raw in items:
            norm = self._normalize_user_item(platform, raw)
            u = norm.get('username')
            if not u or not valid_username(u) or u == root_username:
                continue
            agg.add_profile(make_profile(platform, u, norm.get('full_name'), norm.get('profile_url'), norm.get('photo_url'), (platform, root_username)))
            if direction == 'followers':
                agg.add_relation(platform, u, root_username, REL_FOLLOWER)
            elif direction == 'following':
                agg.add_relation(platform, root_username, u, REL_FOLLOWING)
            elif direction == 'friends':
                agg.add_relation(platform, root_username, u, REL_FRIEND)
                agg.add_relation(platform, u, root_username, REL_FRIEND)

    def _ingest_activity_list(self, agg: Aggregator, platform: str, root_username: str, items: List[Dict[str, Any]], *, rel_type: str):
        if not items:
            return
        for raw in items:
            norm = self._normalize_user_item(platform, raw)
            u = norm.get('username')
            if not u or not valid_username(u) or u == root_username:
                continue
            agg.add_profile(make_profile(platform, u, norm.get('full_name'), norm.get('profile_url'), norm.get('photo_url'), (platform, root_username)))
            agg.add_relation(platform, u, root_username, rel_type)

    # --------------------------- Persistence ---------------------------------
    def _persist(self, platform: str, root_username: str, root_profile: Dict[str, Any], followers, following, friends, commenters, reactors):
        try:
            from api.services.aggregation import valid_username as _valid
            with get_conn() as conn:
                with conn.cursor() as cur:
                    upsert_profile(cur, platform, root_username, root_profile.get('full_name'), root_profile.get('profile_url'), root_profile.get('photo_url'))
                    # Followers: root -> fu (follower) [align with legacy scrape]
                    for rel_item in followers or []:
                        norm = self._normalize_user_item(platform, rel_item)
                        fu = norm.get('username')
                        if fu and _valid(fu) and fu != root_username:
                            upsert_profile(cur, platform, fu, norm.get('full_name'), norm.get('profile_url'), norm.get('photo_url'))
                            add_relationship(cur, platform, root_username, fu, 'follower')
                    # Following: root -> fu (following)
                    for rel_item in following or []:
                        norm = self._normalize_user_item(platform, rel_item)
                        fu = norm.get('username')
                        if fu and _valid(fu) and fu != root_username:
                            upsert_profile(cur, platform, fu, norm.get('full_name'), norm.get('profile_url'), norm.get('photo_url'))
                            add_relationship(cur, platform, root_username, fu, 'following')
                    # Friends (Facebook): single direction root -> fu (friend) [align with legacy]
                    if platform == 'facebook':
                        for rel_item in friends or []:
                            norm = self._normalize_user_item(platform, rel_item)
                            fu = norm.get('username')
                            if fu and _valid(fu) and fu != root_username:
                                upsert_profile(cur, platform, fu, norm.get('full_name'), norm.get('profile_url'), norm.get('photo_url'))
                                add_relationship(cur, platform, root_username, fu, 'friend')
                    # Commenters/Reactors: omit persistence in relationships table (they belong to comments/reactions tables)
                conn.commit()
        except Exception:  # noqa: BLE001
            logger.exception("orchestrator.persist_error platform=%s root=%s", platform, root_username)

    # --------------------------- Photos Helpers ------------------------------
    async def _ensure_photos_batch(self, items: List[Dict[str, Any]], platform: str, page) -> List[Dict[str, Any]]:
        if not items or platform not in ('instagram','facebook','x'):
            return items
        out: List[Dict[str, Any]] = []
        # Parámetros de recuperación og:image
        MAX_OG_FETCH = 40  # límite de perfiles sin foto a intentar
        og_fetch_count = 0
        for it in items:
            try:
                # Skip if already local or empty
                photo = it.get('photo_url') or it.get('foto_usuario') or it.get('foto_perfil') or it.get('foto')
                uname = it.get('username') or it.get('username_usuario')
                purl = it.get('profile_url') or it.get('link_usuario') or it.get('url_usuario')
                if not uname:
                    out.append(it); continue
                if not photo:
                    # Intento recuperación og:image si hay URL de perfil y no excedimos límite
                    if purl and og_fetch_count < MAX_OG_FETCH:
                        recovered = await self._recover_photo_via_og(purl, uname, page)
                        if recovered:
                            photo = recovered
                            # Guardar en estructura
                            it['photo_url'] = photo
                        og_fetch_count += 1
                    else:
                        out.append(it); continue
                if str(photo).startswith('/storage/'):
                    out.append(it); continue
                # Attempt download / proxy
                try:
                    local = await local_or_proxy_photo_url(photo, uname, mode=self.photo_mode, page=page, on_failure='empty')
                    # Write back into canonical key photo_url
                    if local:
                        if 'photo_url' in it:
                            it['photo_url'] = local
                        elif 'foto_usuario' in it:
                            it['foto_usuario'] = local
                        else:
                            it['photo_url'] = local
                except Exception:
                    pass
                out.append(it)
            except Exception:
                out.append(it)
        return out

    async def _recover_photo_via_og(self, profile_url: str, username: str, page) -> str:
        """Recupera la URL de imagen de perfil consultando el HTML y extrayendo meta og:image.
        Devuelve la URL directa (CDN) sin descargar; el flujo de descarga la procesará después.
        """
        try:
            resp = await page.request.get(profile_url, timeout=10000)
            if not resp.ok:
                return ''
            html = await resp.text()
            # Buscar meta property="og:image"
            m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if m:
                return m.group(1)
        except Exception:
            return ''
        return ''
