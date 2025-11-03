import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx
import io

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_SCHEMES = {"http", "https"}


def _is_disallowed_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        )
    except Exception:
        return True


def _host_resolves_to_disallowed(host: str) -> bool:
    try:
        # If host is already an IP
        try:
            if _is_disallowed_ip(host):
                return True
        except Exception:
            pass
        infos = socket.getaddrinfo(host, None)
        for family, _type, _proto, _canonname, sockaddr in infos:
            ip = sockaddr[0]
            if _is_disallowed_ip(ip):
                return True
        return False
    except Exception:
        # On resolution failure, be conservative
        return True

router = APIRouter()

@router.get("/proxy-image")
async def proxy_image(url: str = Query(..., description="URL de la imagen externa")):
    # 1) Validar esquema y host
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=400, detail="URL inválida")

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise HTTPException(status_code=400, detail="Esquema no permitido (solo http/https)")

    host = parsed.hostname or ""
    if not host:
        raise HTTPException(status_code=400, detail="Host inválido")

    if _host_resolves_to_disallowed(host):
        raise HTTPException(status_code=403, detail="Destino no permitido")

    # 2) Descargar con timeout y límites de tamaño
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="La URL no apunta a una imagen válida")

            # Enforce size limit (buffer up to MAX_IMAGE_BYTES)
            data = resp.content
            if data is None:
                raise HTTPException(status_code=502, detail="Respuesta inválida del origen")
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="Imagen demasiado grande")
            return StreamingResponse(io.BytesIO(data), media_type=content_type)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener la imagen: {str(e)}")