from __future__ import annotations
import os
import json
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from src.scrapers.config_runtime import get as cfg_get

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _platforms() -> Dict[str, str]:
    """Return mapping platform -> storage_state absolute path."""
    def p(platform: str, default_rel: str) -> str:
        path = cfg_get(platform, 'storage_state_path', default_rel)
        # Make absolute from repo root
        if not os.path.isabs(path):
            from paths import REPO_ROOT
            path = os.path.join(REPO_ROOT, path)
        return path

    return {
        'instagram': p('instagram', 'data/storage/instagram_storage_state.json'),
        'facebook': p('facebook', 'data/storage/facebook_storage_state.json'),
        'x': p('x', 'data/storage/x_storage_state.json'),
    }


def _file_info(path: str) -> Dict[str, Any]:
    exists = os.path.isfile(path)
    info: Dict[str, Any] = {
        'path': path,
        'exists': exists,
        'size_bytes': None,
        'modified_at': None,
    }
    if exists:
        st = os.stat(path)
        info['size_bytes'] = st.st_size
        info['modified_at'] = datetime.fromtimestamp(st.st_mtime).isoformat()
    return info


@router.get("/", response_model=dict)
def list_sessions() -> Dict[str, Any]:
    """Return status for Instagram, Facebook and X session files."""
    mapping = _platforms()
    return {k: _file_info(v) for k, v in mapping.items()}


@router.get("/{platform}", response_model=dict)
def get_session(platform: str) -> Dict[str, Any]:
    mapping = _platforms()
    if platform not in mapping:
        raise HTTPException(status_code=404, detail="Unknown platform")
    return _file_info(mapping[platform])


@router.get("/{platform}/download")
def download_session(platform: str):
    mapping = _platforms()
    if platform not in mapping:
        raise HTTPException(status_code=404, detail="Unknown platform")
    path = mapping[platform]
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Session file not found")
    return FileResponse(path, media_type='application/json', filename=os.path.basename(path))


@router.put("/{platform}", response_model=dict)
def put_session_json(platform: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Save JSON storage_state sent in request body."""
    mapping = _platforms()
    if platform not in mapping:
        raise HTTPException(status_code=404, detail="Unknown platform")
    path = mapping[platform]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Basic validation: must include cookies array or origins
    if not isinstance(payload, dict) or not ("cookies" in payload or "origins" in payload):
        raise HTTPException(status_code=400, detail="Invalid storage_state payload")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return _file_info(path)


@router.post("/{platform}/upload", response_model=dict)
async def upload_session_file(platform: str, file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload a storage_state JSON file."""
    mapping = _platforms()
    if platform not in mapping:
        raise HTTPException(status_code=404, detail="Unknown platform")
    if not file.filename.lower().endswith('.json'):
        raise HTTPException(status_code=400, detail="Only .json files are accepted")
    path = mapping[platform]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = await file.read()
    try:
        data = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    if not isinstance(data, dict) or not ("cookies" in data or "origins" in data):
        raise HTTPException(status_code=400, detail="Invalid storage_state format")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return _file_info(path)
