import os
import re
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from paths import IMAGES_DIR, PUBLIC_IMAGES_PREFIX_PRIMARY, PUBLIC_IMAGES_PREFIX_COMPAT, ensure_dirs
from src.utils.ftp_storage import get_ftp_client
import logging
from io import BytesIO

router = APIRouter()
logger = logging.getLogger(__name__)

_IMAGES_SUBDIR = os.path.join('..', 'data', 'storage', 'images')

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


@router.get("/scraped-image/{platform}/{username}/{filename}")
async def serve_scraped_image(platform: str, username: str, filename: str):
    """
    Serve images from FTP storage.
    Path format: /files/scraped-image/{platform}/{username}/{filename}
    Maps to FTP: rs/{platform}/{username}/images/{filename}
    """
    try:
        ftp = get_ftp_client()
        
        # Download file from FTP into memory
        file_data = ftp.download(platform, username, 'images', filename)
        
        if not file_data:
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Determine content type from extension
        ext = os.path.splitext(filename)[1].lower()
        content_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp',
        }
        content_type = content_type_map.get(ext, 'image/jpeg')
        
        # Return as streaming response with cache headers
        return StreamingResponse(
            BytesIO(file_data),
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                "Content-Disposition": f'inline; filename="{filename}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving image from FTP: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving image: {str(e)}")
