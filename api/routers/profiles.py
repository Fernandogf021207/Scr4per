from fastapi import APIRouter, HTTPException
from ..db import get_conn
from ..deps import _schema
from ..schemas import ProfileIn, Profile
from .. import repositories as repo

router = APIRouter()

@router.post("/profiles", response_model=Profile)
def create_or_update_profile(p: ProfileIn):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                pid = repo.upsert_profile(cur, p.platform, p.username, p.full_name, p.profile_url, p.photo_url)
                conn.commit()
                schema = _schema(p.platform)
                # Select by platform+username to ease testing and avoid depending on returned id
                cur.execute(
                    f"SELECT id, platform, username, full_name, profile_url, photo_url FROM {schema}.profiles WHERE platform=%s AND username=%s",
                    (p.platform, p.username)
                )
                row = cur.fetchone()
                return Profile(**row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))