FACEBOOK_CONFIG = {
    "max_scroll_attempts": 50,
    "max_no_new_content": 5,
    "max_posts": 10,
    "scroll_pause_ms": 2000,
    "rate_limit_pause_ms": 5000,
    "storage_state_path": "data/storage/facebook_storage_state.json",

    "user_cell_selectors": [
        'div[role="main"] div:has(a[tabindex="0"])'
    ],
    "enlace_selectors": [
        'a[tabindex="0"]'
    ],
    "img_selectors": [
        'a[tabindex="-1"] img'
    ],
    "nombre_usuario_selectors": [
        'a[tabindex="0"]'
    ],
    "foto_selectors": [
        'img[data-imgperflogname="profileCoverPhoto"]',
        'div[role="main"] img[referrerpolicy="origin-when-cross-origin"]',
        'svg[role="img"] + image'
    ],
    "nombre_selectors": [
        'div[role="main"] span[dir="auto"] h1'
    ],
    "comment_selectors": [
        'div[aria-label="Comentario"]',
        'div[data-ad-preview="message"]'
    ],
    "patterns_to_exclude": [
        "/followers", "/following", "/friends", "/videos", "/photo", "/photos",
        "/tv", "/events", "/past_events", "/likes", "/likes_all",
        "/music", "/sports", "/map", "/movies", "/pages",
        "/groups", "/watch", "/reel", "/story", "/video_tv_shows_watch",
        "/games"
    ]
}