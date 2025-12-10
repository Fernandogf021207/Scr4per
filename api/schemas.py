from typing import Optional, Literal, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator, model_validator

class ProfileIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    username: str
    full_name: Optional[str] = None
    profile_url: Optional[str] = None
    photo_url: Optional[str] = None

class Profile(ProfileIn):
    id: int

class RelationshipIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    owner_username: str
    related_username: str
    rel_type: str
    updated_at: Optional[datetime] = None

    @validator('rel_type')
    def _normalize_rel_type(cls, v: str) -> str:
        if not v:
            raise ValueError('rel_type requerido')
        raw = v.strip().lower()
        # Normalización español → inglés
        mapping = {
            'seguidor': 'follower',
            'seguidores': 'follower',
            'seguido': 'following',
            'seguidos': 'following',
            'amigo': 'friend',
            'amigos': 'friend',
            'comentado': 'commented',
            'comentó': 'commented',
            'comentados': 'commented',
            'reaccionado': 'reacted',
            'reaccionó': 'reacted',
            'reacciones': 'reacted',
        }
        canon = mapping.get(raw, raw)
        allowed = {'follower', 'following', 'followed', 'friend', 'commented', 'reacted'}
        if canon not in allowed:
            raise ValueError('rel_type inválido')
        return canon

class PostIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    owner_username: str
    post_url: str

class CommentIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    post_url: str
    commenter_username: str

