FACEBOOK_CONFIG = {
    "max_scroll_attempts": 50,
    "max_no_new_content": 5,
    "max_posts": 10,
    "scroll_pause_ms": 2000,
    "rate_limit_pause_ms": 5000,
    "rate_limit_scroll_interval": 10,  # Pausa cada X scrolls
    "rate_limit_posts_interval": 3,    # Pausa cada X posts procesados
    "storage_state_path": "data/storage/facebook_storage_state.json",

    "user_cell_selectors": [
        'div[role="main"] div:has(a[tabindex="0"])',
        'div[data-pagelet="ProfileAppSection_0"] div:has(a[href*="facebook.com"])',
        'div[aria-label="People"] div:has(a)',
        'div[role="main"] > div > div:has(a[role="link"])'
    ],
    "enlace_selectors": [
        'a[tabindex="0"]',
        'a[href*="facebook.com"]',
        'a[role="link"]:not([href*="/photo"])'
    ],
    "img_selectors": [
        'a[tabindex="-1"] img',
        'img[src*="scontent"]',
        'img[alt*="foto de perfil"]'
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
        'div[data-ad-preview="message"]',
        'div[role="article"] div:has(a[href^="/"])'
    ],
    "comment_container_selectors": [
        # Selector específico del contenedor de comentarios proporcionado
        'div.x9f619.x1n2onr6.x1ja2u2z.x78zum5.xdt5ytf.x2lah0s.x193iq5w.xeuugli.x1icxu4v.x25sj25.x10b6aqq.x1yrsyyn',
        # Selector del botón de comentarios clickeable
        'div[role="button"][tabindex="0"] span[class*="html-span"] div.x1i10hfl',
        # Selectores alternativos para botones de comentarios
        'div[aria-label*="comentario" i]',
        'div[role="button"]:has(i[style*="7H32i_pdCAf.png"])',
        'div[role="button"]:has(span:contains("0"), span:contains("1"), span:contains("2"), span:contains("3"), span:contains("4"), span:contains("5"))',
        # Selector más general para contadores de comentarios
        'span:has(span[class*="html-span"]) div[role="button"]'
    ],
    "patterns_to_exclude": [
        "/followers", "/following", "/friends", "/videos", "/photo", "/photos",
        "/tv", "/events", "/past_events", "/likes", "/likes_all",
        "/music", "/sports", "/map", "/movies", "/pages",
        "/groups", "/watch", "/reel", "/story", "/video_tv_shows_watch",
        "/games"
    ]
}