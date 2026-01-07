"""Configuración para el scraper de Facebook usando Pydantic"""

from pydantic import BaseModel, Field
from typing import Optional


class ScrollConfig(BaseModel):
    """Configuración de scroll para recolección de datos."""
    max_scrolls: int = Field(default=20, description="Número máximo de scrolls")
    pause_ms: int = Field(default=1500, description="Pausa entre scrolls en milisegundos")
    max_no_new: int = Field(default=6, description="Máximo de scrolls sin nuevos elementos antes de parar")


class ValidationConfig(BaseModel):
    """Configuración de validación de sesión (Early Exit)."""
    timeout_seconds: int = Field(default=5, description="Timeout para validación de sesión")
    check_navigation: bool = Field(default=True, description="Verificar presencia de navegación")
    check_login_elements: bool = Field(default=True, description="Verificar elementos de login")
    check_ban_messages: bool = Field(default=True, description="Verificar mensajes de bloqueo")


class RetryConfig(BaseModel):
    """Configuración de reintentos."""
    max_retries: int = Field(default=3, description="Número máximo de reintentos")
    backoff_seconds: float = Field(default=1.0, description="Backoff inicial en segundos")


class ModalConfig(BaseModel):
    """Configuración de manejo de modales."""
    max_attempts: int = Field(default=3, description="Intentos máximos para cerrar modales")
    scroll_pause_ms: int = Field(default=800, description="Pausa después de cerrar modal")


class FacebookScraperConfig(BaseModel):
    """Configuración completa del scraper de Facebook."""
    
    # URLs base
    base_url: str = Field(default="https://www.facebook.com/", description="URL base de Facebook")
    storage_state_path: str = Field(
        default="data/storage/facebook_storage_state.json",
        description="Path al archivo de estado de sesión (deprecated con Pool Global)"
    )
    
    # Configuraciones anidadas
    scroll: ScrollConfig = Field(default_factory=ScrollConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    modal: ModalConfig = Field(default_factory=ModalConfig)
    
    # Timeouts globales
    page_load_timeout: int = Field(default=30000, description="Timeout de carga de página en ms")
    navigation_timeout: int = Field(default=30000, description="Timeout de navegación en ms")
    
    class Config:
        """Configuración de Pydantic."""
        validate_assignment = True


# Instancia global de configuración
FACEBOOK_CONFIG_PYDANTIC = FacebookScraperConfig()

# Mantener compatibilidad con código legacy
FACEBOOK_CONFIG = {
    "base_url": FACEBOOK_CONFIG_PYDANTIC.base_url,
    "storage_state_path": FACEBOOK_CONFIG_PYDANTIC.storage_state_path,
    "scroll": {
        "max_scrolls": FACEBOOK_CONFIG_PYDANTIC.scroll.max_scrolls,
        "pause_ms": FACEBOOK_CONFIG_PYDANTIC.scroll.pause_ms,
        "max_no_new": FACEBOOK_CONFIG_PYDANTIC.scroll.max_no_new,
    },
}


