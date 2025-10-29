from __future__ import annotations
import json
import os
from typing import Any, Dict
from functools import lru_cache

from paths import REPO_ROOT


DEFAULTS_PATH = os.path.join(REPO_ROOT, 'src', 'scrapers', 'scrapers_config.json')
OVERRIDES_DIR = os.path.join(REPO_ROOT, 'data', 'config')
OVERRIDES_PATH = os.path.join(OVERRIDES_DIR, 'scrapers_overrides.json')


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def _set_by_path(d: Dict[str, Any], path: str, value: Any) -> None:
    parts = path.split('.') if path else []
    cur = d
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    if parts:
        cur[parts[-1]] = value


def _get_by_path(d: Dict[str, Any], path: str, default: Any) -> Any:
    cur: Any = d
    for p in path.split('.') if path else []:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _env_overrides() -> Dict[str, Dict[str, Any]]:
    """Map specific environment variables into config dot-paths by platform."""
    mapping = {
        'instagram': {
            'IG_MAX_SCROLLS': 'scroll.max_scrolls',
            'IG_PAUSE_MS': 'scroll.pause_ms',
            'IG_STAGNATION_LIMIT': 'scroll.stagnation_limit',
            'IG_TIMEOUT_LIST_MS': 'timeouts.list_ms',
            'IG_MAX_POSTS': 'posts.max_posts',
            'IG_STORAGE_STATE': 'storage_state_path',
        },
        'facebook': {
            'FB_MAX_SCROLLS': 'scroll.max_scrolls',
            'FB_PAUSE_MS': 'scroll.pause_ms',
            'FB_TIMEOUT_LIST_MS': 'timeouts.list_ms',
            'FB_MAX_POSTS': 'posts.max_posts',
            'FB_STORAGE_STATE': 'storage_state_path',
        },
        'x': {
            'X_MAX_SCROLLS': 'scroll.max_scrolls',
            'X_PAUSE_MS': 'scroll.pause_ms',
            'X_TIMEOUT_LIST_MS': 'timeouts.list_ms',
            'X_MAX_POSTS': 'posts.max_posts',
            'X_STORAGE_STATE': 'storage_state_path',
        },
    }

    result: Dict[str, Dict[str, Any]] = {k: {} for k in mapping.keys()}
    for platform, envmap in mapping.items():
        for env_key, path in envmap.items():
            val = os.getenv(env_key)
            if val is None:
                continue
            # Best-effort type coercion: ints where possible
            if val.isdigit():
                coerced: Any = int(val)
            else:
                # Allow truthy/falsey strings for booleans
                low = val.lower()
                if low in ("true", "false"):
                    coerced = (low == "true")
                else:
                    coerced = val
            _set_by_path(result[platform], path, coerced)
    return result


