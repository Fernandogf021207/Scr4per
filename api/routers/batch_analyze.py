"""
Router para análisis de identidades digitales con integración a casos.
Implementa la lógica de Batch Analysis con semáforo global.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
import asyncio
import logging
from datetime import datetime, timedelta

from ..schemas_batch import (
    BatchAnalysisRequest,
    BatchAnalysisResponse
)
from ..db import get_conn
from .analyze import ejecutar_analisis_background, GLOBAL_SEMAPHORE
from src.utils.event_manager import event_manager

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

async def ejecutar_analisis_con_semaforo(
    id_identidad: int,
    plataforma: str,
    usuario_o_url: str,
    context: dict,
    max_photos: int,
    headless: bool,
    max_depth: int
):
    """Wrapper que ejecuta el análisis respetando el semáforo global."""
    async with GLOBAL_SEMAPHORE:
        logger.info(f"Semaforo adquirido para identidad {id_identidad}")
        await ejecutar_analisis_background(
            id_identidad, plataforma, usuario_o_url, context, max_photos, headless, max_depth
        )
        logger.info(f"Semaforo liberado para identidad {id_identidad}")

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
                
                # Encolar tarea con semáforo
                background_tasks.add_task(
                    ejecutar_analisis_con_semaforo,
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
