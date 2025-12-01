from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from ..schemas_batch import (
    PersonaIn, IdentidadDigitalIn, VinculoObjetivoCasoIn, 
    SeleccionIdentidadIn, AnalisisIdentidadOut
)
from ..db import get_conn
import logging
import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/targets", tags=["targets"])

# ==================================================================
# SCHEMAS LOCALES (o mover a schemas_batch si se prefiere)
# ==================================================================

class PersonaOut(PersonaIn):
    id_persona: int
    fecha_creacion: Any
    foto: Optional[str] = None
    fecha_nacimiento: Optional[Any] = None

class IdentidadDigitalOut(IdentidadDigitalIn):
    id_identidad: int
    # Estado y análisis ahora viven en casos.analisis_identidad

class VinculoOut(VinculoObjetivoCasoIn):
    id_vinculo: int
    fecha_agregado: Any

# ==================================================================
# PERSONAS (Nueva Tabla entidades.personas)
# ==================================================================

@router.get("/personas", response_model=List[PersonaOut])
def list_personas(limit: int = 100, offset: int = 0):
    """Lista personas (nueva tabla)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    id_persona, nombre, apellido_paterno, apellido_materno,
                    curp, rfc, fecha_nacimiento, tipo_sangre,
                    datos_adicionales, fecha_creacion, foto
                FROM entidades.personas 
                ORDER BY fecha_creacion DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
            results = []
            for row in cur.fetchall():
                results.append(row)
            return results
    finally:
        conn.close()

@router.post("/personas", response_model=PersonaOut)
def create_persona(persona: PersonaIn):
    """Crea una nueva Persona en la tabla actualizada."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            datos_json = json.dumps(persona.datos_adicionales or {})
            
            cur.execute("""
                INSERT INTO entidades.personas 
                (nombre, apellido_paterno, apellido_materno, curp, rfc, fecha_nacimiento, tipo_sangre, datos_adicionales)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING 
                    id_persona, nombre, apellido_paterno, apellido_materno,
                    curp, rfc, fecha_nacimiento, tipo_sangre,
                    datos_adicionales, fecha_creacion, foto
            """, (
                persona.nombre,
                persona.apellido_paterno,
                persona.apellido_materno,
                persona.curp,
                persona.rfc,
                persona.fecha_nacimiento,
                persona.tipo_sangre,
                datos_json
            ))
            row = cur.fetchone()
            conn.commit()
            return row
    except Exception as e:
        logger.error(f"Error creando persona: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/personas/{id_persona}", response_model=PersonaOut)
def get_persona(id_persona: int):
    """Obtiene detalles de una Persona."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    id_persona, nombre, apellido_paterno, apellido_materno,
                    curp, rfc, fecha_nacimiento, tipo_sangre,
                    datos_adicionales, fecha_creacion, foto
                FROM entidades.personas 
                WHERE id_persona = %s
            """, (id_persona,))
            row = cur.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="Persona no encontrada")
            return row
    finally:
        conn.close()

# ==================================================================
# VINCULOS (CASOS <-> PERSONAS)
# ==================================================================

