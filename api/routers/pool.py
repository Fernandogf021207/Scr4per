"""
Router para gestión del pool global de cuentas de scraping.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from ..db import get_sqlalchemy_session
from src.services.session_manager import SessionManager

router = APIRouter(prefix="/pool", tags=["pool"])


@router.get("/status")
def get_pool_status(platform: Optional[str] = None):
    """
    Obtiene el estado actual del pool de cuentas.
    
    Query Params:
        platform (opcional): Filtrar por plataforma ('facebook', 'instagram', 'x')
    
    Returns:
        {
            "platform": "facebook" | "all",
            "total": 10,
            "active": 7,
            "busy": 2,
            "cooldown": 0,
            "suspended": 1,
            "banned": 0
        }
    """
    db: Session = get_sqlalchemy_session()
    session_manager = SessionManager()
    
    try:
        stats = session_manager.get_pool_status(platform, db)
        
        return {
            "platform": platform or "all",
            **stats
        }
    finally:
        db.close()


@router.post("/reset-cooldown")
def reset_cooldown_accounts():
    """
    Resetea todas las cuentas en cooldown a active.
    Reduce error_count en 1 por cada cuenta.
    
    Útil para ejecutar manualmente o via cron job cada 1 hora.
    
    Returns:
        {"mensaje": "X cuentas reseteadas de cooldown"}
    """
    db: Session = get_sqlalchemy_session()
    session_manager = SessionManager()
    
    try:
        # Contar antes
        stats_before = session_manager.get_pool_status(None, db)
        cooldown_count = stats_before['cooldown']
        
        # Resetear
        session_manager.reset_cooldown_accounts(db)
        
        return {
            "mensaje": f"{cooldown_count} cuentas reseteadas de cooldown a active",
            "antes": stats_before,
            "despues": session_manager.get_pool_status(None, db)
        }
    finally:
        db.close()
