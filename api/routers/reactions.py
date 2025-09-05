from fastapi import APIRouter, HTTPException
from ..db import get_conn
from ..repositories import add_reaction, add_post
from ..schemas import ReactionIn
from src.utils.url import normalize_post_url

router = APIRouter()

@router.post("/reactions")
def create_reaction(r: ReactionIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    post_url = normalize_post_url(r.platform, r.post_url)
                    reaction_id = add_reaction(cur, r.platform, post_url, r.reactor_username, r.reaction_type)
                except ValueError as ve:
                    raise HTTPException(status_code=400, detail=str(ve))
                conn.commit()
                return {"inserted": bool(reaction_id), "reaction_id": reaction_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))