"""
Router para gestión de sesiones de scraping (BYOS - Bring Your Own Session).

Los analistas pueden vincular, consultar y desvincular sus propias cuentas
de redes sociales para usarlas en el scraper.
"""
from fastapi import APIRouter, HTTPException, Header, Body, Request, status
from typing import Optional, List, Dict, Any
import logging
import json
from datetime import datetime

from ..db import get_conn
from ..schemas_sessions import (
    SessionCreate,
    SessionStorageStateCreate,
    SessionStatusResponse,
    SessionListResponse,
    SessionDeleteResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users/me/sessions", tags=["sessions"])


def normalize_cookie_for_playwright(cookie: dict) -> dict:
    """
    Normaliza cookies de extensiones (EditThisCookie) al formato Playwright.
    
    Transformaciones:
    - Renombra: expirationDate -> expires
    - Elimina: hostOnly, session, storeId, id (campos de extensiones)
    - Estandariza sameSite: "no_restriction"/"unspecified" -> "None", etc.
    
    Args:
        cookie: Cookie en formato de extensión (EditThisCookie)
    
    Returns:
        Cookie normalizada en formato Playwright
    """
    # 1. Copiar para no mutar el original
    c = cookie.copy()
    
    # 2. Renombrar expirationDate -> expires
    if "expirationDate" in c:
        c["expires"] = c.pop("expirationDate")
        
    # 3. Eliminar campos basura de extensiones
    for field in ["hostOnly", "session", "storeId", "id"]:
        c.pop(field, None)
        
    # 4. Normalizar sameSite (Crítico para Playwright)
    if "sameSite" in c:
        val = str(c["sameSite"]).lower()
        if val in ["no_restriction", "unspecified"]:
            c["sameSite"] = "None"
        elif val == "lax":
            c["sameSite"] = "Lax"
        elif val == "strict":
            c["sameSite"] = "Strict"
        else:
            # Si no es estándar, mejor quitarlo y dejar default del navegador
            c.pop("sameSite", None)
            
    # 5. Asegurar tipos básicos (seguridad extra)
    if "expires" in c:
        try:
            c["expires"] = float(c["expires"])
        except (ValueError, TypeError):
            c.pop("expires", None)  # Si no es numérico, quitarlo

    return c


def get_user_id_from_header(x_user_id: Optional[str] = Header(None)) -> int:
    """
    Extrae el ID de usuario del header X-User-Id.
    
    Para MVP: Asume que el frontend envía X-User-Id.
    En producción: Implementar autenticación JWT y extraer del token.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header X-User-Id requerido"
        )
    
    try:
        return int(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id debe ser un número entero"
        )


@router.put("/{platform}", response_model=SessionStatusResponse, status_code=status.HTTP_200_OK)
async def create_or_update_session(
    platform: str,
    request: Request,
    cookies_raw: List[Dict[str, Any]] = Body(...),
    x_user_id: Optional[str] = Header(None)
):
    """
    Crea o actualiza la sesión de scraping para una plataforma.
    
    ✨ **Copy-Paste Friendly:** Acepta directamente el JSON exportado por EditThisCookie.
    Simplemente pega la lista de cookies tal cual. El endpoint normaliza automáticamente
    el formato (expirationDate→expires, sameSite, etc.)
    
    - Si ya existe una sesión para este usuario/plataforma: actualiza cookies y resetea estado
    - Si no existe: crea nueva sesión
    
    Args:
        platform: Plataforma (facebook, instagram, x) - En la URL
        request: Request object para inferir User-Agent
        cookies_raw: Lista de cookies en cualquier formato (EditThisCookie, Playwright, etc.)
        x_user_id: ID del usuario (del header)
    
    Returns:
        Estado actual de la sesión (sin cookies)
    
    Raises:
        400: Lista de cookies vacía o inválida
        401: Usuario no autenticado
    
    Example Body (Paste directo de EditThisCookie):
        [
          {
            "domain": ".facebook.com",
            "name": "c_user",
            "value": "123456",
            "expirationDate": 1797687796.607449,
            "hostOnly": false,
            "sameSite": "no_restriction"
          }
        ]
    """
    id_usuario = get_user_id_from_header(x_user_id)
    
    # Validar plataforma
    if platform not in ['facebook', 'instagram', 'x']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plataforma inválida: {platform}. Debe ser: facebook, instagram, x"
        )
    
    # Validar cookies
    if not cookies_raw or not isinstance(cookies_raw, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar una lista de cookies"
        )
    
    conn = get_conn()
    
    try:
        with conn.cursor() as cur:
            # Normalizar cookies entrantes (EditThisCookie -> Playwright)
            clean_cookies = [normalize_cookie_for_playwright(c) for c in cookies_raw]
            
            # Validación post-normalización
            if not clean_cookies:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La lista de cookies está vacía o todas las cookies son inválidas"
                )
            
            # Construir storage_state en formato Playwright
            storage_state = {
                "cookies": clean_cookies,
                "origins": []
            }
            
            # Inferir User-Agent del navegador que hace la petición
            user_agent = request.headers.get(
                "user-agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            
            # UPSERT: Buscar sesión existente
            cur.execute("""
                SELECT id_sesion FROM entidades.sesiones_scraping
                WHERE id_usuario = %s AND plataforma = %s
            """, (id_usuario, platform))
            
            existing = cur.fetchone()
            
            if existing:
                # Actualizar sesión existente
                cur.execute("""
                    UPDATE entidades.sesiones_scraping
                    SET 
                        cookies = %s,
                        user_agent = %s,
                        estado = 'activa',
                        error_count = 0,
                        ultima_actividad = NOW()
                    WHERE id_usuario = %s AND plataforma = %s
                    RETURNING estado, ultima_actividad, error_count
                """, (
                    json.dumps(storage_state),
                    user_agent,
                    id_usuario,
                    platform
                ))
                
                logger.info(f"[SUCCESS] Sesión actualizada: usuario={id_usuario}, plataforma={platform}, cookies={len(clean_cookies)}")
            else:
                # Crear nueva sesión (proxy_url = NULL por defecto)
                cur.execute("""
                    INSERT INTO entidades.sesiones_scraping
                    (id_usuario, plataforma, cookies, user_agent, proxy_url, estado, error_count)
                    VALUES (%s, %s, %s, %s, NULL, 'activa', 0)
                    RETURNING estado, ultima_actividad, error_count
                """, (
                    id_usuario,
                    platform,
                    json.dumps(storage_state),
                    user_agent
                ))
                
                logger.info(f"[SUCCESS] Sesión creada: usuario={id_usuario}, plataforma={platform}, cookies={len(clean_cookies)}")
            
            result = cur.fetchone()
            conn.commit()
            
            return SessionStatusResponse(
                plataforma=platform,
                estado=result['estado'],
                ultima_actividad=result['ultima_actividad'],
                error_count=result.get('error_count', 0)
            )
            
    except Exception as e:
        conn.rollback()
        logger.error(f"[ERROR] Error al crear/actualizar sesión: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar sesión: {str(e)}"
        )
    finally:
        conn.close()


@router.put("/{platform}/storage-state", response_model=SessionStatusResponse)
def create_or_update_session_storage_state(
    platform: str,
    session: SessionStorageStateCreate,
    x_user_id: Optional[str] = Header(None)
):
    """
    Alternativa: Recibe directamente el storage_state completo de Playwright.
    
    Útil si el frontend ya tiene el formato completo exportado.
    
    Args:
        platform: Plataforma (facebook, instagram, x)
        session: Storage state completo + metadatos
        x_user_id: ID del usuario (del header)
    """
    id_usuario = get_user_id_from_header(x_user_id)
    
    if platform != session.plataforma:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plataforma en URL ({platform}) no coincide con body ({session.plataforma})"
        )
    
    conn = get_conn()
    
    try:
        with conn.cursor() as cur:
            # UPSERT
            cur.execute("""
                SELECT id_sesion FROM entidades.sesiones_scraping
                WHERE id_usuario = %s AND plataforma = %s
            """, (id_usuario, session.plataforma))
            
            existing = cur.fetchone()
            
            if existing:
                cur.execute("""
                    UPDATE entidades.sesiones_scraping
                    SET 
                        cookies = %s,
                        user_agent = %s,
                        proxy_url = %s,
                        estado = 'activa',
                        error_count = 0,
                        ultima_actividad = NOW()
                    WHERE id_usuario = %s AND plataforma = %s
                    RETURNING estado, ultima_actividad, error_count
                """, (
                    json.dumps(session.storage_state),
                    session.user_agent,
                    session.proxy_url,
                    id_usuario,
                    session.plataforma
                ))
            else:
                cur.execute("""
                    INSERT INTO entidades.sesiones_scraping
                    (id_usuario, plataforma, cookies, user_agent, proxy_url, estado, error_count)
                    VALUES (%s, %s, %s, %s, %s, 'activa', 0)
                    RETURNING estado, ultima_actividad, error_count
                """, (
                    id_usuario,
                    session.plataforma,
                    json.dumps(session.storage_state),
                    session.user_agent,
                    session.proxy_url
                ))
            
            result = cur.fetchone()
            conn.commit()
            
            return SessionStatusResponse(
                plataforma=session.plataforma,
                estado=result['estado'],
                ultima_actividad=result['ultima_actividad'],
                error_count=result.get('error_count', 0)
            )
            
    except Exception as e:
        conn.rollback()
        logger.error(f"[ERROR] Error al crear/actualizar sesión (storage_state): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar sesión: {str(e)}"
        )
    finally:
        conn.close()


@router.get("", response_model=SessionListResponse)
def list_user_sessions(x_user_id: Optional[str] = Header(None)):
    """
    Lista todas las sesiones del usuario con su estado actual.
    
    Retorna solo el estado y metadatos, NUNCA las cookies por seguridad.
    
    Args:
        x_user_id: ID del usuario (del header)
    
    Returns:
        Lista de sesiones con estado (activa, caducada, bloqueada)
    """
    id_usuario = get_user_id_from_header(x_user_id)
    
    conn = get_conn()
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT plataforma, estado, ultima_actividad, error_count
                FROM entidades.sesiones_scraping
                WHERE id_usuario = %s
                ORDER BY plataforma
            """, (id_usuario,))
            
            rows = cur.fetchall()
            
            sesiones = [
                SessionStatusResponse(
                    plataforma=row['plataforma'],
                    estado=row['estado'],
                    ultima_actividad=row['ultima_actividad'],
                    error_count=row.get('error_count', 0)
                )
                for row in rows
            ]
            
            return SessionListResponse(sesiones=sesiones)
            
    except Exception as e:
        logger.error(f"[ERROR] Error al listar sesiones: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener sesiones: {str(e)}"
        )
    finally:
        conn.close()


