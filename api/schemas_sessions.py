"""
Esquemas Pydantic para gestión de sesiones de scraping (BYOS - Bring Your Own Session).

Estos esquemas validan la entrada/salida de la API de sesiones donde los analistas
vinculan sus propias cuentas de redes sociales.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime


class CookieItem(BaseModel):
    """
    Representa una cookie individual exportada del navegador.
    Formato estándar de Playwright/EditThisCookie.
    """
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: Optional[float] = None
    httpOnly: Optional[bool] = None
    secure: Optional[bool] = None
    sameSite: Optional[Literal["Strict", "Lax", "None"]] = None


class SessionCreate(BaseModel):
    """
    Datos para crear o actualizar una sesión de scraping.
    
    El analista proporciona las cookies exportadas de su navegador
    después de iniciar sesión manualmente en la plataforma.
    """
    plataforma: Literal['facebook', 'instagram', 'x'] = Field(
        ...,
        description="Plataforma de red social"
    )
    
    cookies: List[CookieItem] = Field(
        ...,
        min_length=1,
        description="Lista de cookies exportadas del navegador"
    )
    
    user_agent: Optional[str] = Field(
        None,
        max_length=500,
        description="User agent del navegador usado (opcional pero recomendado)"
    )
    
    proxy_url: Optional[str] = Field(
        None,
        max_length=255,
        description="URL del proxy (http://user:pass@ip:port)"
    )
    
    @field_validator('cookies')
    @classmethod
    def validate_cookies_not_empty(cls, v):
        """Valida que haya al menos una cookie."""
        if not v or len(v) == 0:
            raise ValueError("Debe proporcionar al menos una cookie")
        return v
    
    @field_validator('user_agent')
    @classmethod
    def validate_user_agent(cls, v):
        """Si se proporciona user agent, validar que no esté vacío."""
        if v is not None and len(v.strip()) == 0:
            raise ValueError("User agent no puede estar vacío")
        return v


class SessionStorageStateCreate(BaseModel):
    """
    Alternativa: recibir directamente el storage_state completo de Playwright.
    Más flexible si el frontend ya tiene el formato completo.
    """
    plataforma: Literal['facebook', 'instagram', 'x']
    storage_state: Dict[str, Any] = Field(
        ...,
        description="Storage state completo de Playwright (incluye cookies, origins, localStorage)"
    )
    user_agent: Optional[str] = None
    proxy_url: Optional[str] = None
    
    @field_validator('storage_state')
    @classmethod
    def validate_storage_state(cls, v):
        """Valida que el storage_state tenga cookies."""
        if 'cookies' not in v or not v['cookies']:
            raise ValueError("storage_state debe contener cookies")
        return v


class SessionStatusResponse(BaseModel):
    """
    Respuesta con el estado de una sesión.
    NUNCA incluye las cookies por seguridad.
    """
    plataforma: Literal['facebook', 'instagram', 'x']
    estado: Literal['activa', 'caducada', 'bloqueada']
    ultima_actividad: datetime
    error_count: Optional[int] = Field(
        default=0,
        description="Contador de errores consecutivos"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "plataforma": "facebook",
                "estado": "activa",
                "ultima_actividad": "2025-12-18T10:30:00Z",
                "error_count": 0
            }
        }


class SessionListResponse(BaseModel):
    """
    Lista de todas las sesiones del usuario con su estado.
    """
    sesiones: List[SessionStatusResponse]
    
    class Config:
        json_schema_extra = {
            "example": {
                "sesiones": [
                    {
                        "plataforma": "facebook",
                        "estado": "activa",
                        "ultima_actividad": "2025-12-18T10:30:00Z",
                        "error_count": 0
                    },
                    {
                        "plataforma": "x",
                        "estado": "caducada",
                        "ultima_actividad": "2025-12-15T08:15:00Z",
                        "error_count": 3
                    }
                ]
            }
        }


class SessionDeleteResponse(BaseModel):
    """Confirmación de eliminación de sesión."""
    mensaje: str
    plataforma: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "mensaje": "Sesión de facebook eliminada exitosamente",
                "plataforma": "facebook"
            }
        }
