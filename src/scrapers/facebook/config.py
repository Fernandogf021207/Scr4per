FACEBOOK_CONFIG = {
    "max_scroll_attempts": 50,
    "max_no_new_content": 5,
    "scroll_pause_ms": 2000,
    "rate_limit_pause_ms": 5000,
    "storage_state_path": "data/storage/facebook_storage_state.json",

    "user_cell_selectors": [
        'div[role="grid"] div[role="row"]',
        'ul > li > div > div > a[role="link"]'
    ],
    "enlace_selectors": [
        'a[role="link"][href^="/profile.php?id="]',
        'a[role="link"][href^="/"][tabindex]'
    ],
    "img_selectors": [
        'image',
        'img[src*="scontent"]'
    ],
    "nombre_usuario_selectors": [
        'span strong',
        'div[dir="auto"] span'
    ],
    "foto_selectors": [
        'image',
        'img[src*="scontent"]'
    ],
    "nombre_selectors": [
        'h1',
        'span[dir="auto"]'
    ],
    "patterns_to_exclude": [
        '/friends_mutual', '/groups', '/events', '/notifications', '/messages', '/watch'
    ]
}
