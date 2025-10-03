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

from playwright.async_api import async_playwright

from src.scrapers.base import PlatformScraper
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
    ) -> None:
        self.scraper_registry = scraper_registry
        self.storage_state_resolver = storage_state_resolver
        self.max_roots = max_roots
        self.persist = persist
        self.headless = headless
        self.max_concurrency = max_concurrency

    # ---------------------------- Public API ---------------------------------
    async def run(self, raw_requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        norm = self._normalize_and_validate(raw_requests)
        agg = Aggregator()
        timings: Dict[str, Dict[str, Any]] = {}
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.headless)
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
        context = await browser.new_context(storage_state=storage_state)
        page = await context.new_page()
        scraper: PlatformScraper = scraper_cls(page, platform)
        username = req.username
        try:
            await scraper.prepare_page()
            root_profile = await scraper.get_root_profile(username)
            followers = await scraper.get_followers(username)
            following = await scraper.get_following(username)
            friends = await scraper.get_friends(username)
            commenters = await scraper.get_commenters(username, req.max_photos)
            reactors = await scraper.get_reactors(username, req.max_photos)

            # Ingest root
            agg.add_root(make_profile(platform, root_profile['username'], root_profile.get('full_name'), root_profile.get('profile_url'), root_profile.get('photo_url'), (platform, username)))
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
                    for rel_item in (followers + following + friends + commenters + reactors):
                        norm = self._normalize_user_item(platform, rel_item)
                        fu = norm.get('username')
                        if fu and _valid(fu):
                            upsert_profile(cur, platform, fu, norm.get('full_name'), norm.get('profile_url'), norm.get('photo_url'))
                            # Relationship direction mapping replicates ingestion logic
                            rel_type_db = rel_item.get('_rel_type_db')
                            if rel_type_db and rel_item.get('_rel_source_db') and rel_item.get('_rel_target_db'):
                                add_relationship(cur, platform, rel_item.get('_rel_source_db'), rel_item.get('_rel_target_db'), rel_type_db)
                conn.commit()
        except Exception:  # noqa: BLE001
            logger.exception("orchestrator.persist_error platform=%s root=%s", platform, root_username)
