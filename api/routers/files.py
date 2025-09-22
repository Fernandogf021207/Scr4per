import os
import re
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()

_IMAGES_SUBDIR = os.path.join('..', 'data', 'storage', 'images')

# Ensure directory exists at import (safe even if it already exists)
os.makedirs(_IMAGES_SUBDIR, exist_ok=True)

_filename_safe_re = re.compile(r"[^a-zA-Z0-9._-]+")

def _safe_ext(filename: str) -> str:
    _, ext = os.path.splitext(filename or '')
    if not ext:
        return '.jpg'
    # Basic guard: normalize weird extensions
    ext = _filename_safe_re.sub('', ext)
    if not ext.startswith('.'):
        ext = '.' + ext
    return ext[:10] or '.jpg'

@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    try:
        # Validate MIME type
        ctype = file.content_type or ''
        if not ctype.startswith('image/'):
            raise HTTPException(status_code=400, detail='El archivo debe ser una imagen')

        ext = _safe_ext(file.filename)
        name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(_IMAGES_SUBDIR, name)

        # Stream save
        content = await file.read()
        with open(dest_path, 'wb') as f:
            f.write(content)

        # Return public URL (served by /storage mount)
        return {"url": f"/storage/images/{name}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
