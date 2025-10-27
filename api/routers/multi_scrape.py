from fastapi import APIRouter, HTTPException
from typing import Any, Dict

from ..schemas import MultiScrapeRequest
from .. import services  # noqa: F401
from ..services import multi_scrape as ms

router = APIRouter()


@router.post("/multi-scrape")
async def multi_scrape(request: MultiScrapeRequest) -> Dict[str, Any]:
    try:
        # Pasamos un dict simple para facilitar monkeypatch en tests
        payload = request.dict()
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
    except Exception as e:  # noqa: F841
        # Falla no controlada en el orquestador
        raise HTTPException(status_code=500, detail="ORCHESTRATOR_ERROR")
