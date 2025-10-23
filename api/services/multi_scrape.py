from __future__ import annotations
from typing import List, Dict, Any

from fastapi import HTTPException
import os

from .aggregation import normalize_username, valid_username
from ..deps import storage_state_for
from src.scrapers.facebook.adapter import FacebookScraperAdapter
from src.scrapers.instagram.adapter import InstagramScraperAdapter
from src.scrapers.x.adapter import XScraperAdapter
from src.scrapers.orchestrator import ScrapeOrchestrator

SCRAPER_REGISTRY = {
    'facebook': FacebookScraperAdapter,
    'instagram': InstagramScraperAdapter,
    'x': XScraperAdapter,
}

# Reuse existing scraper functions (import here to avoid circulars)
MAX_ROOTS = 5  # mantiene compatibilidad; ahora configurable al crear el orquestador
DEFAULT_MAX_CONCURRENCY = 3  # valor inicial para futura parametrización externa

async def multi_scrape_execute(requests: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Validación ligera antes de delegar (evita levantar playwright si ya falla)
    if not requests:
        raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": "No roots provided"})
    if len(requests) > MAX_ROOTS:
        raise HTTPException(status_code=422, detail={"code": "LIMIT_EXCEEDED", "message": f"Max {MAX_ROOTS} roots"})
    for r in requests:
        if not valid_username(normalize_username(r.get('username'))):
            raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": f"Invalid username: {r.get('username')}"})

    headless_env = (os.getenv('SCRAPER_HEADLESS', 'true').lower() == 'true')
    orchestrator = ScrapeOrchestrator(
        scraper_registry=SCRAPER_REGISTRY,
        storage_state_resolver=lambda p: storage_state_for(p),
        max_roots=MAX_ROOTS,
        persist=True,
        headless=headless_env,
        max_concurrency=DEFAULT_MAX_CONCURRENCY if len(requests) > 1 else 1,
        download_photos=True,
        photo_mode='download',  # podría hacerse configurable luego
    )
    try:
        return await orchestrator.run(requests)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail={"code": "VALIDATION_ERROR", "message": str(ve)})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "ORCHESTRATOR_ERROR", "message": str(e)})


"""Legacy helpers (_scrape_one, _ingest_*) removidos: responsabilidad movida al orquestador central."""
