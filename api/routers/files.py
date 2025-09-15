import os
import re
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from paths import IMAGES_DIR, PUBLIC_IMAGES_PREFIX_PRIMARY, PUBLIC_IMAGES_PREFIX_COMPAT, ensure_dirs

router = APIRouter()

"""Almacenamiento de imágenes.

Se usa el directorio raíz del proyecto: ./data/storage/images
La URL pública (contrato actual) permanece: /data/storage/images/<file>
Mount de compatibilidad adicional: /storage/images/<file>
Esto permite eliminar la carpeta api/data/storage.
"""
ensure_dirs()

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
        dest_path = os.path.join(IMAGES_DIR, name)

        # Stream save
        content = await file.read()
        with open(dest_path, 'wb') as f:
            f.write(content)

        # Contrato: devolver prefijo primario. El compat se mantiene montado en main.
        return {"url": f"{PUBLIC_IMAGES_PREFIX_PRIMARY}/{name}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
