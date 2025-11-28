import os
import re
from typing import Optional
import httpx
from urllib.parse import quote_plus, urlencode
import asyncio
from paths import IMAGES_DIR, PUBLIC_IMAGES_PREFIX_PRIMARY, ensure_dirs


def _safe_filename(name: str) -> str:
    """Sanitize a username for filesystem use."""
    name = name or "user"
    # Keep alnum, dash, underscore, dot; replace others with '_'
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return safe[:100]  # avoid extremely long filenames


def _extension_from_headers(content_type: Optional[str], url: str) -> str:
    """Choose a reasonable file extension from content-type or URL.

    Falls back to .jpg if unknown.
    """
    ct = (content_type or "").lower()
    if "/" in ct:
        main, sub = ct.split("/", 1)
        if main == "image":
            # Map common subtypes
            if sub in ("jpeg", "pjpeg", "jpg"):
                return ".jpg"
            if sub in ("png",):
                return ".png"
            if sub in ("webp",):
                return ".webp"
            if sub in ("gif",):
                return ".gif"
            if sub in ("bmp",):
                return ".bmp"
            if sub in ("x-icon", "ico"):
                return ".ico"

    # Try from URL suffix
    lower_url = url.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".ico"):
        if lower_url.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext

    return ".jpg"


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer": "https://www.instagram.com/",
}


async def download_profile_image(
    photo_url: str,
    username: str,
    platform: str,  # 'red_x', 'red_instagram', 'red_facebook'
    *,
    photo_owner: Optional[str] = None,  # Username del dueño de la foto (default: username)
    overwrite: bool = False,
    timeout: float = 20.0,
    page: Optional[object] = None,
    on_failure: str = "proxy",  # 'empty' | 'proxy' | 'raise'
    ftp_path: Optional[str] = None,
) -> str:
    """
    Descarga la foto de perfil y la sube al FTP.

    - username: Usuario root (carpeta FTP: rs/{platform}/{username}/images/)
    - photo_owner: Usuario dueño de la foto (filename: {photo_owner}.jpg)
    - ftp_path: Ruta completa opcional para guardar en FTP (ignora username/platform/photo_owner para la ruta)
    - Sube a FTP en la estructura: rs/{platform}/{username}/images/{photo_owner}.{ext}
    - Deduce la extensión por content-type o URL (fallback .jpg).
    - Evita re-descargar si ya existe (a menos que overwrite=True).

    Returns: ruta FTP tipo "/files/scraped-image/{platform}/{username}/{filename}" o la ruta FTP directa si se usó ftp_path
    """
    if not photo_url:
        return ""

    ensure_dirs()

    # First do a lightweight HEAD to probe content-type (best-effort)
    content_type: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=DEFAULT_HEADERS, http2=True) as client:
            try:
                head = await client.head(photo_url)
                if head.status_code < 400:
                    content_type = head.headers.get("content-type")
            except Exception:
                # Ignore HEAD failures; we'll try GET next
                pass

            ext = _extension_from_headers(content_type, photo_url)
            owner = photo_owner or username
            filename = f"{_safe_filename(owner)}{ext}"
            file_path = os.path.join(IMAGES_DIR, filename)

            if not overwrite and os.path.exists(file_path) and not ftp_path:
                return f"{PUBLIC_IMAGES_PREFIX_PRIMARY}/{filename}"

            # Download the image
            resp = await client.get(photo_url)
            resp.raise_for_status()

            # If GET reveals a better content-type, adjust extension once
            final_ct = resp.headers.get("content-type")
            final_ext = _extension_from_headers(final_ct, photo_url)
            if final_ext != ext:
                owner = photo_owner or username
                filename = f"{_safe_filename(owner)}{final_ext}"
                file_path = os.path.join(IMAGES_DIR, filename)

            # Upload to FTP
            try:
                from src.utils.ftp_storage import get_ftp_client
                ftp = get_ftp_client()
                
                if ftp_path:
                    # Use provided path directly
                    final_path = ftp_path
                    if ftp_path.endswith('/'):
                        final_path = f"{ftp_path}{filename}"
                        
                    ftp.upload_file(final_path, resp.content)
                    # Return URL pointing to the new endpoint
                    return f"/files/scraped-image-path/{final_path}"
                else:
                    ftp.upload(
                        platform=platform,
                        username=username,
                        category='images',
                        filename=filename,
                        data=resp.content
                    )
                    return f"/files/scraped-image/{platform}/{username}/{filename}"
            except Exception as ftp_error:
                # Fallback to local storage on FTP failure
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"FTP upload failed, using local fallback: {ftp_error}")
                ensure_dirs()
                tmp_path = f"{file_path}.part"
                with open(tmp_path, "wb") as f:
                    f.write(resp.content)
                os.replace(tmp_path, file_path)
                return f"{PUBLIC_IMAGES_PREFIX_PRIMARY}/{filename}"
    except Exception:
        # Fallback using Playwright page with session cookies if provided
        if page is not None:
            try:
                r = await page.request.get(photo_url, headers=DEFAULT_HEADERS, timeout=20000)
                if r.ok:
                    ct = r.headers.get("content-type", "")
                    ext = ".png" if "png" in ct else ".webp" if "webp" in ct else ".jpg"
                    owner = photo_owner or username
                    filename = f"{_safe_filename(owner)}{ext}"
                    body_data = await r.body()
                    
                    try:
                        from src.utils.ftp_storage import get_ftp_client
                        ftp = get_ftp_client()
                        if ftp_path:
                            final_path = ftp_path
                            if ftp_path.endswith('/'):
                                final_path = f"{ftp_path}{filename}"
                            ftp.upload_file(final_path, body_data)
                            return f"/files/scraped-image-path/{final_path}"
                        else:
                            ftp.upload(platform, username, 'images', filename, body_data)
                            return f"/files/scraped-image/{platform}/{username}/{filename}"
                    except:
                        # Local fallback
                        file_path = os.path.join(IMAGES_DIR, filename)
                        with open(file_path, "wb") as f:
                            f.write(body_data)
                        return f"{PUBLIC_IMAGES_PREFIX_PRIMARY}/{filename}"
            except Exception:
                pass
        # Final fallback policy
        if on_failure == "proxy":
            return f"/proxy-image?{urlencode({'url': photo_url})}"
        if on_failure == "raise":
            raise RuntimeError("Failed to download image and no fallback allowed")
        return ""


