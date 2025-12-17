"""
Modelos SQLAlchemy para la base de datos.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class SesionScraping(Base):
    """
    Modelo para almacenar las sesiones de scraping por usuario y plataforma.
    Cada usuario tiene sus propias cookies y configuración de proxy.
    """
    __tablename__ = 'sesiones_scraping'
    __table_args__ = {'schema': 'entidades'}
    
    id_sesion = Column(Integer, primary_key=True, autoincrement=True)
    id_usuario = Column(Integer, ForeignKey('entidades.usuarios.id_usuario'), nullable=False)
    plataforma = Column(String(20), nullable=False)  # 'facebook', 'instagram', 'x'
    cookies = Column(JSON, nullable=False)  # Cookies exportadas de Playwright (storage_state)
    proxy_url = Column(Text, nullable=True)  # Proxy residencial (http://user:pass@ip:port)
    user_agent = Column(Text, nullable=True)
    estado = Column(String(20), default='activa', nullable=False)  # activa, caducada, bloqueada
    ultima_actividad = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<SesionScraping(id={self.id_sesion}, usuario={self.id_usuario}, plataforma={self.plataforma}, estado={self.estado})>"
    
    def to_dict(self):
        """Convierte el modelo a diccionario para APIs."""
        return {
            'id_sesion': self.id_sesion,
            'id_usuario': self.id_usuario,
            'plataforma': self.plataforma,
            'cookies': self.cookies,
            'proxy_url': self.proxy_url,
            'user_agent': self.user_agent,
            'estado': self.estado,
            'ultima_actividad': self.ultima_actividad.isoformat() if self.ultima_actividad else None
        }
    
    @property
    def is_active(self) -> bool:
        """Verifica si la sesión está activa."""
        return self.estado == 'activa'
    
    @property
    def storage_state(self) -> dict:
        """
        Retorna las cookies en formato storage_state de Playwright.
        Asume que self.cookies ya está en el formato correcto.
        """
        if isinstance(self.cookies, dict):
            return self.cookies
        return {}
