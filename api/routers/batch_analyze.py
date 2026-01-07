"""
Router para análisis de identidades digitales con integración a casos.
Implementa la lógica de Batch Analysis con semáforo global y pool de cuentas.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session as SQLAlchemySession

from ..schemas_batch import (
    BatchAnalysisRequest,
    BatchAnalysisResponse
)
from ..db import get_conn, get_sqlalchemy_session
from .analyze import ejecutar_analisis_background, GLOBAL_SEMAPHORE
from src.utils.event_manager import event_manager
from src.services.session_manager import SessionManager, ResourceExhaustedException
from src.utils.exceptions import (
    SessionExpiredException,
    AccountBannedException,
    NetworkException,
    StorageException,
    ScraperException,
    log_exception
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["analyze-batch"])

# ==================================================================
# REPOSITORY FUNCTIONS (Acceso a BD)
# ==================================================================

def get_identidades_por_personas(conn, personas_ids: List[int], id_caso: int) -> List[dict]:
    """
    Obtiene TODAS las identidades digitales de las personas solicitadas.
    Si ya existen en el caso, trae su estado actual.
    Si no existen, trae estado NULL (para luego hacer upsert).
    """
    if not personas_ids:
        return []
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                i.id_identidad,
                i.id_persona,
                i.plataforma,
                i.usuario_o_url,
                ai.estado,
                ai.fecha_analisis as ultimo_analisis
            FROM entidades.identidades_digitales i
            LEFT JOIN casos.analisis_identidad ai 
                ON i.id_identidad = ai.id_identidad AND ai.idcaso = %s
            WHERE i.id_persona = ANY(%s)
        """, (id_caso, personas_ids))
        return [dict(row) for row in cur.fetchall()]

def ensure_identidad_en_caso(conn, id_identidad: int, id_caso: int):
    """
    Asegura que la identidad esté registrada en el caso (Upsert).
    Si no existe, la crea con estado 'pendiente'.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO casos.analisis_identidad (idcaso, id_identidad, estado)
            VALUES (%s, %s, 'pendiente')
            ON CONFLICT (idcaso, id_identidad) DO NOTHING
        """, (id_caso, id_identidad))
        conn.commit()

def update_identidad_estado(conn, id_identidad: int, estado: str, id_caso: int):
    """Actualiza el estado de una identidad digital en el caso."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE casos.analisis_identidad
            SET estado = %s::casos.estado_analisis_enum
            WHERE id_identidad = %s AND idcaso = %s
        """, (estado, id_identidad, id_caso))
        conn.commit()
    
    # Emitir evento SSE
    asyncio.create_task(event_manager.broadcast_status(id_identidad, estado, id_caso))

