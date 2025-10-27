"""Definición de códigos de error y utilidades de clasificación.

Los códigos buscan ser estables y consumibles por capas superiores.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class ErrorCode(str, Enum):
    SELECTOR_MISS = "SELECTOR_MISS"
    EMPTY_LIST = "EMPTY_LIST"
    PRIVATE = "PRIVATE"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"

@dataclass
class ScrapeError:
    code: ErrorCode
    message: str
    platform: str
    context: Optional[str] = None
    phase: Optional[str] = None
    selector_category: Optional[str] = None

    def to_dict(self):
        return {
            "code": self.code.value,
            "message": self.message,
            "platform": self.platform,
            "context": self.context,
            "phase": self.phase,
            "selector_category": self.selector_category,
        }

PRIVATE_KEYWORDS = {
    'instagram': ['Esta cuenta es privada', 'This account is private'],
    'facebook': ["This content isn't available", 'Este contenido no está disponible'],
    'x': ['These posts are protected', 'These Tweets are protected']
}

LOGIN_KEYWORDS = {
    'instagram': ['Inicia sesión', 'Log in'],
    'facebook': ['Inicia sesión', 'Log in'],
    'x': ['Iniciar sesión', 'Log in']
}

def classify_page_state(platform: str, text_content: str) -> ErrorCode | None:
    low = text_content.lower()
    for kw in PRIVATE_KEYWORDS.get(platform, []):
        if kw.lower() in low:
            return ErrorCode.PRIVATE
    for kw in LOGIN_KEYWORDS.get(platform, []):
        if kw.lower() in low:
            return ErrorCode.LOGIN_REQUIRED
    return None
