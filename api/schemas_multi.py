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
    full_name: Optional[str]
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
    roots_requested: int
    roots_processed: int
    build_ms: int
    generated_at: str

class MultiScrapeResponse(BaseModel):
    schema_version: int = 2
    root_profiles: List[str]
    profiles: List[ProfileOut]
    relations: List[RelationOut]
    warnings: List[dict]
    meta: MultiScrapeMeta
