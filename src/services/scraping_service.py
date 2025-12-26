"""
Servicio para obtener y gestionar sesiones de scraping desde la base de datos.
"""
from typing import Optional, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import os

from src.utils.exceptions import SessionNotFoundException, SessionExpiredException


class ScrapingService:
    """Servicio para gestionar sesiones de scraping desde la DB."""
    
    def __init__(self):
        """Inicializa el servicio con la conexión a la base de datos."""
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'database': os.getenv('DB_NAME', 'scraper_db'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'postgres')
        }
    
    def get_session_for_user(self, id_usuario: int, plataforma: str) -> Dict[str, Any]:
        """
        Obtiene la sesión activa para un usuario y plataforma específicos.
        
        Args:
            id_usuario: ID del usuario en la base de datos
            plataforma: Nombre de la plataforma (facebook, instagram, x)
            
        Returns:
            Diccionario con los datos de la sesión incluyendo:
            - id_sesion: ID de la sesión
            - cookies: Diccionario con storage_state de Playwright
            - proxy_url: URL del proxy (opcional)
            - user_agent: User agent del navegador
            - estado: Estado de la sesión
            - ultima_actividad: Timestamp de última actividad
            
        Raises:
            SessionNotFoundException: Si no existe sesión para el usuario/plataforma
            SessionExpiredException: Si la sesión existe pero no está activa o expiró
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = """
                SELECT 
                    id_sesion,
                    id_usuario,
                    plataforma,
                    cookies,
                    proxy_url,
                    user_agent,
                    estado,
                    ultima_actividad,
                    fecha_creacion
                FROM entidades.sesiones_scraping
                WHERE id_usuario = %s AND plataforma = %s
                ORDER BY ultima_actividad DESC
                LIMIT 1
            """
            
            cursor.execute(query, (id_usuario, plataforma))
            session = cursor.fetchone()
            
            if not session:
                raise SessionNotFoundException(
                    platform=plataforma,
                    message=f"No se encontró sesión para usuario {id_usuario} en {plataforma}"
                )
            
            # Verificar que la sesión esté activa
            if session['estado'] != 'activa':
                raise SessionExpiredException(
                    platform=plataforma,
                    message=f"La sesión está en estado '{session['estado']}', no 'activa'"
                )
            
            # Verificar que la sesión no haya expirado (más de 30 días sin actividad)
            if session['ultima_actividad']:
                dias_inactividad = (datetime.now() - session['ultima_actividad']).days
                if dias_inactividad > 30:
                    # Actualizar estado a expirada
                    self._mark_session_expired(session['id_sesion'])
                    raise SessionExpiredException(
                        platform=plataforma,
                        message=f"La sesión expiró por inactividad ({dias_inactividad} días)"
                    )
            
            cursor.close()
            return dict(session)
            
        except (SessionNotFoundException, SessionExpiredException):
            raise
        except Exception as e:
            raise Exception(f"Error al obtener sesión desde DB: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def update_session_activity(self, id_sesion: int) -> None:
        """
        Actualiza el timestamp de última actividad de una sesión.
        
        Args:
            id_sesion: ID de la sesión a actualizar
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            query = """
                UPDATE entidades.sesiones_scraping
                SET ultima_actividad = NOW()
                WHERE id_sesion = %s
            """
            
            cursor.execute(query, (id_sesion,))
            conn.commit()
            cursor.close()
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error al actualizar actividad de sesión: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def reset_error_count(self, id_sesion: int) -> None:
        """
        Resetea el contador de errores y actualiza la actividad en caso de scraping exitoso.
        
        Args:
            id_sesion: ID de la sesión a actualizar
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            query = """
                UPDATE entidades.sesiones_scraping
                SET error_count = 0, ultima_actividad = NOW()
                WHERE id_sesion = %s
            """
            
            cursor.execute(query, (id_sesion,))
            conn.commit()
            cursor.close()
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error al resetear error_count: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def increment_error_count(self, id_sesion: int) -> None:
        """
        Incrementa el contador de errores de una sesión.
        Si error_count >= 5, cambia automáticamente el estado a 'bloqueada'.
        
        Args:
            id_sesion: ID de la sesión a actualizar
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Incrementar error_count
            query = """
                UPDATE entidades.sesiones_scraping
                SET error_count = error_count + 1
                WHERE id_sesion = %s
                RETURNING error_count
            """
            
            cursor.execute(query, (id_sesion,))
            result = cursor.fetchone()
            
            if result:
                error_count = result[0]
                
                # Circuit Breaker: Si error_count >= 5, bloquear sesión
                if error_count >= 5:
                    update_state_query = """
                        UPDATE entidades.sesiones_scraping
                        SET estado = 'bloqueada'
                        WHERE id_sesion = %s
                    """
                    cursor.execute(update_state_query, (id_sesion,))
            
            conn.commit()
            cursor.close()
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error al incrementar error_count: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def _mark_session_expired(self, id_sesion: int) -> None:
        """
        Marca una sesión como expirada.
        
        Args:
            id_sesion: ID de la sesión a marcar como expirada
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            query = """
                UPDATE entidades.sesiones_scraping
                SET estado = 'expirada'
                WHERE id_sesion = %s
            """
            
            cursor.execute(query, (id_sesion,))
            conn.commit()
            cursor.close()
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error al marcar sesión como expirada: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def mark_session_banned(self, id_sesion: int) -> None:
        """
        Marca una sesión como baneada.
        
        Args:
            id_sesion: ID de la sesión a marcar como baneada
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            query = """
                UPDATE entidades.sesiones_scraping
                SET estado = 'baneada'
                WHERE id_sesion = %s
            """
            
            cursor.execute(query, (id_sesion,))
            conn.commit()
            cursor.close()
            
        except Exception as e:
            if conn:
                conn.rollback()
            raise Exception(f"Error al marcar sesión como baneada: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def get_storage_state(self, id_usuario: int, plataforma: str) -> Dict[str, Any]:
        """
        Obtiene el storage_state listo para usar con Playwright.
        
        Args:
            id_usuario: ID del usuario
            plataforma: Nombre de la plataforma
            
        Returns:
            Diccionario con formato storage_state de Playwright
        """
        session = self.get_session_for_user(id_usuario, plataforma)
        return session['cookies']


# Instancia global del servicio
scraping_service = ScrapingService()
