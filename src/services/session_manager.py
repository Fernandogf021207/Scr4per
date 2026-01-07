"""
Session Manager: Gestor de pool global de cuentas de scraping.

Implementa lógica de rotación automática con bloqueo pesimista (FOR UPDATE SKIP LOCKED)
para evitar condiciones de carrera en alta concurrencia.
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime

from db.models import ScraperAccount, AccountStatus

logger = logging.getLogger(__name__)


class ResourceExhaustedException(Exception):
    """Se lanza cuando no hay cuentas disponibles en el pool."""
    pass


class SessionManager:
    """
    Gestor del pool global de cuentas.
    
    Responsabilidades:
    1. Seleccionar cuenta disponible con rotación LRU (Least Recently Used)
    2. Bloqueo pesimista para evitar race conditions
    3. Gestión de estados (active, busy, cooldown, suspended, banned)
    4. Circuit breaker automático (suspende cuentas con muchos errores)
    """
    
    def __init__(self, cooldown_threshold: int = 5, suspend_threshold: int = 5):
        """
        Args:
            cooldown_threshold: Número de errores antes de pasar a cooldown
            suspend_threshold: Número de errores antes de suspender permanentemente
        """
        self.cooldown_threshold = cooldown_threshold
        self.suspend_threshold = suspend_threshold
    
    def checkout_account(self, platform: str, db: Session) -> ScraperAccount:
        """
        Obtiene una cuenta disponible del pool y la bloquea atómicamente.
        
        Lógica:
        1. Busca cuentas con status='active' para la plataforma
        2. Ordena por last_used_at ASC NULLS FIRST (prioriza nunca usadas, luego LRU)
        3. Usa FOR UPDATE SKIP LOCKED para evitar deadlocks
        4. Cambia estado a 'busy' y actualiza last_used_at
        5. Hace commit para liberar el lock
        
        Args:
            platform: Plataforma objetivo ('facebook', 'instagram', 'x')
            db: Sesión de SQLAlchemy
            
        Returns:
            ScraperAccount bloqueada y lista para usar
            
        Raises:
            ResourceExhaustedException: Si no hay cuentas disponibles
        """
        logger.info(f"Buscando cuenta disponible para plataforma: {platform}")
        
        # Query con bloqueo pesimista
        # SKIP LOCKED: Si otra transacción ya bloqueó la fila, saltarla y seguir
        account = db.query(ScraperAccount).filter(
            ScraperAccount.platform == platform,
            ScraperAccount.status == AccountStatus.ACTIVE
        ).order_by(
            ScraperAccount.last_used_at.asc().nullsfirst()  # Nulls primero (nunca usadas)
        ).with_for_update(
            skip_locked=True  # CRÍTICO: Evita deadlocks en concurrencia
        ).first()
        
        if not account:
            logger.error(f"No hay cuentas disponibles para {platform}")
            raise ResourceExhaustedException(
                f"No hay cuentas activas disponibles para la plataforma '{platform}'. "
                f"Por favor, agregue más cuentas al pool."
            )
        
        # Cambiar estado a 'busy' y actualizar timestamp
        account.status = AccountStatus.BUSY
        account.last_used_at = datetime.utcnow()
        
        db.commit()  # Liberar el lock y persistir cambios
        
        logger.info(f"Cuenta bloqueada: {account.username} (ID: {account.id})")
        return account
    
    def release_account(self, account_id: int, success: bool, db: Session, error_message: Optional[str] = None):
        """
        Libera una cuenta después del scraping y actualiza su estado.
        
        Lógica de Estados:
        - Éxito (success=True):
            * Estado -> active
            * error_count -> 0
        
        - Fallo (success=False):
            * error_count += 1
            * Si error_count >= suspend_threshold (5): Estado -> suspended
            * Si error_count >= cooldown_threshold (3): Estado -> cooldown
            * Si no: Estado -> active (retry inmediato)
        
        Args:
            account_id: ID de la cuenta a liberar
            success: True si el scraping fue exitoso, False si falló
            db: Sesión de SQLAlchemy
            error_message: Mensaje de error opcional (para logging)
        """
        account = db.query(ScraperAccount).filter(ScraperAccount.id == account_id).first()
        
        if not account:
            logger.warning(f"Intentando liberar cuenta inexistente: {account_id}")
            return
        
        if success:
            # Éxito: Limpiar errores y volver a activa
            account.status = AccountStatus.ACTIVE
            account.error_count = 0
            logger.info(f"Cuenta liberada exitosamente: {account.username} (ID: {account_id})")
        else:
            # Fallo: Incrementar contador y decidir estado
            account.error_count += 1
            
            if account.error_count >= self.suspend_threshold:
                account.status = AccountStatus.SUSPENDED
                logger.error(
                    f"Cuenta SUSPENDIDA por exceso de errores: {account.username} "
                    f"(ID: {account_id}, Errores: {account.error_count})"
                )
            elif account.error_count >= self.cooldown_threshold:
                account.status = AccountStatus.COOLDOWN
                logger.warning(
                    f"Cuenta en COOLDOWN: {account.username} "
                    f"(ID: {account_id}, Errores: {account.error_count})"
                )
            else:
                account.status = AccountStatus.ACTIVE
                logger.warning(
                    f"Cuenta liberada con error: {account.username} "
                    f"(ID: {account_id}, Errores: {account.error_count})"
                )
            
            if error_message:
                logger.error(f"Detalle del error: {error_message}")
        
        db.commit()
    
    def mark_as_suspended(self, account_id: int, db: Session, reason: str = ""):
        """
        Marca una cuenta como suspendida (sesión expirada).
        
        A diferencia de banned, suspended implica que la cuenta puede ser
        recuperada actualizando las cookies.
        
        Args:
            account_id: ID de la cuenta
            db: Sesión de SQLAlchemy
            reason: Razón de la suspensión (para auditoría)
        """
        account = db.query(ScraperAccount).filter(ScraperAccount.id == account_id).first()
        
        if account:
            account.status = AccountStatus.SUSPENDED
            if reason:
                account.notes = f"[SUSPENDED {datetime.utcnow().isoformat()}] {reason}"
            db.commit()
            
            logger.error(
                f"Cuenta suspendida: {account.username} (ID: {account_id}). "
                f"Razón: {reason}. Se requiere actualizar cookies."
            )
    
    def mark_as_banned(self, account_id: int, db: Session, reason: str = ""):
        """
        Marca una cuenta como permanentemente bloqueada.
        Útil para cuentas que detectaron checkpoint/baneo real de la plataforma.
        
        Args:
            account_id: ID de la cuenta
            db: Sesión de SQLAlchemy
            reason: Razón del baneo (para auditoría)
        """
        account = db.query(ScraperAccount).filter(ScraperAccount.id == account_id).first()
        
        if account:
            account.status = AccountStatus.BANNED
            if reason:
                account.notes = f"[BANNED {datetime.utcnow().isoformat()}] {reason}"
            db.commit()
            
            logger.critical(
                f"Cuenta marcada como BANEADA: {account.username} (ID: {account_id}). "
                f"Razón: {reason}"
            )
    
    def reset_cooldown_accounts(self, db: Session):
        """
        Resetea todas las cuentas en cooldown a active.
        Útil para ejecutar periódicamente (cron job cada 1 hora).
        
        Args:
            db: Sesión de SQLAlchemy
        """
        cooldown_accounts = db.query(ScraperAccount).filter(
            ScraperAccount.status == AccountStatus.COOLDOWN
        ).all()
        
        for account in cooldown_accounts:
            account.status = AccountStatus.ACTIVE
            account.error_count = max(0, account.error_count - 1)  # Reducir un poco el contador
        
        db.commit()
        logger.info(f"Reseteadas {len(cooldown_accounts)} cuentas de cooldown a active")
    
    def get_pool_status(self, platform: Optional[str], db: Session) -> dict:
        """
        Obtiene estadísticas del pool de cuentas.
        
        Args:
            platform: Filtrar por plataforma (opcional)
            db: Sesión de SQLAlchemy
            
        Returns:
            Diccionario con contadores por estado
        """
        query = db.query(ScraperAccount)
        if platform:
            query = query.filter(ScraperAccount.platform == platform)
        
        accounts = query.all()
        
        status_counts = {
            'active': 0,
            'busy': 0,
            'cooldown': 0,
            'suspended': 0,
            'banned': 0,
            'total': len(accounts)
        }
        
        for account in accounts:
            status_counts[account.status.value] += 1
        
        return status_counts