async def ejecutar_analisis_con_pool(
    id_identidad: int,
    plataforma: str,
    usuario_o_url: str,
    context: dict,
    max_photos: int,
    headless: bool,
    max_depth: int,
    max_retries: int = 3,
    _retry_count: int = 0,
    _attempted_accounts: List[int] = None
):
    """
    Wrapper que ejecuta el análisis con control de concurrencia, pool de cuentas y retry automático.
    
    Maneja excepciones de forma inteligente para proteger el pool:
    - SessionExpiredException → Suspender cuenta y REINTENTAR con otra cuenta (hasta max_retries)
    - AccountBannedException → Marcar cuenta como banned y REINTENTAR con otra cuenta
    - NetworkException → Incrementar error leve y REINTENTAR con otra cuenta
    - StorageException → Abortar con HTTP 500 (problema crítico de FTP)
    
    Flujo:
    1. Adquiere semáforo (control de hardware: max N navegadores)
    2. Obtiene cuenta del pool (control de recursos: cuentas disponibles)
    3. Ejecuta scraping con las credenciales de la cuenta
    4. Maneja excepciones específicas del scraper
    5. Si error recuperable: Suspende/Marca cuenta, intenta con otra (hasta max_retries)
    6. Libera cuenta según resultado y tipo de error
    7. Libera semáforo
    
    Args:
        max_retries: Número máximo de intentos totales (default: 3)
        _retry_count: Contador interno de reintentos (NO pasar manualmente)
        _attempted_accounts: Lista de IDs de cuentas ya intentadas (NO pasar manualmente)
    """
    session_manager = SessionManager()
    db: Optional[SQLAlchemySession] = None
    account = None
    
    # Inicializar lista de cuentas intentadas en el primer intento
    if _attempted_accounts is None:
        _attempted_accounts = []
    
    # Verificar límite de reintentos
    if _retry_count >= max_retries:
        logger.error(
            f"[ID:{id_identidad}] Se alcanzó el límite de reintentos ({max_retries}). "
            f"Cuentas intentadas: {_attempted_accounts}"
        )
        conn_psycopg = get_conn()
        try:
            update_identidad_estado(
                conn_psycopg, 
                id_identidad, 
                'error', 
                context.get('id_caso')
            )
        finally:
            conn_psycopg.close()
        return  # Salir sin más reintentos
    
    async with GLOBAL_SEMAPHORE:
        logger.info(
            f"[ID:{id_identidad}] Semáforo adquirido. "
            f"Intento {_retry_count + 1}/{max_retries}"
        )
        
        try:
            # 1. Obtener sesión de SQLAlchemy
            db = get_sqlalchemy_session()
            
            # 2. Obtener cuenta del pool (bloqueo atómico)
            try:
                account = session_manager.checkout_account(plataforma, db)
                
                # Verificar si ya intentamos con esta cuenta
                if account.id in _attempted_accounts:
                    logger.warning(
                        f"[ID:{id_identidad}] Cuenta {account.username} (ID:{account.id}) "
                        f"ya fue intentada. Liberando y buscando otra..."
                    )
                    session_manager.release_account(account.id, success=True, db=db)
                    db.close()
                    # Reintentar inmediatamente con otra cuenta
                    return await ejecutar_analisis_con_pool(
                        id_identidad, plataforma, usuario_o_url, context,
                        max_photos, headless, max_depth, max_retries,
                        _retry_count, _attempted_accounts
                    )
                
                # Registrar cuenta intentada
                _attempted_accounts.append(account.id)
                
                logger.info(
                    f"[ID:{id_identidad}] Cuenta asignada: {account.username} "
                    f"(Account ID: {account.id}, Intento: {_retry_count + 1})"
                )
            except ResourceExhaustedException as e:
                logger.error(f"[ID:{id_identidad}] {str(e)}")
                # Actualizar estado en caso
                conn_psycopg = get_conn()
                try:
                    update_identidad_estado(
                        conn_psycopg, 
                        id_identidad, 
                        'error', 
                        context.get('id_caso')
                    )
                finally:
                    conn_psycopg.close()
                # Propagar excepción para que se registre como error
                raise HTTPException(
                    status_code=503,
                    detail=f"No hay cuentas disponibles en el pool para {plataforma}. Reintente más tarde."
                )
            
            # 3. Ejecutar scraping con las credenciales de la cuenta
            # Inyectar cookies, proxy y account_id en el contexto
            context_with_account = {
                **context,
                '_account_id': account.id,  # Para tracking interno y early exit
                '_cookies': account.storage_state,
                '_proxy_url': account.proxy_url
            }
            
            await ejecutar_analisis_background(
                id_identidad, 
                plataforma, 
                usuario_o_url, 
                context_with_account, 
                max_photos, 
                headless, 
                max_depth
            )
            
            # 4. Éxito: Liberar cuenta como exitosa (resetea error_count)
            session_manager.release_account(account.id, success=True, db=db)
            logger.info(
                f"[ID:{id_identidad}] ✅ Análisis exitoso. "
                f"Cuenta {account.username} liberada y limpia."
            )
        
        # 5. Manejo de excepciones específicas del scraper
        except SessionExpiredException as e:
            # Sesión expirada: Suspender cuenta y REINTENTAR con otra
            log_exception(e, logger)
            
            if account and db:
                session_manager.mark_as_suspended(
                    account.id,
                    db,
                    reason=f"Session Expired: {e.message}"
                )
                logger.warning(
                    f"[ID:{id_identidad}] Sesión expirada en cuenta {account.username}. "
                    f"Suspendida. Reintentando con otra cuenta..."
                )
            
            # Cerrar DB antes del retry
            if db:
                db.close()
                db = None
            
            # REINTENTAR con otra cuenta
            return await ejecutar_analisis_con_pool(
                id_identidad, plataforma, usuario_o_url, context,
                max_photos, headless, max_depth, max_retries,
                _retry_count + 1, _attempted_accounts
            )
        
        except AccountBannedException as e:
            # Cuenta baneada: Marcar como banned y REINTENTAR con otra
            log_exception(e, logger)
            
            if account and db:
                session_manager.mark_as_banned(
                    account.id,
                    db,
                    reason=f"Account Banned: {e.message} (Type: {e.ban_type})"
                )
                logger.critical(
                    f"[ID:{id_identidad}] Cuenta {account.username} baneada permanentemente. "
                    f"Reintentando con otra cuenta..."
                )
            
            # Cerrar DB antes del retry
            if db:
                db.close()
                db = None
            
            # REINTENTAR con otra cuenta
            return await ejecutar_analisis_con_pool(
                id_identidad, plataforma, usuario_o_url, context,
                max_photos, headless, max_depth, max_retries,
                _retry_count + 1, _attempted_accounts
            )
        
        except NetworkException as e:
            # Error de red: Incrementar error leve y REINTENTAR con otra cuenta
            log_exception(e, logger)
            
            if account and db:
                # Liberar sin penalizar mucho (incrementa error_count levemente)
                session_manager.release_account(
                    account.id,
                    success=False,
                    db=db,
                    error_message=f"Network Error: {e.message}"
                )
                logger.warning(
                    f"[ID:{id_identidad}] Error de red con cuenta {account.username}. "
                    f"Reintentando con otra cuenta..."
                )
            
            # Cerrar DB antes del retry
            if db:
                db.close()
                db = None
            
            # REINTENTAR con otra cuenta
            return await ejecutar_analisis_con_pool(
                id_identidad, plataforma, usuario_o_url, context,
                max_photos, headless, max_depth, max_retries,
                _retry_count + 1, _attempted_accounts
            )
        
        except StorageException as e:
            # Fallo de almacenamiento (FTP): ERROR CRÍTICO
            log_exception(e, logger)
            
            if account and db:
                # No penalizar la cuenta (no es culpa de ella)
                session_manager.release_account(account.id, success=True, db=db)
            
            # Actualizar estado en caso
            conn_psycopg = get_conn()
            try:
                update_identidad_estado(
                    conn_psycopg, 
                    id_identidad, 
                    'error', 
                    context.get('id_caso')
                )
            finally:
                conn_psycopg.close()
            
            # Abortar con HTTP 500
            logger.critical(f"[ID:{id_identidad}] Fallo crítico de almacenamiento: {e.message}")
            raise HTTPException(
                status_code=500,
                detail=f"Storage Failure: {e.message}"
            )
        
        except ScraperException as e:
            # Otras excepciones del scraper (LayoutChange, etc)
            log_exception(e, logger)
            
            if account and db:
                # Liberar con error leve (puede ser cambio temporal de layout)
                session_manager.release_account(
                    account.id,
                    success=False,
                    db=db,
                    error_message=f"Scraper Error: {e.message}"
                )
            
            # Actualizar estado en caso
            conn_psycopg = get_conn()
            try:
                update_identidad_estado(
                    conn_psycopg, 
                    id_identidad, 
                    'error', 
                    context.get('id_caso')
                )
            finally:
                conn_psycopg.close()
            
            logger.error(f"[ID:{id_identidad}] Scraper exception: {e.message}")
        
        except Exception as e:
            # Excepción genérica: Error inesperado
            logger.error(f"[ID:{id_identidad}] Error inesperado durante análisis: {e}", exc_info=True)
            
            # Liberar cuenta con error
            if account and db:
                session_manager.release_account(
                    account.id, 
                    success=False, 
                    db=db,
                    error_message=f"Unexpected Error: {str(e)}"
                )
            
            # Actualizar estado en caso
            conn_psycopg = get_conn()
            try:
                update_identidad_estado(
                    conn_psycopg, 
                    id_identidad, 
                    'error', 
                    context.get('id_caso')
                )
            finally:
                conn_psycopg.close()
            
            # Re-lanzar para que se registre el error
            raise
        
        finally:
            # 6. Cerrar sesión de SQLAlchemy
            if db:
                db.close()
            
            logger.info(f"[ID:{id_identidad}] Semáforo liberado")

