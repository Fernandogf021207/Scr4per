INSTAGRAM_CONFIG = {
    "max_scroll_attempts": 50,
    "max_no_new_content": 5,
    "scroll_pause_ms": 2000,
    "rate_limit_pause_ms": 5000,
    "storage_state_path": "data/storage/instagram_storage_state.json",

    # Selectores CSS comunes para Instagram
    "user_cell_selectors": [
        'div[role="dialog"] ul > div li'
    ],
    "enlace_selectors": [
        'a[href^="/"]'
    ],
    "img_selectors": [
        'img[src*="cdninstagram"]',
        'img[decoding="auto"]'
    ],
    "nombre_usuario_selectors": [
        'span[dir="auto"]'
    ],
    "foto_selectors": [
        'header img',
        'img[alt*="profile picture"]'
    ],
    "nombre_selectors": [
        'header h1',
        'header span'
    ],
    "patterns_to_exclude": [
        '/explore/', '/reels/', '/direct/', '/stories/', '/accounts/'
    ]
}