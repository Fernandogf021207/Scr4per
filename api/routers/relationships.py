from fastapi import APIRouter, HTTPException
from ..db import get_conn
from ..repositories import add_relationship
from ..schemas import RelationshipIn

router = APIRouter()

@router.post("/relationships")
def create_relationship(r: RelationshipIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                rel_id = add_relationship(cur, r.platform, r.owner_username, r.related_username, r.rel_type)
                conn.commit()
                return {"inserted": bool(rel_id), "relationship_id": rel_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))