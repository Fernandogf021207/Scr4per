"""
Utilidades para generación de rutas jerárquicas en el sistema de archivos FTP.

Este módulo implementa la estructura organizacional definida en el plan de integración:
    /storage/{organizacion}/{area}/{departamento}/{usuario}/{caso}/{persona}/{plataforma}/
"""
import re
from typing import Optional
from pathlib import PurePosixPath


def sanitize_path_component(text: str, max_length: int = 50) -> str:
    """
    Sanitiza un componente de ruta para uso seguro en sistemas de archivos.
    
    Args:
        text: Texto a sanitizar (nombre de organización, área, etc.)
        max_length: Longitud máxima del componente
    
    Returns:
        Texto sanitizado (alfanumérico, guiones, guiones bajos)
    
    Raises:
        ValueError: Si el texto resultante está vacío
    """
    if not text:
        raise ValueError("Path component cannot be empty")
    
    # Remover acentos y caracteres especiales
    # Convertir a minúsculas para consistencia
    clean = text.lower().strip()
    
    # Reemplazar espacios por guiones
    clean = clean.replace(' ', '-')
    
    # Mantener solo alfanuméricos, guiones y guiones bajos
    clean = re.sub(r'[^a-z0-9\-_]', '', clean)
    
    # Limitar longitud
    clean = clean[:max_length]
    
    # Remover guiones/underscores duplicados o al inicio/fin
    clean = re.sub(r'[-_]+', '-', clean).strip('-_')
    
    if not clean:
        raise ValueError(f"Sanitized path component is empty for input: {text}")
    
    return clean


def build_hierarchical_ftp_path(
    organizacion: str,
    usuario_id: int,
    caso_id: int,
    persona_id: int,
    plataforma: str,
    area: Optional[str] = None,
    departamento: Optional[str] = None,
    category: str = "grafos"
) -> str:
    """
    Construye una ruta jerárquica completa para el almacenamiento FTP.
    
    Estructura generada:
        /storage/{org}/{area}/{depto}/{user_id}/{caso_id}/{persona_id}/{plataforma}/{category}/
    
    Args:
        organizacion: Nombre de la organización
        usuario_id: ID del usuario que ejecuta el análisis
        caso_id: ID del caso activo
        persona_id: ID de la persona objetivo
        plataforma: Plataforma de red social ('x', 'instagram', 'facebook')
        area: Nombre del área (opcional)
        departamento: Nombre del departamento (opcional)
        category: Categoría de archivo ('grafos', 'evidencia', 'reportes')
    
    Returns:
        Ruta relativa desde la raíz FTP configurada (ej: storage/acme-corp/inteligencia/...)
    
    Example:
        >>> build_hierarchical_ftp_path(
        ...     organizacion="ACME Corp",
        ...     usuario_id=123,
        ...     caso_id=456,
        ...     persona_id=789,
        ...     plataforma="x",
        ...     area="Inteligencia",
        ...     departamento="Análisis Digital",
        ...     category="grafos"
        ... )
        'storage/acme-corp/inteligencia/analisis-digital/123/456/789/x/grafos'
    """
    # Validar plataforma
    valid_platforms = ['x', 'instagram', 'facebook']
    if plataforma not in valid_platforms:
        raise ValueError(f"Invalid platform: {plataforma}. Must be one of {valid_platforms}")
    
    # Validar categoría
    valid_categories = ['grafos', 'evidencia', 'reportes', 'media', 'screenshots', 'images']
    if category not in valid_categories:
        raise ValueError(f"Invalid category: {category}. Must be one of {valid_categories}")
    
    # Obtener base path desde variable de entorno o usar default
    import os
    base_path = os.getenv('FTP_BASE_PATH', 'redes_sociales')

    # Construir componentes de la ruta
    parts = [base_path]
    
    # Nivel organizacional
    parts.append(sanitize_path_component(organizacion))
    
    # Área (opcional)
    if area:
        parts.append(sanitize_path_component(area))
    
    # Departamento (opcional)
    if departamento:
        parts.append(sanitize_path_component(departamento))
    
    # Nivel de usuario y caso (IDs numéricos, no sanitizar)
    parts.append(str(usuario_id))
    parts.append(str(caso_id))
    parts.append(str(persona_id))
    
    # Plataforma y categoría
    parts.append(plataforma)  # Ya validada
    parts.append(category)    # Ya validada
    
    # Generar ruta usando PurePosixPath para consistencia (siempre forward slashes)
    path = PurePosixPath(*parts)
    
    return str(path)


