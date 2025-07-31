# Configuration for Instagram scraper
INSTAGRAM_CONFIG = {
    "max_posts": 5,
    "scroll_attempts": 30,
    "scroll_pause_ms": 1500,
    "post_scroll_attempts": 5,
    "comment_load_timeout_ms": 3000,
    "comment_scroll_attempts": 10,
    "storage_state_path": "data/storage/instagram_storage_state.json",
    "foto_selectors": [
        'img[alt*="foto de perfil"]',
        'img[data-testid="user-avatar"]',
        'header img',
        'article header img',
        'div[role="button"] img'
    ],
    "nombre_selectors": [
        'header section div div h2',
        'header h2',
        'article header h2',
        'h1',
        'h2'
    ],
    "contenedor_selectors": [
        'div[role="dialog"] div[style*="flex-direction: column"]',
        'div[role="dialog"] div',
        'div[aria-label="Seguidores"]',
        'div[aria-label="Followers"]',
        'div[aria-label="Following"]'
    ],
    "post_selectors": [
        'article a[href*="/p/"]',
        'article a[href*="/reel/"]',
        'a[href*="/p/"]',
        'a[href*="/reel/"]'
    ],
    "botones_cargar_comentarios": [
        'button:has-text("Cargar más comentarios")',
        'button:has-text("Load more comments")',
        'button[aria-label="Load more comments"]',
        'span:has-text("Cargar más comentarios")'
    ],
    "comentario_selectors": [
        'article section div div div div span[dir="auto"] a',
        'div[role="button"] span[dir="auto"] a',
        'span:has(a[href*="/"])',
        'article a[href^="/"][href$="/"]'
    ],
    "follower_selectors": [
        'a[href*="/followers/"]',
        'a:has-text("seguidores")',
        'a:has-text("followers")',
        'header a[href*="followers"]'
    ],
    "following_selectors": [
        'a[href*="/following/"]',
        'a:has-text("seguidos")',
        'a:has-text("following")',
        'header a[href*="following"]'
    ]
}