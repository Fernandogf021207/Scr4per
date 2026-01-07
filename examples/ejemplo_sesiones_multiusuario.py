"""
Ejemplo de uso del nuevo sistema de sesiones multi-usuario.

Este script demuestra cómo usar FacebookScraperManager con sesiones
obtenidas desde la base de datos.
"""
import asyncio
import logging
from src.scrapers.facebook.scraper import (
    FacebookScraperManager,
    obtener_datos_usuario_facebook,
    scrap_friends_all,
)
from src.services.scraping_service import scraping_service
from src.utils.exceptions import (
    SessionExpiredException,
    AccountBannedException,
    SessionNotFoundException,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def ejemplo_scraping_con_sesion_db():
    """
    Ejemplo completo de scraping con sesión obtenida desde la DB.
    """
    # 1. Configurar ID del usuario y plataforma
    id_usuario = 1  # ID del analista en la tabla usuarios
    plataforma = 'facebook'
    perfil_objetivo = 'https://www.facebook.com/username'
    
    manager = None
    
    try:
        # 2. Obtener sesión desde la base de datos
        logger.info(f"Obteniendo sesión para usuario {id_usuario}...")
        session_data = scraping_service.get_session_for_user(id_usuario, plataforma)
        
        logger.info(f"Sesión obtenida: ID={session_data['id_sesion']}, Estado={session_data['estado']}")
        
        # 3. Iniciar el scraper con las credenciales de la DB
        manager = FacebookScraperManager()
        await manager.start(
            storage_state=session_data['cookies'],
            proxy_url=session_data.get('proxy_url'),
            user_agent=session_data.get('user_agent'),
            session_id=session_data['id_sesion'],
            headless=True
        )
        
        # 4. Validar la sesión (early exit)
        logger.info("Validando integridad de la sesión...")
        await manager._validate_session_integrity()
        
        # 5. Obtener la página para usar con las funciones existentes
        page = manager.get_page()
        
        # 6. Realizar scraping (usando las funciones existentes)
        logger.info("Obteniendo datos del perfil...")
        datos_perfil = await obtener_datos_usuario_facebook(page, perfil_objetivo)
        logger.info(f"Perfil: {datos_perfil['nombre_completo']} (@{datos_perfil['username']})")
        
        logger.info("Scrapeando lista de amigos...")
        amigos = await scrap_friends_all(page, perfil_objetivo, datos_perfil['username'])
        logger.info(f"Amigos encontrados: {len(amigos)}")
        
        # 7. Actualizar última actividad de la sesión
        scraping_service.update_session_activity(session_data['id_sesion'])
        logger.info("✅ Scraping completado exitosamente")
        
    except SessionNotFoundException as e:
        logger.error(f"❌ No se encontró sesión: {e.message}")
        # Aquí podrías crear una nueva sesión o notificar al usuario
        
    except SessionExpiredException as e:
        logger.error(f"❌ Sesión expirada: {e.message}")
        # Marcar la sesión como expirada en la DB
        if 'session_data' in locals():
            scraping_service._mark_session_expired(session_data['id_sesion'])
        
    except AccountBannedException as e:
        logger.error(f"❌ Cuenta baneada/checkpoint: {e.message}")
        # Marcar la sesión como baneada en la DB
        if 'session_data' in locals():
            scraping_service.mark_session_banned(session_data['id_sesion'])
        
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}")
        
    finally:
        # 8. Siempre cerrar el navegador
        if manager:
            await manager.close()
            logger.info("Navegador cerrado")


async def ejemplo_validacion_sesion_sin_scraping():
    """
    Ejemplo de solo validar una sesión sin hacer scraping.
    Útil para verificar periódicamente que las sesiones sigan activas.
    """
    id_usuario = 1
    plataforma = 'facebook'
    
    manager = None
    
    try:
        session_data = scraping_service.get_session_for_user(id_usuario, plataforma)
        
        manager = FacebookScraperManager()
        await manager.start(
            storage_state=session_data['cookies'],
            session_id=session_data['id_sesion'],
            headless=True
        )
        
        # Solo validar y salir
        await manager._validate_session_integrity()
        logger.info(f"✅ Sesión {session_data['id_sesion']} válida")
        
        scraping_service.update_session_activity(session_data['id_sesion'])
        
    except (SessionExpiredException, AccountBannedException) as e:
        logger.error(f"❌ Sesión inválida: {e.message}")
        
    finally:
        if manager:
            await manager.close()


if __name__ == '__main__':
    # Ejecutar el ejemplo
    asyncio.run(ejemplo_scraping_con_sesion_db())
    
    # O solo validar la sesión
    # asyncio.run(ejemplo_validacion_sesion_sin_scraping())
