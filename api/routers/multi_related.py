"""Multi-Related Router: Endpoint for graph extraction from database.

POST /multi-related
  - Extracts subgraph from DB starting from multiple root profiles
  - Does NOT trigger new scraping
  - Returns graph structure compatible with multi-scrape response
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from typing import Any
import uuid
import logging

from ..schemas_multi import MultiRelatedRequest, MultiRelatedResponse
from ..services import multi_related as mr

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/multi-related", tags=["multi-related"])


@router.post("", response_model=MultiRelatedResponse)
async def multi_related(payload: MultiRelatedRequest) -> Any:
    """Extract a subgraph from the database starting from multiple root profiles.
    
    This endpoint performs incremental enrichment by reading already-scraped data
    from the database. It does NOT trigger new web scraping.
    
    **Use cases:**
    - Get full relationship graph for multiple profiles without re-scraping
    - Explore connections between profiles (friends of friends)
    - Export data for visualization or analysis
    - Incremental updates after new profiles are scraped
    
    **Parameters:**
    - `roots`: List of 1-10 profiles to start from (platform + username)
    - `depth`: How many levels of connections to include (1-3)
      - 1 = direct connections only
      - 2 = friends of friends
      - 3 = 3rd degree connections
    - `include_inter_root_relations`: Whether to include direct relationships between roots
    - `relation_types`: Filter by specific types (follower, following, friend, etc.)
    - `max_profiles`: Limit total profiles returned (performance control)
    
    **Response:**
    - Compatible with multi-scrape response format
    - `profiles`: All profiles in the subgraph with metadata
    - `relations`: All relationships between profiles
    - `meta`: Query statistics and execution info
    - `warnings`: Non-fatal issues (e.g., root not found in DB)
    
    **Example request:**
    ```json
    {
      "roots": [
        {"platform": "instagram", "username": "user1"},
        {"platform": "instagram", "username": "user2"}
      ],
      "depth": 2,
      "include_inter_root_relations": true,
      "max_profiles": 500
    }
    ```
    """
    request_id = uuid.uuid4().hex[:12]
    logger.info(f"multi_related.start rid={request_id} roots={len(payload.roots)} depth={payload.depth}")
    
    try:
        # Convert request to dict for service layer
        request_data = {
            'roots': payload.roots,
            'depth': payload.depth,
            'include_inter_root_relations': payload.include_inter_root_relations,
            'relation_types': payload.relation_types,
            'max_profiles': payload.max_profiles,
        }

        data = await mr.multi_related_execute(request_data)
        
        # Inject request ID into meta
        if isinstance(data, dict) and 'meta' in data and isinstance(data['meta'], dict):
            data['meta']['request_id'] = request_id
        
        logger.info(
            f"multi_related.done rid={request_id} "
            f"profiles={len(data.get('profiles', []))} "
            f"relations={len(data.get('relations', []))} "
            f"truncated={data.get('meta', {}).get('truncated', False)}"
        )
        
        return data
        
    except HTTPException:
        logger.warning(f"multi_related.http_error rid={request_id}")
        raise
    except Exception as e:
        logger.exception(f"multi_related.fail rid={request_id} error={e}")
        raise HTTPException(
            status_code=500, 
            detail={
                "code": "INTERNAL_ERROR",
                "message": str(e),
                "request_id": request_id
            }
        )
