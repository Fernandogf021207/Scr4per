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
                pid = upsert_profile(cur, p.platform, p.username, p.full_name, p.profile_url, p.photo_url, p.facebook_id)
                conn.commit()
                schema = _schema(p.platform)
                # facebook_id column only exists in red_facebook.profiles
                fb_col = "facebook_id" if p.platform == "facebook" else "NULL AS facebook_id"
                cur.execute(
                    f"SELECT id, platform, username, full_name, profile_url, photo_url, {fb_col} "
                    f"FROM {schema}.profiles WHERE id=%s",
                    (pid,)
                )
                row = cur.fetchone()
                return Profile(**row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))