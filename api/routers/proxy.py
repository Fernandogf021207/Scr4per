from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx
import io

router = APIRouter()

@router.get("/proxy-image")
async def proxy_image(url: str = Query(..., description="URL de la imagen externa")):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="La URL no apunta a una imagen válida")
            return StreamingResponse(io.BytesIO(resp.content), media_type=content_type)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener la imagen: {str(e)}")