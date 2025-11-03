from typing import Optional, Literal, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator

class ProfileIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    username: str
    full_name: Optional[str] = None
    profile_url: Optional[str] = None
    photo_url: Optional[str] = None

class Profile(ProfileIn):
    id: int

class RelationshipIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    owner_username: str
    related_username: str
    rel_type: str
    updated_at: Optional[datetime] = None

    @validator('rel_type')
    def _normalize_rel_type(cls, v: str) -> str:
        if not v:
            raise ValueError('rel_type requerido')
        raw = v.strip().lower()
        # Normalización español → inglés
        mapping = {
            'seguidor': 'follower',
            'seguidores': 'follower',
            'seguido': 'following',
            'seguidos': 'following',
            'amigo': 'friend',
            'amigos': 'friend',
            'comentado': 'commented',
            'comentó': 'commented',
            'comentados': 'commented',
            'reaccionado': 'reacted',
            'reaccionó': 'reacted',
            'reacciones': 'reacted',
        }
        canon = mapping.get(raw, raw)
        allowed = {'follower', 'following', 'followed', 'friend', 'commented', 'reacted'}
        if canon not in allowed:
            raise ValueError('rel_type inválido')
        return canon

class PostIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    owner_username: str
    post_url: str

class CommentIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    post_url: str
    commenter_username: str

class ReactionIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    post_url: str
    reactor_username: str
    reaction_type: Optional[str] = None

class ScrapeRequest(BaseModel):
    url: str
    platform: Literal['x', 'instagram', 'facebook']
    max_photos: Optional[int] = 5

class GraphSessionIn(BaseModel):
    platform: Literal['x','instagram','facebook']
    owner_username: str
    elements: Dict[str, Any]
    style: Optional[Dict[str,Any]] = None
    layout: Optional[Dict[str,Any]] = None

class ExportInput(BaseModel):
    perfil_objetivo: Dict[str, Any] = Field(alias="Perfil objetivo")
    perfiles_relacionados: List[Dict[str, Any]] = Field(alias="Perfiles relacionados")
    class Config:
        allow_population_by_field_name = True


# ==========================
# Multi-scrape (schema v2)
# ==========================

USERNAME_REGEX = r'^[A-Za-z0-9._-]{2,60}$'


class MultiScrapeRoot(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    username: str  # 2..60, alfanumérico + ._-
    max_photos: int = Field(5, ge=0, le=50)

    @validator('username')
    def _username_valid(cls, v: str):
        import re
        if not re.match(USERNAME_REGEX, v or ''):
            raise ValueError('invalid username (2..60, A-Za-z0-9._-)')
        return v


class MultiScrapeRequest(BaseModel):
    roots: List[MultiScrapeRoot] = Field(..., description="1..5 roots")
    headless: bool = True
    max_concurrency: Optional[int] = Field(None, ge=1, le=3)
    persist: bool = True
    strict_sessions: bool = False

    @validator('roots')
    def _check_roots(cls, v: List[MultiScrapeRoot]):
        if not v:
            raise ValueError('roots must contain at least 1 item')
        if len(v) > 5:
            raise ValueError('Max 5 roots')
        return v

    @validator('max_concurrency', always=True)
    def _default_max_concurrency(cls, v: Optional[int], values: Dict[str, Any]):
        if v is not None:
            return v
        roots = values.get('roots') or []
        return 1 if len(roots) <= 1 else 3


class MultiScrapeProfileItem(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    username: str
    full_name: Optional[str] = None
    profile_url: Optional[str] = None
    photo_url: Optional[str] = None
    sources: List[str] = []

    @validator('username')
    def _username_valid(cls, v: str):
        import re
        if not re.match(USERNAME_REGEX, v or ''):
            raise ValueError('invalid username (2..60, A-Za-z0-9._-)')
        return v


class MultiScrapeRelationItem(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    source: str
    target: str
    type: Literal['follower', 'following', 'friend']

    @validator('source', 'target')
    def _username_valid(cls, v: str):
        import re
        if not re.match(USERNAME_REGEX, v or ''):
            raise ValueError('invalid username (2..60, A-Za-z0-9._-)')
        return v


class MultiScrapeWarning(BaseModel):
    code: str
    message: str


class MultiScrapeResponse(BaseModel):
    schema_version: int = 2
    root_profiles: List[str]
    profiles: List[MultiScrapeProfileItem]
    relations: List[MultiScrapeRelationItem]
    warnings: List[MultiScrapeWarning] = []
    meta: Dict[str, Any]