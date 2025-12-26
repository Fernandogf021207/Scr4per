import os, json
import logging
from typing import Literal
from fastapi import APIRouter, HTTPException
from psycopg2.extras import Json
from ..db import get_conn
from ..deps import _schema
from paths import GRAPH_SESSION_DIR, REPO_ROOT, ensure_dirs
from src.utils.ftp_storage import get_ftp_client

router = APIRouter()
logger = logging.getLogger(__name__)

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
                
                # Try loading from FTP if path is in new format (platform/username/graphs/file.json)
                if path and '/' in path:
                    try:
                        # Parse FTP path: red_x/username/graphs/filename.json
                        parts = path.split('/')
                        if len(parts) >= 4 and parts[2] == 'graphs':
                            platform_ftp = parts[0]  # e.g., "red_x"
                            username_ftp = parts[1]
                            filename = parts[3]
                            
                            ftp = get_ftp_client()
                            json_data = ftp.download(platform_ftp, username_ftp, 'graphs', filename)
                            if json_data:
                                elements = json.loads(json_data.decode('utf-8'))
                                logger.info(f"Loaded graph from FTP: {path}")
                    except Exception as e:
                        logger.warning(f"Failed to load from FTP ({path}): {e}, falling back to local or DB")
                
                # Fallback to local file if path is old format
                elif path:
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
        
        # Map platform to FTP directory name (red_x, red_instagram, red_facebook)
        platform_ftp = f"red_{platform}"
        filename = f"{platform}__{owner_username}.json"
        
        # Try uploading to FTP first
        ftp_path = None
        try:
            ftp = get_ftp_client()
            json_bytes = json.dumps(elements, ensure_ascii=False).encode('utf-8')
            ftp.upload(platform_ftp, owner_username, 'graphs', filename, json_bytes)
            # Store FTP path in format: red_x/username/graphs/filename.json
            ftp_path = f"{platform_ftp}/{owner_username}/graphs/{filename}"
            logger.info(f"Saved graph to FTP: {ftp_path}")
        except Exception as e:
            logger.error(f"Failed to upload graph to FTP: {e}, falling back to local storage")
            # Fallback to local file storage
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            base_dir = os.path.join(repo_root, '..', 'data', 'storage', 'graph_session')
            os.makedirs(base_dir, exist_ok=True)
            tmp_path = os.path.join(base_dir, filename + ".tmp")
            final_path = os.path.join(base_dir, filename)
            with open(tmp_path, 'w', encoding='utf-8') as fh:
                json.dump(elements, fh, ensure_ascii=False)
            os.replace(tmp_path, final_path)
            ftp_path = os.path.relpath(final_path, start=REPO_ROOT)

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
                """, (owner_username, Json(elements), Json(style), Json(layout), ftp_path))
                conn.commit()
                return cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))