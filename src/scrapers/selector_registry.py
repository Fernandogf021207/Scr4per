"""Selector registry versionado para plataformas de scraping.

Proporciona un punto centralizado para administrar los selectores clave por plataforma
con capacidad de versionado para facilitar actualizaciones y rollback.
"""
from typing import List, Dict, Any

SELECTOR_REGISTRY: Dict[str, Dict[str, Any]] = {
    "instagram": {
        "version": "ig-1",
        "lists": {
            "followers_link": [
                'a[href*="/followers/"]',
                'a:has-text("seguidores")',
                'a:has-text("followers")',
                'header a[href*="followers"]'
            ],
            "following_link": [
                'a[href*="/following/"]',
                'a:has-text("seguidos")',
                'a:has-text("following")',
                'header a[href*="following"]'
            ],
            "list_item": [
                'div[role="dialog"] a[role="link"]',
                'div[aria-modal="true"] a[role="link"]',
                'div[role="dialog"] div:has(a[role="link"])'
            ]
        },
        "private_indicators": [
            'Esta cuenta es privada',
            'This account is private'
        ],
        "login_indicators": [
            'Log in', 'Inicia sesión', 'Registrarte'
        ]
    },
    "facebook": {
        "version": "fb-1",
        "lists": {
            "friends_link": [
                'a[href*="friends"]',
            ],
            "followers_link": [
                'a[href*="followers"]'
            ],
            "following_link": [
                'a[href*="following"]'
            ],
            "list_item": [
                'div[role="main"] a[href^="/profile.php?id="]',
                'div[role="main"] a[href^="/"]:not([href*="photo"])'
            ]
        },
        "private_indicators": [
            "This content isn't available", "Este contenido no está disponible"
        ],
        "login_indicators": [
            'Log in', 'Inicia sesión'
        ]
    },
    "x": {
        "version": "x-1",
        "lists": {
            "followers_link": [
                'a[href$="/followers"]'
            ],
            "following_link": [
                'a[href$="/following"]'
            ],
            "list_item": [
                'div[data-testid="UserCell"] a[role="link"][href^="/"]'
            ]
        },
        "private_indicators": [
            'These posts are protected', 'Estas publicaciones son protegidas', 'These Tweets are protected'
        ],
        "login_indicators": [
            'Log in', 'Iniciar sesión'
        ]
    }
}

class SelectorRegistryError(Exception):
    pass

def registry_version(platform: str) -> str:
    data = SELECTOR_REGISTRY.get(platform)
    if not data:
        raise SelectorRegistryError(f"No registry for platform={platform}")
    return data.get("version", "unknown")

def get_selectors(platform: str, category: str) -> List[str]:
    data = SELECTOR_REGISTRY.get(platform)
    if not data:
        raise SelectorRegistryError(f"No registry for platform={platform}")
    struct = data
    # Navegar jerárquicamente por keys separadas por '.'
    cur: Any = struct
    for part in category.split('.'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise SelectorRegistryError(f"Category '{category}' not found for platform={platform}")
    if not isinstance(cur, list):
        raise SelectorRegistryError(f"Category '{category}' is not a list for platform={platform}")
    return cur

def text_indicators(platform: str, key: str) -> List[str]:
    data = SELECTOR_REGISTRY.get(platform, {})
    return data.get(key, [])  # type: ignore
