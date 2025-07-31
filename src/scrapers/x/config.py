# Configuration for X scraper
X_CONFIG = {
    "max_scroll_attempts": 50,
    "max_no_new_content": 5,
    "max_posts": 10,
    "scroll_pause_ms": 2000,
    "rate_limit_pause_ms": 5000,
    "storage_state_path": "data/storage/x_storage_state.json",
    "foto_selectors": [
        '[data-testid="UserAvatar-Container-"] img',
        'div[data-testid="UserName"] img',
        'header img[alt*="avatar"]',
        'img[alt*="profile"]',
        'div[role="banner"] img'
    ],
    "nombre_selectors": [
        '[data-testid="UserName"] div[dir="ltr"] span',
        'div[data-testid="UserName"] span',
        'h2[role="heading"] span',
        'div[role="banner"] h2 span'
    ],
    "user_cell_selectors": [
        '[data-testid="UserCell"]',
        'div[data-testid="UserCell"]',
        '[data-testid="cellInnerDiv"] div:has(a[role="link"])',
        'article[role="article"]:has(a[href^="/"])',
        'div:has(> div > div > a[href^="/"][role="link"])'
    ],
    "enlace_selectors": [
        'a[role="link"][href^="/"]',
        'div > a[href^="/"]',
        'a[href^="/"][dir="ltr"]'
    ],
    "img_selectors": [
        'img[alt*="avatar"]',
        'img[src*="profile_images"]',
        'div[data-testid="UserAvatar-Container-"] img',
        'img[alt][src^="https://pbs.twimg.com"]'
    ],
    "nombre_usuario_selectors": [
        'div[dir="ltr"] > span:first-child',
        'span[dir="ltr"]:not(:has(span))',
        'div:has(a[role="link"]) span:first-child',
        'div[data-testid="UserName"] span:first-child'
    ],
    "comment_selectors": [
        'div[data-testid="tweet"]:has(a[role="link"][href^="/"])',
        'article[role="article"]:has(div[data-testid="tweetText"])',
        'div[role="article"]:has(a[href^="/"][role="link"])'
    ],
    "patterns_to_exclude": [
        '/status/', '/photo/', '/video/', '/lists/', '/moments/',
        '/search', '/i/', '/compose/', '/settings/', '/notifications/',
        '/messages/', '/bookmarks/', '/explore/', '/home', '/hashtag/'
    ]
}