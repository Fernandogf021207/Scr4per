from fastapi import APIRouter, HTTPException
from ..db import get_conn
from ..repositories import add_comment, add_post
from ..schemas import CommentIn
from src.utils.url import normalize_post_url

router = APIRouter()

@router.post("/comments")
def create_comment(c: CommentIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                try:
                    post_url = normalize_post_url(c.platform, c.post_url)
                    comment_id = add_comment(cur, c.platform, post_url, c.commenter_username)
                except ValueError as ve:
                    raise HTTPException(status_code=400, detail=str(ve))
                conn.commit()
                return {"inserted": bool(comment_id), "comment_id": comment_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))