def build_graph_file_path(
    organizacion: str,
    usuario_id: int,
    caso_id: int,
    persona_id: int,
    plataforma: str,
    username: str,
    area: Optional[str] = None,
    departamento: Optional[str] = None
) -> str:
    """
    Construye la ruta completa del archivo JSON de grafo.
    
    Args:
        organizacion: Nombre de la organización
        usuario_id: ID del usuario
        caso_id: ID del caso
        persona_id: ID de la persona objetivo
        plataforma: Plataforma de red social
        username: Username del perfil analizado
        area: Nombre del área (opcional)
        departamento: Nombre del departamento (opcional)
    
    Returns:
        Ruta completa incluyendo el nombre del archivo
    
    Example:
        'storage/acme-corp/inteligencia/123/456/789/x/grafos/grafo_x_jvgador9.json'
    """
    dir_path = build_hierarchical_ftp_path(
        organizacion=organizacion,
        usuario_id=usuario_id,
        caso_id=caso_id,
        persona_id=persona_id,
        plataforma=plataforma,
        area=area,
        departamento=departamento,
        category='grafos'
    )
    
    # Sanitizar username para nombre de archivo
    safe_username = sanitize_path_component(username, max_length=60)
    filename = f"grafo_{plataforma}_{safe_username}.json"
    
    return str(PurePosixPath(dir_path) / filename)


def build_evidence_path(
    organizacion: str,
    usuario_id: int,
    caso_id: int,
    persona_id: int,
    plataforma: str,
    area: Optional[str] = None,
    departamento: Optional[str] = None
) -> str:
    """
    Construye la ruta del directorio de evidencia (screenshots, media).
    
    Returns:
        Ruta del directorio de evidencia
    """
    return build_hierarchical_ftp_path(
        organizacion=organizacion,
        usuario_id=usuario_id,
        caso_id=caso_id,
        persona_id=persona_id,
        plataforma=plataforma,
        area=area,
        departamento=departamento,
        category='evidencia'
    )


def build_image_file_path(
    organizacion: str,
    usuario_id: int,
    caso_id: int,
    persona_id: int,
    plataforma: str,
    username: str,
    filename: str,
    area: Optional[str] = None,
    departamento: Optional[str] = None
) -> str:
    """
    Construye la ruta completa para una imagen en el FTP.
    
    Args:
        organizacion: Nombre de la organización
        usuario_id: ID del usuario
        caso_id: ID del caso
        persona_id: ID de la persona objetivo
        plataforma: Plataforma de red social
        username: Username del perfil (dueño de la imagen)
        filename: Nombre del archivo (ej: 'profile.jpg')
        area: Nombre del área (opcional)
        departamento: Nombre del departamento (opcional)
    
    Returns:
        Ruta completa incluyendo el nombre del archivo
    """
    dir_path = build_hierarchical_ftp_path(
        organizacion=organizacion,
        usuario_id=usuario_id,
        caso_id=caso_id,
        persona_id=persona_id,
        plataforma=plataforma,
        area=area,
        departamento=departamento,
        category='images'
    )
    
    return str(PurePosixPath(dir_path) / filename)


def parse_user_context_to_path(context: dict) -> dict:
    """
    Convierte un UserContext (dict) a parámetros para las funciones de ruta.
    
    Args:
        context: Dict con campos de UserContext (id_usuario, id_caso, etc.)
    
    Returns:
        Dict con parámetros formateados para build_hierarchical_ftp_path
    
    Example:
        >>> ctx = {
        ...     "id_usuario": 123,
        ...     "id_caso": 456,
        ...     "id_organizacion": 1,
        ...     "nombre_organizacion": "ACME Corp",
        ...     "nombre_area": "Inteligencia",
        ...     "nombre_departamento": "Digital"
        ... }
        >>> parse_user_context_to_path(ctx)
        {
            'organizacion': 'ACME Corp',
            'usuario_id': 123,
            'caso_id': 456,
            'area': 'Inteligencia',
            'departamento': 'Digital'
        }
    """
    return {
        'organizacion': context['nombre_organizacion'],
        'usuario_id': context['id_usuario'],
        'caso_id': context['id_caso'],
        'area': context.get('nombre_area'),
        'departamento': context.get('nombre_departamento')
    }
