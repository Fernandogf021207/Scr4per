import asyncio
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from ..deps import storage_state_for
from ..db import get_conn
from ..repositories import upsert_profile, add_relationship
from .adapters import launch_browser, close_browser, get_adapter

logger = logging.getLogger('api.routers.multi_scrape')

USERNAME_REGEX = r'^[A-Za-z0-9._-]{2,60}$'

def _root_id(platform: str, username: str) -> str:
    return f"{platform}:{username}"


def _valid_username(u: str) -> bool:
    import re
    return bool(re.match(USERNAME_REGEX, u or ''))


def _merge_sources(existing: List[str], new_sources: List[str]) -> List[str]:
    return sorted(set(existing or []) | set(new_sources or []))


async def _process_root(root: Dict[str, Any], browser) -> Dict[str, Any]:
    start = time.perf_counter()
    platform = root["platform"]
    username = root["username"]
    headless = bool(root.get("headless", True))
    persist = bool(root.get("persist", True))
    strict_sessions = bool(root.get("strict_sessions", False))
    tenant = root.get("tenant")

    rid = _root_id(platform, username)
    warnings: List[Dict[str, str]] = []
    profiles_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    relations: List[Dict[str, Any]] = []

    # Storage-state check (lax policy by default)
    storage_path = storage_state_for(platform, tenant)
    if not storage_path or not os.path.isfile(storage_path):
        msg = f"{rid} missing storage_state"
        if strict_sessions:
            raise ValueError("STORAGE_STATE_MISSING")
        warnings.append({"code": "STORAGE_STATE_MISSING", "message": msg})
        elapsed = time.perf_counter() - start
        return {
            "root_id": rid,
            "profiles": [],
            "relations": [],
            "warnings": warnings,
            "timing_seconds": elapsed,
        }

    adapter = get_adapter(platform, browser, tenant)

    try:
        logger.info("root.start rid=%s platform=%s username=%s", rid, platform, username)
        # Root profile
        root_prof = await adapter.get_root_profile(username)
        root_prof["sources"] = [rid]
        key = (root_prof["platform"], root_prof["username"])
        if _valid_username(key[1]):
            profiles_map[key] = root_prof

        # Lists
        followers = await adapter.get_followers(username, int(root.get("max_photos") or 5))
        following = await adapter.get_following(username, int(root.get("max_photos") or 5))
        friends: List[Dict[str, Any]] = []
        if platform == 'facebook':
            friends = await adapter.get_friends(username)

        def add_profile(item: Dict[str, Any]):
            u = item.get("username")
            if not _valid_username(u) or u == username:
                return None
            k = (item["platform"], u)
            item["sources"] = _merge_sources(item.get("sources", []), [rid])
            if k in profiles_map:
                profiles_map[k]["sources"] = _merge_sources(profiles_map[k].get("sources", []), item["sources"]) 
            else:
                profiles_map[k] = item
            return u

        def add_relation(target_username: str, rel_type: str):
            if not target_username or target_username == username:
                return
            relations.append({
                "platform": platform,
                "source": username,
                "target": target_username,
                "type": rel_type,
            })

        for it in followers:
            tu = add_profile(it)
            if tu:
                add_relation(tu, 'follower')

        for it in following:
            tu = add_profile(it)
            if tu:
                add_relation(tu, 'following')

        if friends:
            for it in friends:
                tu = add_profile(it)
                if tu:
                    add_relation(tu, 'friend')

        # Persist per root (transaction)
        if persist and profiles_map:
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        # Ensure root first
                        upsert_profile(cur, platform, username, root_prof.get("full_name"), root_prof.get("profile_url"), root_prof.get("photo_url"))
                        for r in relations:
                            rel_type = r["type"]
                            tgt = r["target"]
                            if not _valid_username(tgt) or tgt == username:
                                continue
                            # Upsert related profile with whatever info we collected
                            p = profiles_map.get((platform, tgt))
                            upsert_profile(cur, platform, tgt, p.get("full_name") if p else None, p.get("profile_url") if p else None, p.get("photo_url") if p else None)
                            add_relationship(cur, platform, username, tgt, rel_type)
                        conn.commit()
            except Exception as db_ex:  # pragma: no cover
                logger.warning("root.db_warning rid=%s error=%s", rid, db_ex)
                warnings.append({"code": "DB_WARNING", "message": f"{rid} persistence issue: {db_ex}"})

        elapsed = time.perf_counter() - start
        logger.info("root.done rid=%s profiles=%d relations=%d", rid, len(profiles_map), len(relations))
        return {
            "root_id": rid,
            "profiles": list(profiles_map.values()),
            "relations": relations,
            "warnings": warnings,
            "timing_seconds": elapsed,
        }
    except Exception as e:  # pragma: no cover
        logger.exception("root.fail rid=%s error=%s", rid, e)
        warnings.append({"code": "PARTIAL_FAILURE", "message": f"{rid} {str(e)}"})
        elapsed = time.perf_counter() - start
        return {
            "root_id": rid,
            "profiles": list(profiles_map.values()),
            "relations": relations,
            "warnings": warnings,
            "timing_seconds": elapsed,
        }