async def local_or_proxy_photo_url(
    photo_url: str,
    username: str,
    platform: str,  # 'red_x', 'red_instagram', 'red_facebook'
    mode: str = "download",
    photo_owner: Optional[str] = None,  # Username del dueño de la foto
    page: Optional[object] = None,
    on_failure: str = "proxy",
    retries: int = 3,
    backoff_seconds: float = 0.4,
    ftp_path: Optional[str] = None,
) -> str:
    """
    Devuelve una URL utilizable por el frontend para mostrar la imagen de perfil.
    - username: Usuario root (carpeta FTP)
    - photo_owner: Usuario dueño de la foto (filename)
    - mode="download": descarga y devuelve "/files/scraped-image/{platform}/{username}/{filename}"
    - mode="proxy": usa el endpoint /proxy-image para evitar CORS sin guardar
    - mode="external": devuelve la URL original (si el frontend puede cargarla)
    """
    if not photo_url:
        return ""

    mode = (mode or "download").lower()
    if mode == "proxy":
        # URL-encode to be safe
        return f"/proxy-image?url={quote_plus(photo_url)}"
    if mode == "external":
        return photo_url
    # default -> download with retries
    # If already a local storage or FTP path, return as-is
    if str(photo_url).startswith('/storage/') or str(photo_url).startswith('/files/'):
        return photo_url

    attempts = max(1, int(retries))
    for i in range(attempts):
        result = await download_profile_image(photo_url, username, platform, photo_owner=photo_owner, page=page, on_failure='proxy', ftp_path=ftp_path)
        # Accept result if it's a valid path (not a proxy fallback)
        if result and not result.startswith('/proxy-image'):
            return result
        if i < attempts - 1:
            try:
                await asyncio.sleep(backoff_seconds * (i + 1))
            except Exception:
                pass
    # All attempts failed
    if on_failure == 'proxy':
        return f"/proxy-image?url={quote_plus(photo_url)}"
    if on_failure == 'raise':
        raise RuntimeError("Image download failed after retries")
    return ""


async def download_image_to_path(
    photo_url: str,
    ftp_path: str,
    timeout: float = 20.0
) -> str:
    """
    Descarga una imagen desde una URL y la sube a una ruta específica del FTP.
    
    Args:
        photo_url: URL de la imagen
        ftp_path: Ruta completa en el FTP donde guardar la imagen
        timeout: Timeout para la descarga
        
    Returns:
        La ruta FTP utilizada si tuvo éxito, o string vacío si falló.
    """
    if not photo_url:
        return ""
        
    from src.utils.ftp_storage import get_ftp_client
    
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=DEFAULT_HEADERS, http2=True) as client:
            response = await client.get(photo_url)
            if response.status_code >= 400:
                return ""
                
            content = response.content
            if not content:
                return ""
                
            ftp = get_ftp_client()
            ftp.upload_file(ftp_path, content)
            return ftp_path
            
    except Exception as e:
        # Log error but don't crash
        print(f"Error downloading image {photo_url}: {e}")
        return ""
