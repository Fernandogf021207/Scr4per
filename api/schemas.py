from typing import Optional, Literal, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

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
    rel_type: Literal['follower', 'following', 'followed', 'friend', 'commented', 'reacted']
    updated_at: Optional[datetime] = None

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
    model_config = {
        'populate_by_name': True,
    }

# Support multiple export blocks to allow concatenating several objectives
class ExportBlock(BaseModel):
    perfil_objetivo: Dict[str, Any] = Field(alias="Perfil objetivo")
    perfiles_relacionados: List[Dict[str, Any]] = Field(alias="Perfiles relacionados")
    model_config = {
        'populate_by_name': True,
    }

class MultiExportInput(BaseModel):
    # Frontend should send an array of blocks under key "Perfiles"
    bloques: List[ExportBlock] = Field(alias="Perfiles")
    model_config = {
        'populate_by_name': True,
    }