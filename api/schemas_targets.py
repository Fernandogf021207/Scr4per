from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date, datetime

# --- ESQUEMAS PARA IDENTIDADES DIGITALES ---

class IdentidadBase(BaseModel):
    plataforma: str = Field(..., example="x", description="x, instagram, facebook")
    usuario_o_url: str = Field(..., example="elonmusk", description="Usuario o URL completa")

class IdentidadCreate(IdentidadBase):
    pass

class IdentidadResponse(IdentidadBase):
    id_identidad: int
    id_persona: int
    # No incluimos estado aquí porque eso depende del caso, 
    # pero para la edición básica de la persona no es estrictamente necesario.

    class Config:
        from_attributes = True

# --- ESQUEMAS PARA PERSONAS ---

class PersonaBase(BaseModel):
    nombre: str
    apellido_paterno: str
    apellido_materno: Optional[str] = None
    curp: Optional[str] = None
    rfc: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    tipo_sangre: Optional[str] = None
    foto: Optional[str] = None # Ruta FTP si ya existe, o null
    datos_adicionales: Optional[Dict[str, Any]] = {}

class PersonaCreate(PersonaBase):
    """
    Payload para crear una nueva persona y vincularla a un caso.
    Permite agregar redes sociales iniciales.
    """
    # Contexto necesario para el vínculo
    id_caso: int
    id_usuario: int # Quién lo agrega (Auditor)
    
    # Redes iniciales (opcional)
    identidades: List[IdentidadCreate] = []

class PersonaUpdate(BaseModel):
    """
    Payload para editar datos biográficos y agregar identidades.
    Campos opcionales; si no se envían, no se cambian.
    """
    nombre: Optional[str] = None
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    curp: Optional[str] = None
    rfc: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    tipo_sangre: Optional[str] = None
    datos_adicionales: Optional[Dict[str, Any]] = None
    foto: Optional[str] = None
    identidades: Optional[List[IdentidadCreate]] = None

class PersonaResponse(PersonaBase):
    id_persona: int
    fecha_creacion: Any
    
    # Incluimos las identidades para pintar la tarjeta completa
    identidades: List[IdentidadResponse] = []

    class Config:
        from_attributes = True

class BatchDeleteRequest(BaseModel):
    personas_ids: List[int]
    id_caso: Optional[int] = None

class BatchDeleteResponse(BaseModel):
    deleted_ids: List[int]
    failed_ids: List[Dict[str, Any]] # {id: 1, reason: "..."}