@lru_cache(maxsize=1)
def _cached_effective_config() -> Dict[str, Any]:
    # Load defaults
    with open(DEFAULTS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Load file overrides
    if os.path.isfile(OVERRIDES_PATH):
        try:
            with open(OVERRIDES_PATH, 'r', encoding='utf-8') as f:
                overrides = json.load(f)
            if isinstance(overrides, dict):
                _deep_merge(data, overrides)
        except Exception:
            # Ignore broken overrides; caller can fix via API
            pass

    # Apply environment overrides
    envs = _env_overrides()
    for platform, ov in envs.items():
        if ov:
            if platform not in data or not isinstance(data[platform], dict):
                data[platform] = {}
            _deep_merge(data[platform], ov)

    return data


def effective_config(refresh: bool = False) -> Dict[str, Any]:
    """Return merged configuration: defaults + overrides + environment.

    Set refresh=True to drop the cache.
    """
    if refresh:
        _cached_effective_config.cache_clear()  # type: ignore[attr-defined]
    return _cached_effective_config()


def get(platform: str, path: str, default: Any = None) -> Any:
    cfg = effective_config()
    platform_cfg = cfg.get(platform, {}) if isinstance(cfg, dict) else {}
    return _get_by_path(platform_cfg, path, default)


def set_override(platform: str, path: str, value: Any) -> None:
    """Persist an override for a platform at a dot-path.

    Writes to data/config/scrapers_overrides.json and clears cache.
    """
    os.makedirs(OVERRIDES_DIR, exist_ok=True)
    current: Dict[str, Any] = {}
    if os.path.isfile(OVERRIDES_PATH):
        try:
            with open(OVERRIDES_PATH, 'r', encoding='utf-8') as f:
                current = json.load(f) or {}
        except Exception:
            current = {}

    if platform not in current or not isinstance(current[platform], dict):
        current[platform] = {}
    _set_by_path(current[platform], path, value)

    with open(OVERRIDES_PATH, 'w', encoding='utf-8') as f:
        json.dump(current, f, ensure_ascii=False, indent=2)

    # Drop cache so effective_config reflects the change
    _cached_effective_config.cache_clear()  # type: ignore[attr-defined]


__all__ = [
    'effective_config',
    'get',
    'set_override',
]
from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Any, Dict

_DEFAULTS_CACHE: Dict[str, Any] | None = None
_MERGED_CACHE: Dict[str, Any] | None = None

BASE_DIR = Path(__file__).resolve().parent
DEFAULTS_PATH = BASE_DIR / 'scrapers_config.json'
DATA_CONFIG_DIR = Path('data/config')
OVERRIDES_PATH = DATA_CONFIG_DIR / 'scrapers_overrides.json'


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def load_defaults() -> Dict[str, Any]:
    global _DEFAULTS_CACHE
    if _DEFAULTS_CACHE is None:
        _DEFAULTS_CACHE = _load_json(DEFAULTS_PATH)
    return _DEFAULTS_CACHE


def load_overrides() -> Dict[str, Any]:
    return _load_json(OVERRIDES_PATH)


def _apply_env_overrides(cfg: Dict[str, Any]) -> Dict[str, Any]:
    # Simple, documented env overrides per platform
    # Instagram
    ig = cfg.setdefault('instagram', {})
    ig_scroll = ig.setdefault('scroll', {})
    if v := os.getenv('IG_MAX_SCROLLS'):
        ig_scroll['max_scrolls'] = int(v)
    if v := os.getenv('IG_SCROLL_PAUSE_MS'):
        ig_scroll['pause_ms'] = int(v)
    if v := os.getenv('IG_STAGNATION_LIMIT'):
        ig_scroll['stagnation_limit'] = int(v)
    if v := os.getenv('IG_TIMEOUT_MS'):
        ig.setdefault('timeouts', {})['list_ms'] = int(v)
    if v := os.getenv('IG_MAX_POSTS'):
        ig.setdefault('posts', {})['max_posts'] = int(v)

    # Facebook
    fb = cfg.setdefault('facebook', {})
    fb_scroll = fb.setdefault('scroll', {})
    if v := os.getenv('FB_MAX_SCROLLS'):
        fb_scroll['max_scrolls'] = int(v)
    if v := os.getenv('FB_SCROLL_PAUSE_MS'):
        fb_scroll['pause_ms'] = int(v)

    # X / Twitter
    x = cfg.setdefault('x', {})
    x_scroll = x.setdefault('scroll', {})
    if v := os.getenv('X_MAX_SCROLLS'):
        x_scroll['max_scrolls'] = int(v)
    if v := os.getenv('X_SCROLL_PAUSE_MS'):
        x_scroll['pause_ms'] = int(v)
    if v := os.getenv('X_MAX_POSTS'):
        x.setdefault('posts', {})['max_posts'] = int(v)

    return cfg


def effective_config(refresh: bool = False) -> Dict[str, Any]:
    global _MERGED_CACHE
    if _MERGED_CACHE is not None and not refresh:
        return _MERGED_CACHE
    cfg = json.loads(json.dumps(load_defaults()))  # deep copy
    # Apply file overrides (user-set via API)
    ov = load_overrides()
    cfg = _deep_merge(cfg, ov)
    # Apply env overrides
    cfg = _apply_env_overrides(cfg)
    _MERGED_CACHE = cfg
    return cfg


def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get(platform: str, path: str, default: Any = None) -> Any:
    cfg = effective_config()
    node: Any = cfg.get(platform, {})
    for part in path.split('.'):
        if not isinstance(node, dict):
            return default
        node = node.get(part)
        if node is None:
            return default
    return node


def set_override(platform: str, path: str, value: Any) -> Dict[str, Any]:
    DATA_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current = load_overrides()
    root = current.setdefault(platform, {})
    _set_in_path(root, path, value)
    OVERRIDES_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
    # refresh cache
    effective_config(refresh=True)
    return current


def _set_in_path(root: Dict[str, Any], path: str, value: Any) -> None:
    parts = path.split('.')
    node = root
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value
