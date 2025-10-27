from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from typing import Any

from ..schemas_multi import MultiScrapeRequest, MultiScrapeResponse
from ..services import multi_scrape as ms
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/multi-scrape", tags=["multi-scrape"])

@router.post("", response_model=MultiScrapeResponse)
async def multi_scrape(payload: MultiScrapeRequest) -> Any:
    request_id = uuid.uuid4().hex[:12]
    logger.info(f"multi_scrape.start rid={request_id} roots={len(payload.roots)}")
    try:
        data = await ms.multi_scrape_execute([
            {"platform": r.platform, "username": r.username, "max_photos": r.max_photos} for r in payload.roots
        ])
        # Inject correlation id into meta if present
        if isinstance(data, dict) and 'meta' in data and isinstance(data['meta'], dict):
            data['meta']['request_id'] = request_id
        logger.info(f"multi_scrape.done rid={request_id} profiles={len(data.get('profiles',{}))} relations={len(data.get('relations',[]))}")
        return data
    except HTTPException:
        logger.warning(f"multi_scrape.http_error rid={request_id}")
        raise
    except Exception as e:
        logger.exception(f"multi_scrape.fail rid={request_id} error={e}")
        raise HTTPException(status_code=500, detail={"code":"INTERNAL_ERROR","message": str(e),"request_id":request_id})
