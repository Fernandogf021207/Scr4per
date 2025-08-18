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
        # Selectores generalistas para botones de comentarios
        'div[role="button"]:has-text("Ver más comentarios")',
        'div[role="button"]:has-text("comentario")',
        'div[role="button"]:has-text("comentarios")',
        'div[role="button"]:has-text("")',
        'div[role="button"] i[style*="7H32i_pdCAf.png"]',
        'div[role="button"] i[data-visualcompletion="css-img"]',
        'div[aria-label*="comentario" i]',
        'div[aria-label*="comment" i]',
        'div[role="button"][tabindex="0"]:has(span)',
    ],
    "modal_selectors": [
        'div[role="dialog"]',
        'div[aria-modal="true"]',
        'div[data-pagelet*="comment"]',
        'div[class*="modal"]',
        'div[style*="position: fixed"]',
    ],
    "modal_comment_selectors": [
        'div[role="dialog"] div[aria-label="Comentario"]',
        'div[aria-modal="true"] div[aria-label="Comentario"]',
        'div[role="dialog"] div:has(a[href^="/"])',
        'div[aria-modal="true"] div:has(a[href^="/"])',
        'div:has(a[href^="/"]):has(img[src*="scontent"])',
    ],
    "likes_button_selectors": [
        # Área de recuento de reacciones/likes en el post
        'div[role="toolbar"]:has(span:has-text("Consulta quién reaccionó a esto "))',
        'div[role="toolbar"]:has(span:has-text("Consulta quién reaccionó a esto" i))',
        'span:has-text("Me gusta")',
        'span:has-text("likes" i)',
    'span.x135b78x',
        'a[role="link"]:has(span:has-text("likes" i))',
        'div[aria-label*="Consulta quién reaccionó a esto" i]',
        'div[aria-label*="Consulta quién reaccionó a esto" i]',
    ],
    "modal_likes_item_selectors": [
        # Elementos de usuarios dentro del modal de likes
        'div[role="dialog"] a[role="button"][tabindex="0"]',
        'div[role="dialog"] div:has(a[href^="/"][role="link"])',
        'div[role="dialog"] div[aria-label*="Personas" i] div:has(a)',
        'div[role="dialog"] div[style*="display"]:has(a[href^="/"])',
    ],
    "patterns_to_exclude": [
        "/followers", "/following", "/friends", "/videos", "/photo", "/photos",
        "/tv", "/events", "/past_events", "/likes", "/likes_all",
        "/music", "/sports", "/map", "/movies", "/pages",
        "/groups", "/watch", "/reel", "/story", "/video_tv_shows_watch",
        "/games"
    ]
}