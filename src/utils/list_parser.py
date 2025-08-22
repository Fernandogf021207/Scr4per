from __future__ import annotations

from typing import Optional

from .url import normalize_input_url, extract_username_from_url


def build_user_item(platform: str, href: str, name_text: Optional[str], photo_url: Optional[str]) -> dict:
    """Pure helper that builds a normalized user dict from basic pieces.

    Inputs:
    - platform: 'facebook' | 'instagram' | 'x'
    - href: profile URL (absolute or relative)
    - name_text: visible name text near the link
    - photo_url: image URL if available

    Output keys (common across scrapers):
    - nombre_usuario, username_usuario, link_usuario, foto_usuario
    """
    # Normalize the href to canonical URL
    url = normalize_input_url(platform, href)
    username = extract_username_from_url(platform, url) or 'unknown'

    nombre = (name_text or '').strip() or username
    foto = (photo_url or '').strip()
    if foto.startswith('data:'):
        foto = ''

    return {
        'nombre_usuario': nombre,
        'username_usuario': username,
        'link_usuario': url,
        'foto_usuario': foto,
    }


def build_user_list(platform: str, rows: list[dict]) -> list[dict]:
    """Build a list of normalized user dicts from simple row dicts.
    Each row: {href, name_text?, photo_url?}
    Deduplicates by link_usuario.
    """
    seen = set()
    out: list[dict] = []
    for r in rows:
        item = build_user_item(platform, r.get('href', ''), r.get('name_text'), r.get('photo_url'))
        key = item['link_usuario']
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