# ==================================================================
# ENDPOINTS
# ==================================================================

@router.post("/batch", response_model=BatchAnalysisResponse)
async def start_batch_analysis_by_persons(
    request: BatchAnalysisRequest, 
    background_tasks: BackgroundTasks
):
    """
    Inicia el análisis en lote para una lista de personas.
    Busca todas las identidades digitales asociadas y las encola para análisis.
    Si las identidades no estaban seleccionadas previamente para el caso, las agrega automáticamente.
    """
    conn = get_conn()
    try:
        # 1. Obtener TODAS las identidades de las personas solicitadas (incluyendo las no seleccionadas)
        identidades = get_identidades_por_personas(conn, request.personas_ids, request.context.id_caso)
        
        iniciadas = []
        omitidas = []
        
        for ident in identidades:
            id_identidad = ident['id_identidad']
            estado = ident['estado'] # Puede ser None si no estaba seleccionada
            ultimo_analisis = ident['ultimo_analisis']
            
            # Si no estaba en el caso (estado is None), la agregamos ahora
            if estado is None:
                ensure_identidad_en_caso(conn, id_identidad, request.context.id_caso)
                estado = 'pendiente' # Asumimos pendiente tras insertar

            # Lógica de filtrado:
            # Si está 'procesando' y hace menos de 10 min, omitir.
            should_process = True
            if estado == 'procesando':
                if ultimo_analisis:
                    tiempo_transcurrido = datetime.now(ultimo_analisis.tzinfo) - ultimo_analisis
                    if tiempo_transcurrido < timedelta(minutes=10):
                        should_process = False
                else:
                    # Si dice procesando pero no tiene fecha, asumimos estancado y procesamos
                    pass
            
            if should_process:
                # Actualizar estado a procesando inmediatamente para evitar doble submit
                update_identidad_estado(conn, id_identidad, 'procesando', request.context.id_caso)
                
                # Encolar tarea con semáforo y pool
                background_tasks.add_task(
                    ejecutar_analisis_con_pool,
                    id_identidad=id_identidad,
                    plataforma=ident['plataforma'],
                    usuario_o_url=ident['usuario_o_url'],
                    context=request.context.dict(),
                    max_photos=request.max_photos,
                    headless=request.headless,
                    max_depth=request.max_depth
                )
                iniciadas.append(id_identidad)
            else:
                omitidas.append(id_identidad)
        
        return BatchAnalysisResponse(
            mensaje="Proceso de análisis en lote iniciado",
            total_identidades_encontradas=len(identidades),
            identidades_iniciadas=iniciadas,
            identidades_omitidas=omitidas,
            detalle=f"Se iniciaron {len(iniciadas)} análisis. {len(omitidas)} omitidos por estar ya en proceso."
        )
        
    finally:
        conn.close()
