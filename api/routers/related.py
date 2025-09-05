from typing import List, Dict, Any, Literal
from fastapi import APIRouter, HTTPException, Path
from ..db import get_conn
from ..deps import _schema

router = APIRouter()

def _to_spanish_rel(rel_type: str) -> str:
    mapping = {
        'follower': 'seguidor',
        'following': 'seguido',
        'followed': 'seguido',
        'friend': 'amigo',
        'commented': 'comentó',
        'reacted': 'reaccionó',
    }
    return mapping.get((rel_type or '').lower(), rel_type)

def _build_related_from_db(cur, platform: str, owner_username: str) -> List[Dict[str, Any]]:
    schema = _schema(platform)
    cur.execute(
        f"SELECT id FROM {schema}.profiles WHERE platform=%s AND username=%s",
        (platform, owner_username)
    )
    row = cur.fetchone()
    if not row:
        return []
    owner_id = row["id"]

    relacionados: List[Dict[str, Any]] = []

    cur.execute(
        f"""
        SELECT DISTINCT p.username, p.full_name, p.profile_url, p.photo_url, r.rel_type
        FROM {schema}.relationships r
        JOIN {schema}.profiles p ON p.id = r.related_profile_id
        WHERE r.owner_profile_id = %s
        """,
        (owner_id,)
    )
    for r in cur.fetchall() or []:
        relacionados.append({
            "username": r.get("username"),
            "full_name": r.get("full_name"),
            "profile_url": r.get("profile_url"),
            "photo_url": r.get("photo_url"),
            "tipo de relacion": _to_spanish_rel(r.get("rel_type")),
            "updated_at": r.get("updated_at"),
        })

    try:
        cur.execute(
            f"""
            SELECT DISTINCT p.username, p.full_name, p.profile_url, p.photo_url
            FROM {schema}.comments c
            JOIN {schema}.posts po ON po.id = c.post_id
            JOIN {schema}.profiles p ON p.id = c.commenter_profile_id
            WHERE po.owner_profile_id = %s
            """,
            (owner_id,)
        )
        for r in cur.fetchall() or []:
            relacionados.append({
                "username": r.get("username"),
                "full_name": r.get("full_name"),
                "profile_url": r.get("profile_url"),
                "photo_url": r.get("photo_url"),
                "tipo de relacion": 'comentó',
                "updated_at": r.get("updated_at"),
            })
    except Exception:
        pass

    try:
        cur.execute(
            f"""
            SELECT DISTINCT p.username, p.full_name, p.profile_url, p.photo_url
            FROM {schema}.reactions rx
            JOIN {schema}.posts po ON po.id = rx.post_id
            JOIN {schema}.profiles p ON p.id = rx.reactor_profile_id
            WHERE po.owner_profile_id = %s
            """,
            (owner_id,)
        )
        for r in cur.fetchall() or []:
            relacionados.append({
                "username": r.get("username"),
                "full_name": r.get("full_name"),
                "profile_url": r.get("profile_url"),
                "photo_url": r.get("photo_url"),
                "tipo de relacion": 'reaccionó',
                "updated_at": r.get("updated_at"),
            })
    except Exception:
        pass

    return relacionados

@router.get("/related/{platform}/{username}")
def get_related(
    platform: Literal['x','instagram','facebook'] = Path(...),
    username: str = Path(...)
):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                relacionados = _build_related_from_db(cur, platform, username)
                schema = _schema(platform)
                cur.execute(
                    f"SELECT platform, username, full_name, profile_url, photo_url, updated_at "
                    f"FROM {schema}.profiles WHERE platform=%s AND username=%s",
                    (platform, username)
                )
                objetivo = cur.fetchone() or {"platform": platform, "username": username}
        return {"Perfil objetivo": objetivo, "Perfiles relacionados": relacionados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))