class ReactionIn(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    post_url: str
    reactor_username: str
    reaction_type: Optional[str] = None

class ScrapeRequest(BaseModel):
    url: str
    platform: Literal['x', 'instagram', 'facebook']
    max_photos: Optional[int] = 5

class GraphSessionIn(BaseModel):
    platform: Literal['x','instagram','facebook']
    owner_username: str
    elements: Dict[str, Any]
    style: Optional[Dict[str,Any]] = None
    layout: Optional[Dict[str,Any]] = None

class ExportPerfil(BaseModel):
    """Un perfil individual con sus relacionados."""
    perfil_objetivo: Dict[str, Any] = Field(
        ...,
        description="Información del perfil objetivo"
    )
    perfiles_relacionados: List[Dict[str, Any]] = Field(
        ...,
        description="Lista de perfiles relacionados"
    )

class ExportInput(BaseModel):
    """
    Schema para exportar datos a Excel.
    El frontend envía un array de perfiles bajo el campo 'perfiles'.
    """
    perfiles: List[ExportPerfil] = Field(
        ...,
        description="Lista de perfiles con sus relacionados"
    )


# ==========================
# Multi-scrape (schema v2)
# ==========================

USERNAME_REGEX = r'^[A-Za-z0-9._-]{2,60}$'


class MultiScrapeRoot(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    username: str  # 2..60, alfanumérico + ._-
    max_photos: int = Field(5, ge=0, le=50)

    @validator('username')
    def _username_valid(cls, v: str):
        import re
        if not re.match(USERNAME_REGEX, v or ''):
            raise ValueError('invalid username (2..60, A-Za-z0-9._-)')
        return v


class MultiScrapeRequest(BaseModel):
    roots: List[MultiScrapeRoot] = Field(..., description="1..5 roots")
    headless: bool = True
    max_concurrency: Optional[int] = Field(None, ge=1, le=3)
    persist: bool = True
    strict_sessions: bool = False

    @validator('roots')
    def _check_roots(cls, v: List[MultiScrapeRoot]):
        if not v:
            raise ValueError('roots must contain at least 1 item')
        if len(v) > 5:
            raise ValueError('Max 5 roots')
        return v

    @model_validator(mode='after')
    def _default_max_concurrency(self):
        if self.max_concurrency is None:
            roots = self.roots or []
            self.max_concurrency = 1 if len(roots) <= 1 else 3
        return self


class MultiScrapeProfileItem(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    username: str
    full_name: Optional[str] = None
    profile_url: Optional[str] = None
    photo_url: Optional[str] = None
    sources: List[str] = []

    @validator('username')
    def _username_valid(cls, v: str):
        import re
        if not re.match(USERNAME_REGEX, v or ''):
            raise ValueError('invalid username (2..60, A-Za-z0-9._-)')
        return v


class MultiScrapeRelationItem(BaseModel):
    platform: Literal['x', 'instagram', 'facebook']
    source: str
    target: str
    type: Literal['follower', 'following', 'friend', 'commented', 'reacted']

    @validator('source', 'target')
    def _username_valid(cls, v: str):
        import re
        if not re.match(USERNAME_REGEX, v or ''):
            raise ValueError('invalid username (2..60, A-Za-z0-9._-)')
        return v


class MultiScrapeWarning(BaseModel):
    code: str
    message: str


class MultiScrapeResponse(BaseModel):
    schema_version: int = 2
    root_profiles: List[str]
    profiles: List[MultiScrapeProfileItem]
    relations: List[MultiScrapeRelationItem]
    warnings: List[MultiScrapeWarning] = []
    meta: Dict[str, Any]


# ==========================
# Integration Schemas (Casos & Personas)
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


class PersonaObjetivoIn(BaseModel):
    """Datos para crear/actualizar una Persona Objetivo."""
    nombre_completo: str = Field(..., min_length=2, max_length=200)
    curp: Optional[str] = Field(None, max_length=20, pattern=r'^[A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d$')
    rfc: Optional[str] = Field(None, max_length=15)
    fecha_nacimiento: Optional[str] = Field(None, description="Formato: YYYY-MM-DD")
    datos_adicionales: Optional[Dict[str, Any]] = Field(None, description="Alias, direcciones, notas")


class PersonaObjetivoOut(PersonaObjetivoIn):
    """Respuesta con datos de Persona Objetivo."""
    id_persona: int
    creado_por: Optional[int]
    fecha_creacion: datetime


class IdentidadDigitalIn(BaseModel):
    """Datos para agregar una Identidad Digital a una Persona."""
    id_persona: int = Field(..., description="ID de la persona objetivo")
    plataforma: Literal['x', 'instagram', 'facebook']
    usuario_o_url: str = Field(..., min_length=2, max_length=500, description="Username o URL completa")


class IdentidadDigitalOut(IdentidadDigitalIn):
    """Respuesta con datos de Identidad Digital."""
    id_identidad: int
    estado: Literal['pendiente', 'procesando', 'analizado', 'error']
    mensaje_error: Optional[str] = None
    id_perfil_scraped: Optional[int] = None
    ruta_grafo_ftp: Optional[str] = None
    ruta_evidencia_ftp: Optional[str] = None
    ultimo_analisis: Optional[datetime] = None
    intentos_fallidos: int = 0
    agregado_por: Optional[int] = None
    fecha_creacion: Optional[datetime] = None


class AnalysisRequest(BaseModel):
    """
    Solicitud para iniciar el análisis de una Identidad Digital.
    Incluye el contexto del usuario para generación de rutas jerárquicas.
    """
    id_identidad: int = Field(..., description="ID de la identidad digital a analizar")
    context: UserContext
    max_photos: int = Field(10, ge=1, le=50, description="Número máximo de fotos a analizar")
    headless: bool = Field(True, description="Ejecutar navegador en modo headless")
    max_depth: int = Field(1, ge=1, le=3, description="Profundidad de análisis (1=solo perfil, 2=amigos)")
    
    # Parámetros opcionales del scraping
    max_photos: int = Field(5, ge=0, le=50)
    headless: bool = True
    max_depth: int = Field(2, ge=1, le=3, description="Niveles de relaciones a explorar")


class AnalysisStatusResponse(BaseModel):
    """Respuesta de estado del análisis."""
    id_identidad: int
    estado: Literal['pendiente', 'procesando', 'analizado', 'error']
    mensaje_error: Optional[str]
    progreso: Optional[Dict[str, Any]] = Field(None, description="Información de progreso (perfiles, relaciones)")
    ultimo_analisis: Optional[datetime]
    ruta_grafo_ftp: Optional[str]


# BatchAnalysisRequest and BatchAnalysisResponse moved to schemas_batch.py


class VinculoObjetivoCasoIn(BaseModel):
    """Vincula una Persona Objetivo con un Caso."""
    id_caso: int
    id_persona: int
    rol_en_caso: Optional[str] = Field(None, max_length=50, description="Ej: sospechoso, testigo, víctima")
    notas: Optional[str] = Field(None, max_length=2000)


class VinculoObjetivoCasoOut(VinculoObjetivoCasoIn):
    """Respuesta de vínculo Objetivo-Caso."""
    id_vinculo: int
    agregado_por: Optional[int]
    fecha_agregado: datetime