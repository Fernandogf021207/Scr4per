from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from ..schemas import (
    PersonaObjetivoIn, PersonaObjetivoOut,
    IdentidadDigitalIn, IdentidadDigitalOut
)
from ..db import get_conn
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/targets", tags=["targets"])

# ==================================================================
# PERSONAS OBJETIVO
# ==================================================================

@router.get("/personas", response_model=List[PersonaObjetivoOut])
def list_personas(limit: int = 100, offset: int = 0):
    """Lista personas objetivo."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id_persona, nombre_completo, curp, datos_adicionales, fecha_creacion 
                FROM entidades.personas_objetivo 
                ORDER BY fecha_creacion DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
            results = []
            for row in cur.fetchall():
                datos_out = row['datos_adicionales'] or {}
                results.append({
                    "id_persona": row['id_persona'],
                    "nombre_completo": row['nombre_completo'],
                    "curp": row['curp'],
                    "rfc": datos_out.get('rfc'),
                    "fecha_nacimiento": datos_out.get('fecha_nacimiento'),
                    "datos_adicionales": datos_out,
                    "fecha_creacion": row['fecha_creacion'],
                    "creado_por": None
                })
            return results
    finally:
        conn.close()

@router.post("/personas", response_model=PersonaObjetivoOut)
def create_persona(persona: PersonaObjetivoIn):
    """Crea una nueva Persona Objetivo."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Preparar datos adicionales (RFC y fecha van aquí según MD)
            datos = persona.datos_adicionales or {}
            if persona.rfc:
                datos['rfc'] = persona.rfc
            if persona.fecha_nacimiento:
                datos['fecha_nacimiento'] = persona.fecha_nacimiento
            
            import json
            datos_json = json.dumps(datos)

            # Insertar persona (Estructura estricta del MD)
            cur.execute("""
                INSERT INTO entidades.personas_objetivo 
                (nombre_completo, curp, datos_adicionales)
                VALUES (%s, %s, %s)
                RETURNING id_persona, nombre_completo, curp, datos_adicionales, fecha_creacion
            """, (
                persona.nombre_completo,
                persona.curp,
                datos_json
            ))
            row = cur.fetchone()
            conn.commit()
            
            # Mapear respuesta
            datos_out = row['datos_adicionales'] or {}
            return {
                "id_persona": row['id_persona'],
                "nombre_completo": row['nombre_completo'],
                "curp": row['curp'],
                "rfc": datos_out.get('rfc'),
                "fecha_nacimiento": datos_out.get('fecha_nacimiento'),
                "datos_adicionales": datos_out,
                "fecha_creacion": row['fecha_creacion'],
                "creado_por": None
            }
    except Exception as e:
        logger.error(f"Error creando persona: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/personas/{id_persona}", response_model=PersonaObjetivoOut)
def get_persona(id_persona: int):
    """Obtiene detalles de una Persona Objetivo."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id_persona, nombre_completo, curp, datos_adicionales, fecha_creacion 
                FROM entidades.personas_objetivo 
                WHERE id_persona = %s
            """, (id_persona,))
            row = cur.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="Persona no encontrada")
            
            datos_out = row['datos_adicionales'] or {}
            return {
                "id_persona": row['id_persona'],
                "nombre_completo": row['nombre_completo'],
                "curp": row['curp'],
                "rfc": datos_out.get('rfc'),
                "fecha_nacimiento": datos_out.get('fecha_nacimiento'),
                "datos_adicionales": datos_out,
                "fecha_creacion": row['fecha_creacion'],
                "creado_por": None
            }
    finally:
        conn.close()

# ==================================================================
# IDENTIDADES DIGITALES
# ==================================================================

@router.get("/identidades", response_model=List[IdentidadDigitalOut])
def list_identidades(limit: int = 100, offset: int = 0):
    """Lista todas las identidades digitales."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM entidades.identidades_digitales
                ORDER BY fecha_creacion DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            return cur.fetchall()
    finally:
        conn.close()

@router.post("/identidades", response_model=IdentidadDigitalOut)
def add_identidad(identidad: IdentidadDigitalIn):
    """Agrega una Identidad Digital a una Persona."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Verificar si ya existe
            cur.execute("""
                SELECT id_identidad FROM entidades.identidades_digitales
                WHERE id_persona = %s AND plataforma = %s AND usuario_o_url = %s
            """, (identidad.id_persona, identidad.plataforma, identidad.usuario_o_url))
            
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Identidad ya registrada para esta persona")
            
            # Insertar
            cur.execute("""
                INSERT INTO entidades.identidades_digitales
                (id_persona, plataforma, usuario_o_url, estado)
                VALUES (%s, %s, %s, 'pendiente')
                RETURNING *
            """, (identidad.id_persona, identidad.plataforma, identidad.usuario_o_url))
            
            row = cur.fetchone()
            conn.commit()
            
            return row
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error agregando identidad: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/identidades/{id_identidad}", response_model=IdentidadDigitalOut)
def get_identidad(id_identidad: int):
    """Obtiene detalles de una Identidad Digital."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM entidades.identidades_digitales WHERE id_identidad = %s
            """, (id_identidad,))
            row = cur.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="Identidad no encontrada")
                
            return row
    finally:
        conn.close()

@router.get("/personas/{id_persona}/identidades", response_model=List[IdentidadDigitalOut])
def list_identidades_persona(id_persona: int):
    """Lista todas las identidades de una persona."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM entidades.identidades_digitales WHERE id_persona = %s
            """, (id_persona,))
            return cur.fetchall()
    finally:
        conn.close()
