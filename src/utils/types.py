from typing import TypedDict, NotRequired


class UserItem(TypedDict):
    nombre_usuario: str
    username_usuario: str
    link_usuario: str
    foto_usuario: str
    post_url: NotRequired[str]
    reaction_type: NotRequired[str]
