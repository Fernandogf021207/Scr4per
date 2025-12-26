from fastapi import APIRouter, HTTPException, Header
from typing import Any, Dict
import logging

from ..schemas import MultiScrapeRequest
from .. import services  # noqa: F401
from ..services import multi_scrape as ms

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/multi-scrape")
async def multi_scrape(request: MultiScrapeRequest, x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")) -> Dict[str, Any]:
    try:
        # Pasamos un dict simple para facilitar monkeypatch en tests
        payload = request.dict()
        if x_tenant_id:
            payload["tenant"] = x_tenant_id
        data = await ms.multi_scrape_execute(payload)
        return data
    except HTTPException:
        raise
    except ValueError as ve:
        # Errores de sesión/almacenamiento u otras validaciones en tiempo de ejecución
        detail = str(ve)
        if 'STORAGE_STATE_MISSING' in detail:
            raise HTTPException(status_code=400, detail='STORAGE_STATE_MISSING')
        raise HTTPException(status_code=400, detail=detail)
    except ConnectionError as ce:
        # Error de conexión (FTP, red, etc.)
        logger.error(f"Connection error in multi_scrape: {ce}", exc_info=True)
        raise HTTPException(status_code=503, detail="CONNECTION_ERROR")
    except Exception as e:
        # Falla no controlada en el orquestador — loguear el error completo
        logger.exception(f"Unexpected error in multi_scrape: {e}")
        raise HTTPException(status_code=500, detail="ORCHESTRATOR_ERROR")
