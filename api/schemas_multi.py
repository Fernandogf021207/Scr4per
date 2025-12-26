from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator
import re

USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{2,60}$')
SUPPORTED_PLATFORMS = {'facebook','instagram','x'}
MAX_ROOTS = 5

class MultiRootItem(BaseModel):
    platform: Literal['facebook','instagram','x']
    username: str = Field(..., description="Raw username provided by client")
    max_photos: int = Field(5, ge=0, le=50)

    @validator('username')
    def _validate_username(cls, v: str):
        vv = v.strip().lstrip('@')
        if not USERNAME_RE.match(vv):
            raise ValueError('Invalid username')
        return vv

class MultiScrapeRequest(BaseModel):
    roots: List[MultiRootItem]

    @validator('roots')
    def _validate_roots(cls, v):
        if not v:
            raise ValueError('At least one root required')
        if len(v) > MAX_ROOTS:
            raise ValueError(f'Max {MAX_ROOTS} roots')
        return v

class ProfileOut(BaseModel):
    platform: str
    username: str
    full_name: str
    profile_url: Optional[str]
    photo_url: Optional[str]
    sources: List[str]

class RelationOut(BaseModel):
    platform: str
    source: str
    target: str
    type: str

class MultiScrapeMeta(BaseModel):
    schema_version: int
    build_ms: int
    roots_requested: int
    roots_processed: int

class MultiScrapeResponse(BaseModel):
    schema_version: int = 2
    root_profiles: List[str]
    profiles: List[ProfileOut]
    relations: List[RelationOut]
    meta: dict
    warnings: list = []


# ============================================================================
# Multi-Related Endpoint Schemas
# ============================================================================

class MultiRelatedRootItem(BaseModel):
    """Single root profile to start graph extraction from DB."""
    platform: Literal['facebook','instagram','x']
    username: str = Field(..., description="Username of the root profile")

    @validator('username')
    def _validate_username(cls, v: str):
        vv = v.strip().lstrip('@')
        if not USERNAME_RE.match(vv):
            raise ValueError('Invalid username')
        return vv


class MultiRelatedRequest(BaseModel):
    """Request schema for POST /multi-related endpoint.
    
    Extracts a subgraph from the database starting from multiple root profiles.
    Does not trigger new scraping; only reads existing data.
    """
    roots: List[MultiRelatedRootItem] = Field(
        ..., 
        min_items=1, 
        max_items=10,
        description="Root profiles to start graph extraction (1-10)"
    )
    depth: int = Field(
        1, 
        ge=1, 
        le=3,
        description="Depth of relations to extract (1=direct connections, 2=friends of friends, etc.)"
    )
    include_inter_root_relations: bool = Field(
        True,
        description="Whether to include direct relationships between root profiles themselves"
    )
    relation_types: Optional[List[str]] = Field(
        None,
        description="Filter by relation types: ['follower','following','friend','commented','reacted']. None = all types."
    )
    max_profiles: Optional[int] = Field(
        None,
        ge=1,
        le=5000,
        description="Limit total profiles returned (for performance). None = no limit."
    )

    @validator('roots')
    def _validate_roots(cls, v):
        if not v:
            raise ValueError('At least one root required')
        # Detect duplicates
        seen = set()
        for r in v:
            key = (r.platform, r.username.lower())
            if key in seen:
                raise ValueError(f'Duplicate root: {r.platform}:{r.username}')
            seen.add(key)
        return v


class ProfileOutExtended(BaseModel):
    """Extended profile information for multi-related response."""
    platform: str
    username: str
    full_name: Optional[str]
    profile_url: Optional[str]
    photo_url: Optional[str]
    is_root: bool = Field(False, description="True if this profile was one of the input roots")
    depth_level: int = Field(0, description="Distance from nearest root (0=root, 1=direct connection, etc.)")
    updated_at: Optional[str] = Field(None, description="Last update timestamp from DB")


class RelationOutExtended(BaseModel):
    """Extended relation information for multi-related response."""
    platform: str
    source: str
    target: str
    type: str
    created_at: Optional[str] = Field(None, description="When this relation was first recorded")
    

class MultiRelatedMeta(BaseModel):
    """Metadata about the multi-related query execution."""
    roots_requested: int
    roots_found: int = Field(description="Number of roots that exist in DB")
    total_profiles: int
    total_relations: int
    depth_executed: int
    query_duration_ms: int
    truncated: bool = Field(False, description="True if max_profiles limit was hit")


class MultiRelatedResponse(BaseModel):
    """Response schema for POST /multi-related endpoint.
    
    Returns a subgraph extracted from the database.
    Compatible with multi-scrape response structure for frontend reuse.
    """
    schema_version: int = 2
    root_profiles: List[str] = Field(description="Root profile identifiers: ['platform:username', ...]")
    profiles: List[ProfileOutExtended]
    relations: List[RelationOutExtended]
    meta: MultiRelatedMeta
    warnings: List[dict] = Field(default_factory=list)
