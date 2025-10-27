import os, json
from typing import Literal
from fastapi import APIRouter, HTTPException
from psycopg2.extras import Json
from ..db import get_conn
from ..deps import _schema
from paths import GRAPH_SESSION_DIR, REPO_ROOT, ensure_dirs

router = APIRouter()

@router.get("/graph-session/{platform}/{owner_username}")
def load_graph_session(platform: Literal['x','instagram','facebook'], owner_username: str):
    try:
        schema = _schema(platform)
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                  SELECT elements, elements_path, style, layout, updated_at
                  FROM {schema}.graph_sessions
                  WHERE owner_username=%s
                """, (owner_username,))
                row = cur.fetchone()
                if not row:
                    # 404 is clearer for caller than silently returning null
                    from fastapi import status
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="graph_session not found")
                elements = row.get('elements')
                path = row.get('elements_path')
                if path:
                    try:
                        # paths.elements_path is stored relative to REPO_ROOT
                        full_path = path if os.path.isabs(path) else os.path.join(REPO_ROOT, path)
                        with open(full_path, 'r', encoding='utf-8') as fh:
                            elements = json.load(fh)
                    except Exception:
                        pass
                row['elements'] = elements
                return row
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/graph-session")
def save_graph_session(body: dict):
    try:
        platform = body.get("platform")
        owner_username = body.get("owner_username")
        elements = body.get("elements") or {}
        style = body.get("style")
        layout = body.get("layout")
        schema = _schema(platform)
        # Use centralized paths to avoid drifting directories
        ensure_dirs()
        base_dir = GRAPH_SESSION_DIR
        os.makedirs(base_dir, exist_ok=True)

        filename = f"{platform}__{owner_username}.json"
        tmp_path = os.path.join(base_dir, filename + ".tmp")
        final_path = os.path.join(base_dir, filename)
        with open(tmp_path, 'w', encoding='utf-8') as fh:
            json.dump(elements, fh, ensure_ascii=False)
        os.replace(tmp_path, final_path)
        # Guardamos la ruta relativa respecto a la raíz del repositorio para futuras lecturas
        rel_path = os.path.relpath(final_path, start=REPO_ROOT)

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO {schema}.graph_sessions (owner_username, elements, style, layout, elements_path, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (owner_username) DO UPDATE
                    SET elements = EXCLUDED.elements,
                        style = EXCLUDED.style,
                        layout = EXCLUDED.layout,
                        elements_path = EXCLUDED.elements_path,
                        updated_at = NOW()
                    RETURNING id, owner_username, updated_at;
                """, (owner_username, Json(elements), Json(style), Json(layout), rel_path))
                conn.commit()
                return cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))