@router.delete("/{platform}", response_model=SessionDeleteResponse)
def delete_session(
    platform: str,
    x_user_id: Optional[str] = Header(None)
):
    """
    Elimina (desvincula) la sesión de una plataforma.
    
    Borra físicamente el registro de la base de datos.
    El analista deberá volver a vincular su cuenta si quiere usar esa plataforma.
    
    Args:
        platform: Plataforma a desvincular (facebook, instagram, x)
        x_user_id: ID del usuario (del header)
    
    Returns:
        Confirmación de eliminación
    
    Raises:
        404: Sesión no encontrada
    """
    id_usuario = get_user_id_from_header(x_user_id)
    
    # Validar plataforma
    if platform not in ['facebook', 'instagram', 'x']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plataforma inválida: {platform}. Debe ser: facebook, instagram, x"
        )
    
    conn = get_conn()
    
    try:
        with conn.cursor() as cur:
            # Verificar que existe
            cur.execute("""
                SELECT id_sesion FROM entidades.sesiones_scraping
                WHERE id_usuario = %s AND plataforma = %s
            """, (id_usuario, platform))
            
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No existe sesión de {platform} para este usuario"
                )
            
            # Eliminar
            cur.execute("""
                DELETE FROM entidades.sesiones_scraping
                WHERE id_usuario = %s AND plataforma = %s
            """, (id_usuario, platform))
            
            conn.commit()
            
            logger.info(f"[SUCCESS] Sesión eliminada: usuario={id_usuario}, plataforma={platform}")
            
            return SessionDeleteResponse(
                mensaje=f"Sesión de {platform} eliminada exitosamente",
                plataforma=platform
            )
            
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"[ERROR] Error al eliminar sesión: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar sesión: {str(e)}"
        )
    finally:
        conn.close()
