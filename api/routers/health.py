from fastapi import APIRouter, HTTPException
from ..db import get_conn

router = APIRouter()

@router.get("/health")
def health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                ok = cur.fetchone()["ok"]
        return {"status": "ok", "db": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))