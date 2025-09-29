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
    *,
    overwrite: bool = False,
    timeout: float = 20.0,
    page: Optional[object] = None,
    on_failure: str = "proxy",  # 'empty' | 'proxy' | 'raise'
) -> str:
    """
    Descarga la foto de perfil al servidor y devuelve la ruta local accesible por el frontend.

    - Crea storage/images si no existe.
    - Deduce la extensión por content-type o URL (fallback .jpg).
    - Evita re-descargar si ya existe (a menos que overwrite=True).

    Returns: ruta relativa tipo "/data/storage/images/<username>.<ext>"
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
            filename = f"{_safe_filename(username)}{ext}"
            file_path = os.path.join(IMAGES_DIR, filename)

            if not overwrite and os.path.exists(file_path):
                return f"{PUBLIC_IMAGES_PREFIX_PRIMARY}/{filename}"

            # Download the image
            resp = await client.get(photo_url)
            resp.raise_for_status()

            # If GET reveals a better content-type, adjust extension once
            final_ct = resp.headers.get("content-type")
            final_ext = _extension_from_headers(final_ct, photo_url)
            if final_ext != ext:
                filename = f"{_safe_filename(username)}{final_ext}"
                file_path = os.path.join(IMAGES_DIR, filename)

            # Write to disk atomically-ish
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
                    filename = f"{_safe_filename(username)}{ext}"
                    file_path = os.path.join(IMAGES_DIR, filename)
                    tmp_path = f"{file_path}.part"
                    with open(tmp_path, "wb") as f:
                        f.write(await r.body())
                    os.replace(tmp_path, file_path)
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
    mode: str = "download",
    page: Optional[object] = None,
    on_failure: str = "proxy",
    retries: int = 3,
    backoff_seconds: float = 0.4,
) -> str:
    """
    Devuelve una URL utilizable por el frontend para mostrar la imagen de perfil.
    - mode="download": descarga y devuelve "/storage/images/<file>"
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
    # If already a local storage path, return as-is
    if str(photo_url).startswith('/storage/'):
        return photo_url

    attempts = max(1, int(retries))
    for i in range(attempts):
        result = await download_profile_image(photo_url, username, page=page, on_failure='proxy')
        if result and (result.startswith('/storage/') or result.startswith(PUBLIC_IMAGES_PREFIX_PRIMARY)):
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
