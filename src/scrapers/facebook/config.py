# Configuration for Facebook scraper
FACEBOOK_CONFIG = {
    "max_scroll_attempts": 50,
    "max_no_new_content": 5,
    "max_posts": 10,
    "scroll_pause_ms": 2000,
    "rate_limit_pause_ms": 5000,
    "storage_state_path": "data/storage/facebook_storage_state.json",
    "foto_selectors": [
        'img[data-imgperflogname="profileCoverPhoto"]',
        'img[alt*="profile picture"]',
        'div[role="banner"] img',
        'img[src*="scontent"]',
        'div[role="main"] img[referrerpolicy="origin-when-cross-origin"]',
        'svg[role="img"] + image'
    ],
    "nombre_selectors": [
        'div[role="main"] span[dir="auto"] h1',
        'h1',
        'div[data-testid="profile_name"] span',
        'span[dir="auto"]'
    ],
    "user_cell_selectors": [
        'div[role="main"] div:has(a[tabindex="0"])',
        'div[role="main"] div div a[href*="/profile.php"]',
        'div[role="main"] div div a[href^="/"]',
        'div[data-visualcompletion="ignore-dynamic"] a'
    ],
    "enlace_selectors": [
        'a[tabindex="0"]',
        'a[href*="/profile.php"]',
        'a[href^="/"][role="link"]',
        'div > a[href^="/"]'
    ],
    "img_selectors": [
        'a[tabindex="-1"] img',
        'img[alt*="profile"]',
        'img[src*="scontent"]',
        'div img[src^="https://scontent"]'
    ],
    "nombre_usuario_selectors": [
        'a[tabindex="0"] span',
        'span[dir="auto"]',
        'div a span',
        'div[data-testid="user-name"] span'
    ],
    "comment_selectors": [
        'div[aria-label="Comment"] a[href^="/"]',
        'div[role="article"] div div a[href^="/"]',
        'div[data-testid="UFI2Comment/root"] a',
        'div[aria-label*="commented on"] a'
    ],
    "post_selectors": [
        'div[role="article"] a[href*="/posts/"]',
        'div[role="article"] a[href*="/permalink.php"]',
        'a[href*="/posts/"]',
        'a[href*="/permalink.php"]'
    ],
    "patterns_to_exclude": [
        '/groups/', '/events/', '/marketplace/',
        '/watch/', '/ads/', '/pages/',
        '/login/', '/logout/', '/settings/',
        '/followers', '/following', '/friends',
        '/videos', '/photo', '/photos',
        '/music', '/sports', '/map', '/movies',
        '/reel', '/story'
    ]
}