async def multi_scrape_execute(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Orquestador principal de multi-scrape (MVP):
    - No realiza scraping real (los adapters se integrarán en siguientes iteraciones).
    - Construye perfiles raíz y estructura de respuesta compatible con schema_version=2.
    """
    roots: List[Dict[str, Any]] = request.get("roots", [])
    headless: bool = bool(request.get("headless", True))
    persist: bool = bool(request.get("persist", True))
    strict_sessions: bool = bool(request.get("strict_sessions", False))
    max_concurrency: int = int(request.get("max_concurrency") or (1 if len(roots) <= 1 else 3))
    tenant: Any = request.get("tenant")

    t0 = time.perf_counter()
    sem = asyncio.Semaphore(max_concurrency)

    run_id = secrets.token_hex(6)
    logger.info("multi_scrape.start rid=%s roots=%d", run_id, len(roots))

    browser = await launch_browser(headless=headless)
    try:
        async def _guarded(root):
            async with sem:
                # inject global flags into root for processing
                r = dict(root)
                r["headless"] = headless
                r["persist"] = persist
                r["strict_sessions"] = strict_sessions
                r["tenant"] = tenant
                return await _process_root(r, browser)

        tasks = [asyncio.create_task(_guarded(r)) for r in roots]
        results: List[Dict[str, Any]] = []
        for t in tasks:
            try:
                results.append(await t)
            except Exception as e:  # pragma: no cover
                rid = _root_id(roots[len(results)]["platform"], roots[len(results)]["username"]) if len(results) < len(roots) else ""
                results.append({
                    "root_id": rid,
                    "profiles": [],
                    "relations": [],
                    "warnings": [{"code": "PARTIAL_FAILURE", "message": str(e)}],
                    "timing_seconds": 0.0,
                })
    finally:
        await close_browser(browser)

    # Merge results
    root_profiles: List[str] = []
    profiles_map: Dict[tuple, Dict[str, Any]] = {}
    relations: List[Dict[str, Any]] = []
    warnings: List[Dict[str, str]] = []
    roots_timings: Dict[str, Dict[str, float]] = {}

    for res in results:
        rid = res.get("root_id")
        if rid:
            root_profiles.append(rid)
            roots_timings[rid] = {"seconds": float(res.get("timing_seconds", 0.0))}
        for w in res.get("warnings", []):
            warnings.append(w)
        for p in res.get("profiles", []):
            key = (p["platform"], p["username"])
            if key not in profiles_map:
                profiles_map[key] = p
            else:
                existing = profiles_map[key]
                # Acumular sources de manera idempotente y ordenada
                existing_sources = set(existing.get("sources", [])) | set(p.get("sources", []))
                profiles_map[key]["sources"] = sorted(existing_sources)
        relations.extend(res.get("relations", []))

    profiles = list(profiles_map.values())
    generated_at = datetime.now(timezone.utc).isoformat()
    build_ms = int((time.perf_counter() - t0) * 1000)

    response = {
        "schema_version": 2,
        "root_profiles": root_profiles,
        "profiles": profiles,
        "relations": relations,
        "warnings": warnings,
        "meta": {
            "schema_version": 2,
            "roots_requested": len(roots),
            "roots_processed": len([r for r in results if r.get("root_id")]),
            "generated_at": generated_at,
            "build_ms": build_ms,
            "roots_timings": roots_timings,
            "max_concurrency": max_concurrency,
        },
    }
    logger.info("multi_scrape.done rid=%s profiles=%d relations=%d", run_id, len(profiles), len(relations))
    return response
