from fastapi import APIRouter, HTTPException
from typing import Any, Dict
from src.scrapers.config_runtime import effective_config, set_override

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/scrapers", response_model=dict)
def get_all_scraper_config() -> Dict[str, Any]:
    """Return effective scraper configuration (defaults + overrides + env)."""
    return effective_config()


@router.get("/scrapers/{platform}", response_model=dict)
def get_scraper_config(platform: str) -> Dict[str, Any]:
    cfg = effective_config()
    if platform not in cfg:
        raise HTTPException(status_code=404, detail="Unknown platform")
    return cfg[platform]


@router.put("/scrapers/{platform}", response_model=dict)
def update_scraper_config(platform: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update overrides for a platform. Payload keys are merged at dot-path granularity.

    Example body:
    {"scroll": {"max_scrolls": 120, "pause_ms": 700}, "posts": {"max_posts": 8}}
    """
    # Flatten dict into dot paths to store individual overrides
    def flatten(prefix: str, obj: Any, out: Dict[str, Any]):
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_prefix = f"{prefix}.{k}" if prefix else k
                flatten(new_prefix, v, out)
        else:
            out[prefix] = obj

    flat: Dict[str, Any] = {}
    flatten("", payload, flat)
    for path, value in flat.items():
        if not path:
            continue
        set_override(platform, path, value)
    return effective_config(refresh=True).get(platform, {})
