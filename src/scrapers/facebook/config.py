"""
Configuración centralizada para el scraper de Facebook.
"""
from pydantic import BaseModel, Field


class FacebookConfig(BaseModel):
    """Configuración para el scraper de Facebook."""
    
    base_url: str = Field(
        default="https://www.facebook.com/",
        description="URL base de Facebook"
    )
    
    modal_scroll_pause: float = Field(
        default=3.0,
        description="Tiempo de pausa (segundos) entre scrolls en modales"
    )
    
    max_friends_to_scrape: int = Field(
        default=5000,
        description="Número máximo de amigos a scrapear por lista"
    )
    
    headless: bool = Field(
        default=True,
        description="Ejecutar navegador en modo headless"
    )
    
    timeout_navigation: int = Field(
        default=30000,
        description="Timeout para navegación (milisegundos)"
    )
    
    timeout_selectors: int = Field(
        default=10000,
        description="Timeout para espera de selectores (milisegundos)"
    )
    
    max_retry_attempts: int = Field(
        default=3,
        description="Número máximo de reintentos en caso de error"
    )
    
    max_scrolls: int = Field(
        default=20,
        description="Número máximo de scrolls en listados"
    )
    
    scroll_pause_ms: int = Field(
        default=3500,
        description="Pausa entre scrolls (milisegundos)"
    )
    
    max_no_new: int = Field(
        default=6,
        description="Número de scrolls sin nuevos elementos antes de detenerse"
    )
    
    max_friends: int = Field(
        default=500,
        description="Número máximo de amigos a procesar (para limitar scraping)"
    )
    
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        description="User Agent por defecto si no se proporciona uno específico"
    )


# Instancia global de configuración
facebook_config = FacebookConfig()

