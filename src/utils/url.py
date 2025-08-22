from __future__ import annotations

from urllib.parse import urlparse, urlunparse, urlencode, parse_qs


CANONICAL_HOST = {
    'facebook': 'www.facebook.com',
    'instagram': 'www.instagram.com',
    'x': 'x.com',
}

ALIASES = {
    'facebook': {
        'facebook.com', 'www.facebook.com', 'm.facebook.com', 'mbasic.facebook.com', 'web.facebook.com'
    },
    'instagram': {
        'instagram.com', 'www.instagram.com', 'm.instagram.com'
    },
    'x': {
        'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com', 'mobile.twitter.com', 'm.twitter.com'
    },
}


def _ensure_https(url: str) -> str:
    if not url:
        return url
    if url.startswith(('http://', 'https://')):
        return url
    return 'https://' + url.lstrip('/')


def normalize_input_url(platform: str, url: str) -> str:
    """Normalize a profile URL for a given platform.
    - Ensures https
    - Maps alias domains to canonical
    - Removes duplicate domain artifacts and trailing junk
    """
    if not url:
        return url
    url = _ensure_https(url.strip())

    # Fix accidental duplicated domain like https://x.com.com/user
    # Heuristic: if host ends with '.com.com', collapse to '.com'
    p = urlparse(url)
    host = (p.netloc or '').lower()
    if host.endswith('.com.com'):
        host = host[:-4]

    plat = (platform or '').lower()
    canonical = CANONICAL_HOST.get(plat, host or '')
    aliases = ALIASES.get(plat, {host})

    # Strip port if any and map alias to canonical
    host = host.split(':')[0]
    if host in aliases:
        host = canonical

    # Clean path: collapse multiple slashes
    path = (p.path or '/').replace('//', '/')
    if not path.startswith('/'):
        path = '/' + path

    # Remove trailing "?" and keep/strip query by platform specifics
    query = p.query or ''
    fragment = ''  # drop fragment

    # Platform-specific adjustments
    if plat == 'facebook':
        # Keep relevant query for photo.php (fbid, set, id, owner, comment_id)
        if 'photo.php' in path or path.startswith('/photo/'):
            allowed = {'fbid', 'set', 'id', 'owner', 'comment_id'}
            q = parse_qs(query, keep_blank_values=False)
            q = {k: v for k, v in q.items() if k in allowed}
            query = urlencode({k: v[-1] for k, v in q.items()}) if q else ''
        else:
            query = ''
        # Ensure single trailing slash for profile pages (not for photo.php)
        if not ('photo.php' in path or '/photos/' in path):
            path = path.rstrip('/') + '/'
    elif plat == 'instagram':
        query = ''
        # Ensure trailing slash for profiles and posts
        if path.count('/') >= 1:
            path = path.rstrip('/') + '/'
    elif plat == 'x':
        query = ''
        # No trailing slash normalization needed beyond collapse
        if path != '/' and path.endswith('/'):
            # Keep trailing slash for pure profile path, but not for /status/...
            if '/status/' in path:
                path = path.rstrip('/')
    normalized = urlunparse(('https', host, path, '', query, fragment))
    return normalized


def extract_username_from_url(platform: str, url: str) -> str | None:
    if not url:
        return None
    p = urlparse(_ensure_https(url))
    plat = (platform or '').lower()
    path = (p.path or '/').strip('/')
    parts = [seg for seg in path.split('/') if seg]
    if not parts:
        return None

    if plat == 'facebook':
        # profile.php?id=...
        if parts and parts[0] == 'profile.php':
            q = parse_qs(p.query)
            return q.get('id', [None])[-1]
        # Skip list suffixes
        skip = {'friends', 'friends_all', 'followers', 'following', 'photos', 'photos_by', 'photos_all'}
        if parts[0] in skip and len(parts) > 1:
            return parts[-1]
        return parts[0]
    if plat == 'instagram':
        skip = {'followers', 'following', 'p', 'reel', 'tv', 'stories', 'explore', 'accounts'}
        if parts[0] in skip and len(parts) > 1:
            return parts[1]
        return parts[0]
    if plat == 'x':
        skip = {'status', 'i', 'hashtag', 'search', 'home', 'settings', 'messages', 'notifications'}
        if parts[0] in skip and len(parts) > 1:
            return None
        return parts[0]
    return parts[0]


def normalize_post_url(platform: str, url: str) -> str:
    """Best-effort normalization for post URLs used as keys in DB."""
    plat = (platform or '').lower()
    url = _ensure_https(url or '')
    p = urlparse(url)
    host = p.netloc.split(':')[0].lower()
    # Map to canonical host
    if host in ALIASES.get(plat, {host}):
        host = CANONICAL_HOST.get(plat, host)
    path = (p.path or '/').replace('//', '/')
    query = p.query or ''

    if plat == 'facebook':
        if 'photo.php' in path or '/photos/' in path:
            allowed = {'fbid', 'set', 'id', 'owner', 'comment_id'}
            q = parse_qs(query, keep_blank_values=False)
            q = {k: v for k, v in q.items() if k in allowed}
            query = urlencode({k: v[-1] for k, v in q.items()}) if q else ''
        else:
            query = ''
    else:
        # IG and X: strip query/fragments
        query = ''

    return urlunparse(('https', host, path.rstrip('/'), '', query, ''))
