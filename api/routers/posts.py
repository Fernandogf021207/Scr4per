from fastapi import APIRouter, HTTPException
from ..db import get_conn
from ..repositories import add_post
from ..schemas import PostIn
from src.utils.url import normalize_post_url

router = APIRouter()

@router.post("/posts")
def create_post(p: PostIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                post_url = normalize_post_url(p.platform, p.post_url)
                post_id = add_post(cur, p.platform, p.owner_username, post_url)
                conn.commit()
                return {"inserted": bool(post_id), "post_id": post_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))