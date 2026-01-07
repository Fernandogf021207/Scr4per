"""
Modelos SQLAlchemy para la base de datos del scraper.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import enum

Base = declarative_base()


# ==================================================================
# ENUMS
# ==================================================================

class AccountStatus(enum.Enum):
    """Estados posibles de una cuenta en el pool global."""
    ACTIVE = "active"       # Disponible para uso
    BUSY = "busy"           # En uso actualmente
    COOLDOWN = "cooldown"   # Esperando antes de reusar
    SUSPENDED = "suspended" # Temporalmente deshabilitada (errores)
    BANNED = "banned"       # Permanentemente bloqueada


# ==================================================================
# MODELOS
# ==================================================================

class ScraperAccount(Base):
    """
    Modelo para el pool global de cuentas de scraping.
    Estas son cuentas "bot" propiedad del sistema que se rotan automáticamente.
    
    DIFERENCIA CON sesiones_scraping:
    - sesiones_scraping: Cookies del analista (BYOS - Bring Your Own Session)
    - scraper_accounts: Cuentas propiedad del sistema (Pool rotativo)
    """
    __tablename__ = 'scraper_accounts'
    __table_args__ = {'schema': 'entidades'}
    
    # Identificación
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False)  # 'facebook', 'instagram', 'x'
    username = Column(String(100), nullable=False)  # Email o handle interno
    
    # Credenciales
    cookies = Column(JSONB, nullable=False)  # Storage state de Playwright
    proxy_url = Column(Text, nullable=True)  # Proxy asociado (opcional)
    
    # Gestión de Estado y Rotación
    status = Column(
        SQLEnum(AccountStatus, name='account_status_enum', schema='entidades', values_callable=lambda obj: [e.value for e in obj]),
        default=AccountStatus.ACTIVE,
        nullable=False
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True)  # NULL = nunca usada
    error_count = Column(Integer, default=0, nullable=False)
    
    # Metadatos
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    notes = Column(Text, nullable=True)  # Notas del admin
    
    def __repr__(self):
        return f"<ScraperAccount(id={self.id}, platform={self.platform}, username={self.username}, status={self.status.value})>"
    
    def to_dict(self):
        """Convierte el modelo a diccionario (sin exponer cookies por seguridad)."""
        return {
            'id': self.id,
            'platform': self.platform,
            'username': self.username,
            'status': self.status.value,
            'proxy_url': self.proxy_url,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'error_count': self.error_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'notes': self.notes
        }
    
    @property
    def is_available(self) -> bool:
        """Verifica si la cuenta está disponible para usar."""
        return self.status == AccountStatus.ACTIVE
    
    @property
    def should_suspend(self) -> bool:
        """Verifica si la cuenta debe ser suspendida por exceso de errores."""
        return self.error_count >= 5
    
    @property
    def storage_state(self) -> dict:
        """
        Retorna el storage_state de Playwright desde el campo cookies.
        Asume que cookies es un JSONB con la estructura de Playwright.
        """
        if isinstance(self.cookies, dict):
            return self.cookies
        return {'cookies': self.cookies, 'origins': []}
