import os
from typing import Optional

import requests
from dotenv import load_dotenv

# Load optional API base URL
load_dotenv()
API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def create_or_update_profile(platform: str, username: str, full_name: Optional[str] = None,
                              profile_url: Optional[str] = None, photo_url: Optional[str] = None):
    payload = {
        "platform": platform,
        "username": username,
        "full_name": full_name,
        "profile_url": profile_url,
        "photo_url": photo_url,
    }
    r = requests.post(f"{API_BASE}/profiles", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def create_relationship(platform: str, owner_username: str, related_username: str, rel_type: str):
    payload = {
        "platform": platform,
        "owner_username": owner_username,
        "related_username": related_username,
        "rel_type": rel_type,
    }
    r = requests.post(f"{API_BASE}/relationships", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def create_post(platform: str, owner_username: str, post_url: str):
    payload = {
        "platform": platform,
        "owner_username": owner_username,
        "post_url": post_url,
    }
    r = requests.post(f"{API_BASE}/posts", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def create_comment(platform: str, post_url: str, commenter_username: str):
    payload = {
        "platform": platform,
        "post_url": post_url,
        "commenter_username": commenter_username,
    }
    r = requests.post(f"{API_BASE}/comments", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()
