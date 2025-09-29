from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple, Set, List, Optional, Iterable, Any
import time

RelationTuple = Tuple[str, str, str, str]  # (platform, source_username, target_username, type)
ProfileKey = Tuple[str, str]

# Relation types expected (Spanish)
RELATION_TYPES = {"seguidor", "seguido", "amigo", "comentó", "reaccionó", "mencionó", "etiquetó"}


def normalize_username(username: str) -> str:
    return (username or "").strip()


def valid_username(username: str) -> bool:
    # Regex simplified inline to avoid re; keep consistent with FE contract
    if not username:
        return False
    if len(username) > 50:
        return False
    for ch in username:
        if not (ch.isalnum() or ch in "._-"):
            return False
    return True


def merge_full_name(current: Optional[str], incoming: Optional[str]) -> Optional[str]:
    if not incoming:
        return current
    if not current:
        return incoming
    # Strategy prefer_longer_name (ties -> keep current)
    if len(incoming) > len(current):
        return incoming
    return current

@dataclass
class ProfileAccum:
    platform: str
    username: str
    full_name: Optional[str] = None
    profile_url: Optional[str] = None
    photo_url: Optional[str] = None
    sources: Set[ProfileKey] = field(default_factory=set)

    def merge(self, other: 'ProfileAccum') -> None:
        self.full_name = merge_full_name(self.full_name, other.full_name)
        if not self.profile_url and other.profile_url:
            self.profile_url = other.profile_url
        if not self.photo_url and other.photo_url:
            self.photo_url = other.photo_url
        self.sources |= other.sources

@dataclass
class Aggregator:
    profiles: Dict[ProfileKey, ProfileAccum] = field(default_factory=dict)
    relations: Set[RelationTuple] = field(default_factory=set)
    roots: List[ProfileKey] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    def add_root(self, p: ProfileAccum):
        key = (p.platform, p.username)
        if key not in self.profiles:
            self.profiles[key] = p
        else:
            self.profiles[key].merge(p)
        if key not in self.roots:
            self.roots.append(key)

    def add_profile(self, p: ProfileAccum):
        key = (p.platform, p.username)
        if key in self.profiles:
            self.profiles[key].merge(p)
        else:
            self.profiles[key] = p

    def add_relation(self, platform: str, source: str, target: str, rel_type: str):
        if rel_type not in RELATION_TYPES:
            return
        if source == target:
            return
        self.relations.add((platform, source, target, rel_type))

    def build_payload(self, *, roots_requested: int) -> Dict[str, Any]:
        """Build final payload according to documented schema v2.
        Contract (F1):
          root_profiles: ["platform:username", ...]
          profiles[i].sources: ["platform:root_username", ...]
          relations: items with flat keys (platform, source, target, type)
        """
        # Root profile identifiers preserving request order
        root_profiles_ids: List[str] = [f"{p}:{u}" for (p, u) in self.roots if (p, u) in self.profiles]
        # Profiles list
        profiles_out: List[Dict[str, Any]] = []
        for acc in self.profiles.values():
            profiles_out.append(_profile_to_dict(acc))
        # Relations list
        relations_out: List[Dict[str, Any]] = []
        for (platform, src, tgt, typ) in self.relations:
            relations_out.append({
                "platform": platform,
                "source": src,
                "target": tgt,
                "type": typ,
            })
        roots_processed = len(root_profiles_ids)
        return {
            "schema_version": 2,
            "root_profiles": root_profiles_ids,
            "profiles": profiles_out,
            "relations": relations_out,
            "warnings": self.warnings,
            "meta": {
                "schema_version": 2,
                "roots_requested": roots_requested,
                "roots_processed": roots_processed,
                "generated_at": _iso_now(),
                "build_ms": int((time.time() - self.started_at) * 1000),
            },
        }

def _iso_now() -> str:
    import datetime
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'

def _profile_to_dict(acc: ProfileAccum) -> Dict[str, Any]:
    return {
        "platform": acc.platform,
        "username": acc.username,
        "full_name": acc.full_name,
        "profile_url": acc.profile_url,
        "photo_url": acc.photo_url,
        # Sources as string identifiers platform:username (deterministic order)
        "sources": [f"{p}:{u}" for (p, u) in sorted(acc.sources)],
    }

# Helper to create ProfileAccum from raw dict

def make_profile(platform: str, username: str, full_name: Optional[str], profile_url: Optional[str], photo_url: Optional[str], source: ProfileKey) -> ProfileAccum:
    pa = ProfileAccum(platform=platform, username=username, full_name=full_name, profile_url=profile_url, photo_url=photo_url)
    pa.sources.add(source)
    return pa