@router.post("/vinculos", response_model=VinculoOut)
def vincular_persona_caso(vinculo: VinculoObjetivoCasoIn):
    """Vincula una Persona existente a un Caso."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Verificar si ya existe el vínculo
            cur.execute("""
                SELECT id_vinculo FROM casos.vinculos_objetivo
                WHERE idcaso = %s AND id_persona = %s
            """, (vinculo.id_caso, vinculo.id_persona))
            
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="La persona ya está vinculada a este caso")
            
            # Insertar vínculo
            cur.execute("""
                INSERT INTO casos.vinculos_objetivo
                (idcaso, id_persona, agregado_por)
                VALUES (%s, %s, %s)
                RETURNING id_vinculo, idcaso AS id_caso, id_persona, agregado_por, fecha_agregado
            """, (vinculo.id_caso, vinculo.id_persona, vinculo.agregado_por))
            
            row = cur.fetchone()
            conn.commit()
            return row
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error vinculando persona a caso: {e}")
        # Manejo de error de FK si el caso o la persona no existen
        if 'foreign key constraint' in str(e).lower():
             raise HTTPException(status_code=404, detail="Caso o Persona no encontrados")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/casos/{id_caso}/personas", response_model=List[PersonaOut])
def list_personas_por_caso(id_caso: int):
    """Lista todas las personas vinculadas a un caso específico."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.* 
                FROM entidades.personas p
                JOIN casos.vinculos_objetivo v ON p.id_persona = v.id_persona
                WHERE v.idcaso = %s
                ORDER BY v.fecha_agregado DESC
            """, (id_caso,))
            
            results = []
            for row in cur.fetchall():
                results.append(row)
            return results
    finally:
        conn.close()

# ==================================================================
# VISTA TABLERO: Personas + Identidades (optimizada para frontend)
# ==================================================================

class IdentidadAsociada(BaseModel):
    id_identidad: int
    plataforma: str
    usuario: str
    estado_analisis: str
    ruta_grafo: Optional[str] = None
    ultimo_analisis: Optional[Any] = None


class PersonaCardOut(BaseModel):
    id_caso: int
    id_persona: int
    nombre: str
    apellido_paterno: str
    apellido_materno: Optional[str] = None
    foto: Optional[str] = None
    curp: Optional[str] = None
    rfc: Optional[str] = None
    fecha_agregado: Any
    identidades_asociadas: List[IdentidadAsociada] = []


@router.get("/casos/{id_caso}/tablero", response_model=List[PersonaCardOut])
def get_tablero_personas(id_caso: int):
    """Devuelve la vista `casos.vista_tablero_personas` para el caso solicitado.

    La vista ya retorna la estructura JSON con `identidades_asociadas`.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    idcaso AS id_caso,
                    id_persona,
                    nombre,
                    apellido_paterno,
                    apellido_materno,
                    foto,
                    curp,
                    rfc,
                    fecha_agregado,
                    identidades_asociadas
                FROM casos.vista_tablero_personas 
                WHERE idcaso = %s
            """, (id_caso,))
            rows = cur.fetchall()

            results = []
            for row in rows:
                # `identidades_asociadas` viene como JSONB desde la vista;
                # RealDictCursor ya lo convierte a estructuras Python.
                results.append(row)

            return results
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
                ORDER BY id_identidad DESC
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
                (id_persona, plataforma, usuario_o_url)
                VALUES (%s, %s, %s)
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

# ==================================================================
# GESTIÓN DE IDENTIDADES EN CASOS (SELECCIÓN)
# ==================================================================

@router.post("/casos/{id_caso}/identidades/seleccionar", response_model=List[AnalisisIdentidadOut])
def seleccionar_identidades_caso(id_caso: int, seleccion: SeleccionIdentidadIn):
    """
    Selecciona qué identidades de una persona serán analizadas en este caso.
    Crea registros en casos.analisis_identidad.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            results = []
            for id_identidad in seleccion.identidades_ids:
                # Upsert: Si ya existe, reactivamos el estado a pendiente
                cur.execute("""
                    INSERT INTO casos.analisis_identidad (idcaso, id_identidad, estado)
                    VALUES (%s, %s, 'pendiente')
                    ON CONFLICT (idcaso, id_identidad) DO UPDATE 
                    SET estado = 'pendiente'
                    RETURNING id_analisis, idcaso AS id_caso, id_identidad, estado, ruta_grafo_ftp, fecha_analisis
                """, (id_caso, id_identidad))
                results.append(cur.fetchone())
            conn.commit()
            return results
    except Exception as e:
        logger.error(f"Error seleccionando identidades: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/casos/{id_caso}/identidades", response_model=List[AnalisisIdentidadOut])
def list_identidades_caso(id_caso: int):
    """Lista las identidades seleccionadas para un caso con su estado de análisis."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    id_analisis, idcaso AS id_caso, id_identidad, 
                    estado, ruta_grafo_ftp, fecha_analisis
                FROM casos.analisis_identidad
                WHERE idcaso = %s
            """, (id_caso,))
            return cur.fetchall()
    finally:
        conn.close()
