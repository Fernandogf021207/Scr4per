from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from typing import Any

from ..schemas_multi import MultiScrapeRequest, MultiScrapeResponse
from ..services.multi_scrape import multi_scrape_execute

router = APIRouter(prefix="/multi-scrape", tags=["multi-scrape"])

@router.post("", response_model=MultiScrapeResponse)
async def multi_scrape(payload: MultiScrapeRequest) -> Any:
    try:
        data = await multi_scrape_execute([
            {"platform": r.platform, "username": r.username, "max_photos": r.max_photos} for r in payload.roots
        ])
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code":"INTERNAL_ERROR","message": str(e)})
