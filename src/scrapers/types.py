from typing import TypedDict, Literal, Optional, List

RelationType = Literal['seguidor','seguido','amigo','comentó','reaccionó']

class UserItem(TypedDict, total=False):
    platform: str
    username_usuario: str
    nombre_mostrado: str
    link_usuario: str
    foto_url: str
    post_url: str
    reaction_type: str

class RelationItem(TypedDict):
    source: str  # user id or link
    target: str  # user id or link
    tipo: RelationType
    platform: str

class ExtractorStats(TypedDict, total=False):
    duration_ms: int
    scrolls: int
    new_items: int
    early_exit: str

class ExtractorResult(TypedDict, total=False):
    items: List[UserItem]
    stats: ExtractorStats
