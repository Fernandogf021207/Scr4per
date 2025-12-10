from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

# ==========================
# Modelos de Entrada (Schemas Batch)
# ==========================

class UserContext(BaseModel):
    """
    Contexto jerárquico del usuario para almacenamiento y auditoría.
    Se usa para generar rutas FTP organizadas por estructura organizacional.
    """
    id_usuario: int = Field(..., description="ID del usuario en core.users")
    id_caso: int = Field(..., description="ID del caso activo")
    id_organizacion: int = Field(..., description="ID de la organización")
    id_area: Optional[int] = Field(None, description="ID del área dentro de la organización")
    id_departamento: Optional[int] = Field(None, description="ID del departamento dentro del área")
    
    # Nombres para generar carpetas legibles en FTP
    nombre_organizacion: str = Field(..., max_length=100)
    nombre_area: Optional[str] = Field(None, max_length=100)
    nombre_departamento: Optional[str] = Field(None, max_length=100)

class BatchAnalysisRequest(BaseModel):
    """
    Solicitud para iniciar análisis en lote de múltiples personas.
    El sistema buscará todas las identidades digitales asociadas a estas personas.
    """
    personas_ids: List[int] = Field(..., min_items=1, description="Lista de IDs de personas a analizar")
    context: UserContext
    
    # Parámetros opcionales del scraping
    max_photos: int = Field(10, ge=0, le=50)
    headless: bool = True
    max_depth: int = Field(2, ge=1, le=3)

class BatchAnalysisResponse(BaseModel):
    """Respuesta inmediata al iniciar un análisis en lote."""
    mensaje: str
    total_identidades_encontradas: int
    identidades_iniciadas: List[int]
    identidades_omitidas: List[int]
    detalle: str

class PersonaIn(BaseModel):
    nombre: str
    apellido_paterno: str
    apellido_materno: Optional[str] = None
    curp: Optional[str] = None
    rfc: Optional[str] = None
    fecha_nacimiento: Optional[str] = None
    tipo_sangre: Optional[str] = None
    datos_adicionales: Optional[Dict[str, Any]] = None

class IdentidadDigitalIn(BaseModel):
    id_persona: int
    plataforma: Literal['x', 'instagram', 'facebook']
    usuario_o_url: str

class SeleccionIdentidadIn(BaseModel):
    identidades_ids: List[int]

class AnalisisIdentidadOut(BaseModel):
    id_analisis: int
    id_caso: int
    id_identidad: int
    estado: str
    ruta_grafo_ftp: Optional[str] = None
    fecha_analisis: Optional[datetime] = None

class VinculoObjetivoCasoIn(BaseModel):
    id_caso: int
    id_persona: int
    agregado_por: int
