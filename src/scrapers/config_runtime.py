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

