"""
Router para análisis de identidades digitales con integración a casos.

Este módulo maneja el ciclo de vida completo del análisis:
1. Iniciar análisis (dispara scraping con contexto organizacional)
2. Consultar estado del análisis
3. Obtener resultados (grafo JSON desde FTP)
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
import asyncio
from ..schemas import (
    AnalysisRequest,
    AnalysisStatusResponse,
    IdentidadDigitalOut
)
from ..schemas_batch import (
    BatchAnalysisRequest,
    BatchAnalysisResponse
)
from ..db import get_conn
import logging
from src.utils.event_manager import event_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["analyze"])

# Semáforo global para limitar concurrencia de navegadores
GLOBAL_SEMAPHORE = asyncio.Semaphore(3)


# ==================================================================
# REPOSITORY FUNCTIONS (Acceso a BD)
# ==================================================================

def get_identidades_por_personas(conn, personas_ids: List[int]) -> List[dict]:
    """Obtiene todas las identidades digitales de una lista de personas."""
    if not personas_ids:
        return []
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                id_identidad,
                id_persona,
                plataforma,
                usuario_o_url,
                estado,
                ultimo_analisis
            FROM entidades.identidades_digitales
            WHERE id_persona = ANY(%s)
        """, (personas_ids,))
        return cur.fetchall()


def get_identidad_digital(conn, id_identidad: int) -> Optional[dict]:
    """Obtiene una identidad digital por ID."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                id_identidad,
                id_persona,
                plataforma,
                usuario_o_url
            FROM entidades.identidades_digitales
            WHERE id_identidad = %s
        """, (id_identidad,))
        return cur.fetchone()


def update_identidad_estado(conn, id_identidad: int, estado: str, id_caso: int):
    """Actualiza el estado de una identidad digital en el contexto de un caso."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE casos.analisis_identidad
            SET estado = %s::casos.estado_analisis_enum
            WHERE id_identidad = %s AND idcaso = %s
        """, (estado, id_identidad, id_caso))
        conn.commit()
    
    # Emitir evento SSE
    asyncio.create_task(event_manager.broadcast_status(id_identidad, estado, id_caso))


def update_identidad_resultado(conn, id_identidad: int, id_caso: int,
                               id_perfil_scraped: Optional[int],
                               ruta_grafo_ftp: Optional[str]):
    """Actualiza los resultados del análisis en el contexto de un caso."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE casos.analisis_identidad
            SET id_perfil_scraped = %s,
                ruta_grafo_ftp = %s,
                estado = 'analizado'::casos.estado_analisis_enum,
                fecha_analisis = NOW()
            WHERE id_identidad = %s AND idcaso = %s
        """, (id_perfil_scraped, ruta_grafo_ftp, id_identidad, id_caso))
        conn.commit()
    
    # Emitir evento SSE
    asyncio.create_task(event_manager.broadcast_status(id_identidad, 'analizado', id_caso))


def increment_intentos_fallidos(conn, id_identidad: int):
    """Incrementa el contador de intentos fallidos."""
    # No-op si la columna no existe en el esquema MD
    pass


# ==================================================================
# BACKGROUND TASK: Proceso de Análisis
# ==================================================================

async def ejecutar_analisis_background(
    id_identidad: int,
    plataforma: str,
    usuario_o_url: str,
    context: dict,
    max_photos: int,
    headless: bool,
    max_depth: int
):
    """
    Tarea en background que ejecuta el scraping completo.
    
    Pasos:
    1. Marca estado como 'procesando'
    2. Ejecuta scraper correspondiente
    3. Guarda datos en red_x/instagram/facebook
    4. Genera grafo JSON
    5. Sube archivos a FTP con ruta jerárquica
    6. Actualiza estado a 'analizado' con rutas
    """
    from src.utils.storage_paths import (
        build_graph_file_path,
        build_evidence_path,
        parse_user_context_to_path
    )
    from src.utils.ftp_storage import get_ftp_client
    from datetime import datetime
    import json
    
    conn = None
    
    try:
        conn = get_conn()
        
        # 1. Actualizar estado a procesando
        id_caso = context.get('id_caso')
        update_identidad_estado(conn, id_identidad, 'procesando', id_caso)
        logger.info(f"Iniciando análisis de identidad {id_identidad}: {plataforma}/{usuario_o_url}")
        
        # 2. Extraer username de la URL si es necesario
        from src.utils.url import extract_username_from_url
        username = extract_username_from_url(usuario_o_url, plataforma) or usuario_o_url
        
        # Obtener persona_id para construir rutas
        identidad = get_identidad_digital(conn, id_identidad)
        if not identidad:
            raise Exception(f"Identidad {id_identidad} no encontrada")
        persona_id = identidad['id_persona']

        # Construir ruta base para imágenes
        from src.utils.storage_paths import build_hierarchical_ftp_path
        path_params = parse_user_context_to_path(context)
        image_base_path = build_hierarchical_ftp_path(
            organizacion=path_params['organizacion'],
            usuario_id=path_params['usuario_id'],
            caso_id=path_params['caso_id'],
            persona_id=persona_id,
            plataforma=plataforma,
            area=path_params.get('area'),
            departamento=path_params.get('departamento'),
            category='images'
        )

        # 3. Ejecutar scraping simplificado
        result = await _scrape_single_profile(
            platform=plataforma,
            username=username,
            max_photos=max_photos,
            headless=headless,
            image_base_path=image_base_path
        )
        
        if not result or 'error' in result:
            raise Exception(result.get('error', 'Error desconocido en scraping'))
        
        profile_id = result.get('profile_id')
        
        # 4. Generar grafo JSON estandarizado (Schema V2 Multi-Scrape)
        from ..deps import _schema
        
        # Estructuras para el grafo
        profiles_map = {}
        relations_list = []
        root_id = f"{plataforma}:{username}"
        
        # 4.1 Agregar perfil root
        root_prof_data = result.get('profile', {})
        # Asegurar campos mínimos
        if not root_prof_data.get('username'):
            root_prof_data['username'] = username
        if not root_prof_data.get('platform'):
            root_prof_data['platform'] = plataforma
            
        root_prof_data['sources'] = [root_id]
        profiles_map[(plataforma, username)] = root_prof_data

        # 4.2 Obtener relaciones y perfiles relacionados desde BD
        with conn.cursor() as cur:
            schema = _schema(plataforma)
            cur.execute(f"""
                SELECT 
                    r.rel_type,
                    p_related.username as related_username,
                    p_related.full_name,
                    p_related.profile_url,
                    p_related.photo_url
                FROM {schema}.relationships r
                JOIN {schema}.profiles p_owner ON r.owner_profile_id = p_owner.id
                JOIN {schema}.profiles p_related ON r.related_profile_id = p_related.id
                WHERE p_owner.username = %s
                LIMIT 500
            """, (username,))
            
            for row in cur.fetchall():
                rel_username = row['related_username']
                rel_type = row['rel_type']
                
                # Agregar relación
                relations_list.append({
                    "platform": plataforma,
                    "source": username,
                    "target": rel_username,
                    "type": rel_type
                })
                
                # Agregar perfil relacionado
                rel_key = (plataforma, rel_username)
                if rel_key not in profiles_map:
                    profiles_map[rel_key] = {
                        "platform": plataforma,
                        "username": rel_username,
                        "full_name": row['full_name'],
                        "profile_url": row['profile_url'],
                        "photo_url": row['photo_url'],
                        "sources": [root_id]
                    }
                else:
                    if root_id not in profiles_map[rel_key].get('sources', []):
                         profiles_map[rel_key]['sources'].append(root_id)
        
        # 4.3 Construir objeto final
        grafo_data = {
            "schema_version": 2,
            "root_profiles": [root_id],
            "profiles": list(profiles_map.values()),
            "relations": relations_list,
            "warnings": [],
            "meta": {
                "schema_version": 2,
                "generated_at": datetime.now().isoformat(),
                "roots_processed": 1,
                "context": {
                    "id_identidad": id_identidad,
                    "id_caso": context.get('id_caso'),
                    "analizado_por": context.get('id_usuario')
                }
            }
        }
        
        grafo_json = json.dumps(grafo_data, ensure_ascii=False, indent=2)
        
        ruta_grafo = build_graph_file_path(
            **path_params,
            persona_id=persona_id,
            plataforma=plataforma,
            username=username
        )
        ruta_evidencia = build_evidence_path(
            organizacion=path_params['organizacion'],
            usuario_id=path_params['usuario_id'],
            caso_id=path_params['caso_id'],
            persona_id=persona_id,
            plataforma=plataforma,
            area=path_params.get('area'),
            departamento=path_params.get('departamento')
        )
        
        # 6. Subir archivos a FTP
        ftp_client = get_ftp_client()
        
        # Usar la ruta jerárquica calculada previamente
        ftp_client.upload_file(
            path=ruta_grafo,
            data=grafo_json.encode('utf-8')
        )
        
        logger.info(f"Grafo subido a FTP: {ruta_grafo}")
        
        # 7. Actualizar BD con resultados
        update_identidad_resultado(
            conn,
            id_identidad=id_identidad,
            id_caso=id_caso,
            id_perfil_scraped=profile_id,
            ruta_grafo_ftp=ruta_grafo
        )
        
        logger.info(f"Análisis completado exitosamente para identidad {id_identidad}")
        
    except Exception as e:
        logger.exception(f"Error en análisis de identidad {id_identidad}: {e}")
        
        if conn:
            id_caso = context.get('id_caso')
            update_identidad_estado(
                conn,
                id_identidad=id_identidad,
                estado='error',
                id_caso=id_caso
            )
            increment_intentos_fallidos(conn, id_identidad)
    
    finally:
        if conn:
            conn.close()


# Helper function para scraping completo (usando adapters como multi_scrape)
async def _scrape_single_profile(platform: str, username: str, max_photos: int, headless: bool, image_base_path: Optional[str] = None):
    """
    Scraping completo de un perfil incluyendo seguidores/seguidos.
    Usa los mismos adapters que multi_scrape.
    """
    from ..deps import storage_state_for
    from ..repositories import upsert_profile, add_relationship
    from ..services.adapters import launch_browser, close_browser, get_adapter
    import os
    
    conn = get_conn()
    profile_id = None
    
    try:
        # Verificar storage_state
        storage_state = storage_state_for(platform)
        if not storage_state or not os.path.isfile(storage_state):
            raise Exception(f"Storage state no encontrado para {platform}. Inicia sesión primero.")
        
        # Lanzar browser y obtener adapter
        browser = await launch_browser(headless=headless)
        adapter = get_adapter(platform, browser, tenant=None)
        
        try:
            # 1. Obtener perfil principal
            logger.info(f"Obteniendo perfil de {username}...")
            root_profile = await adapter.get_root_profile(username, image_base_path=image_base_path)
            
            # 2. Obtener seguidores y seguidos
            logger.info(f"Obteniendo seguidores de {username}...")
            followers = await adapter.get_followers(username, max_photos, image_base_path=image_base_path)
            
            logger.info(f"Obteniendo seguidos de {username}...")
            following = await adapter.get_following(username, max_photos, image_base_path=image_base_path)
            
            # 3. Si es Facebook, obtener amigos, reacciones y comentarios
            friends = []
            reactors = []
            commenters = []
            
            if platform == 'facebook':
                logger.info(f"Obteniendo amigos de {username}...")
                try:
                    friends = await adapter.get_friends(username)
                except Exception as e:
                    logger.warning(f"No se pudieron obtener amigos: {e}")
                
                logger.info(f"Obteniendo reacciones en fotos de {username}...")
                try:
                    reactors = await adapter.get_photo_reactors(username, max_photos, include_comment_reactions=False)
                except Exception as e:
                    logger.warning(f"No se pudieron obtener reacciones: {e}")
                    
                logger.info(f"Obteniendo comentarios en fotos de {username}...")
                try:
                    commenters = await adapter.get_photo_commenters(username, max_photos)
                except Exception as e:
                    logger.warning(f"No se pudieron obtener comentarios: {e}")
            
            # 4. Guardar en BD
            with conn.cursor() as cur:
                # Perfil principal
                profile_id = upsert_profile(
                    cur,
                    platform=platform,
                    username=root_profile.get('username', username),
                    full_name=root_profile.get('full_name'),
                    profile_url=root_profile.get('profile_url'),
                    photo_url=root_profile.get('photo_url')
                )
                
                # Relaciones - Seguidores
                for follower in followers[:100]:  # Limitar a 100 para no saturar
                    if follower.get('username') and follower['username'] != username:
                        upsert_profile(
                            cur,
                            platform=platform,
                            username=follower['username'],
                            full_name=follower.get('full_name'),
                            profile_url=follower.get('profile_url'),
                            photo_url=follower.get('photo_url')
                        )
                        add_relationship(cur, platform, username, follower['username'], 'follower')
                
                # Relaciones - Seguidos
                for followed in following[:100]:
                    if followed.get('username') and followed['username'] != username:
                        upsert_profile(
                            cur,
                            platform=platform,
                            username=followed['username'],
                            full_name=followed.get('full_name'),
                            profile_url=followed.get('profile_url'),
                            photo_url=followed.get('photo_url')
                        )
                        add_relationship(cur, platform, username, followed['username'], 'following')
                
                # Relaciones - Amigos (Facebook)
                for friend in friends[:100]:
                    if friend.get('username') and friend['username'] != username:
                        upsert_profile(
                            cur,
                            platform=platform,
                            username=friend['username'],
                            full_name=friend.get('full_name'),
                            profile_url=friend.get('profile_url'),
                            photo_url=friend.get('photo_url')
                        )
                        add_relationship(cur, platform, username, friend['username'], 'friend')

                # Relaciones - Reacciones (Facebook)
                for reactor in reactors[:100]:
                    if reactor.get('username') and reactor['username'] != username:
                        upsert_profile(
                            cur,
                            platform=platform,
                            username=reactor['username'],
                            full_name=reactor.get('full_name'),
                            profile_url=reactor.get('profile_url'),
                            photo_url=reactor.get('photo_url')
                        )
                        add_relationship(cur, platform, username, reactor['username'], 'reacted')

                # Relaciones - Comentarios (Facebook)
                for commenter in commenters[:100]:
                    if commenter.get('username') and commenter['username'] != username:
                        upsert_profile(
                            cur,
                            platform=platform,
                            username=commenter['username'],
                            full_name=commenter.get('full_name'),
                            profile_url=commenter.get('profile_url'),
                            photo_url=commenter.get('photo_url')
                        )
                        add_relationship(cur, platform, username, commenter['username'], 'commented')
                
                conn.commit()
            
            logger.info(f"Scraping completado: {len(followers)} seguidores, {len(following)} seguidos, {len(friends)} amigos, {len(reactors)} reacciones, {len(commenters)} comentarios")
            
            return {
                'profile_id': profile_id,
                'profile': root_profile,
                'followers_count': len(followers),
                'following_count': len(following),
                'friends_count': len(friends),
                'reactors_count': len(reactors),
                'commenters_count': len(commenters)
            }
            
        finally:
            await close_browser(browser)
        
    except Exception as e:
        logger.error(f"Error en scraping de {platform}/{username}: {e}")
        return {'error': str(e)}
    
    finally:
        if conn:
            conn.close()


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

# @router.post("/batch") -> MOVED TO batch_analyze.py



@router.post("/start", response_model=AnalysisStatusResponse)
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """
    Inicia el análisis de una identidad digital.
    
    El proceso se ejecuta en background y actualiza el estado en la BD.
    
    Args:
        request: Solicitud con id_identidad, contexto de usuario y parámetros
        background_tasks: FastAPI background tasks
    
    Returns:
        Estado actual de la identidad digital
    
    Raises:
        404: Identidad digital no encontrada
        409: Identidad ya está siendo procesada (a menos que force=true)
    """
    conn = get_conn()
    
    try:
        # Validar que existe la identidad
        identidad = get_identidad_digital(conn, request.id_identidad)
        
        if not identidad:
            raise HTTPException(
                status_code=404,
                detail=f"Identidad digital {request.id_identidad} no encontrada"
            )
        
        # Validar que no esté ya procesándose
        # Permitir reintentar si está en error o si pasaron más de 10 minutos
        if identidad['estado'] == 'procesando':
            from datetime import datetime, timedelta
            ultimo_analisis = identidad.get('ultimo_analisis')
            
            # Si ha pasado más de 10 minutos, asumir que el proceso murió
            if ultimo_analisis:
                tiempo_transcurrido = datetime.now(ultimo_analisis.tzinfo) - ultimo_analisis
                if tiempo_transcurrido > timedelta(minutes=10):
                    logger.warning(f"Análisis {request.id_identidad} lleva más de 10 min en 'procesando'. Permitiendo reinicio.")
                else:
                    raise HTTPException(
                        status_code=409,
                        detail="El análisis ya está en proceso. Espera a que termine o reinténtalo después de 10 minutos."
                    )
            else:
                raise HTTPException(
                    status_code=409,
                    detail="El análisis ya está en proceso"
                )
        
        # Agendar análisis en background
        background_tasks.add_task(
            ejecutar_analisis_background,
            id_identidad=request.id_identidad,
            plataforma=identidad['plataforma'],
            usuario_o_url=identidad['usuario_o_url'],
            context=request.context.dict(),
            max_photos=request.max_photos,
            headless=request.headless,
            max_depth=request.max_depth
        )
        
        # Actualizar estado a procesando inmediatamente
        update_identidad_estado(conn, request.id_identidad, 'procesando')
        
        logger.info(f"Análisis agendado para identidad {request.id_identidad}")
        
        return AnalysisStatusResponse(
            id_identidad=request.id_identidad,
            estado='procesando',
            mensaje_error=None,
            progreso={"mensaje": "Análisis iniciado"},
            ultimo_analisis=None,
            ruta_grafo_ftp=None
        )
        
    finally:
        conn.close()


@router.get("/status/{id_identidad}", response_model=AnalysisStatusResponse)
async def get_analysis_status(id_identidad: int):
    """
    Consulta el estado actual de un análisis.
    
    Args:
        id_identidad: ID de la identidad digital
    
    Returns:
        Estado actual del análisis
    
    Raises:
        404: Identidad digital no encontrada
    """
    conn = get_conn()
    
    try:
        identidad = get_identidad_digital(conn, id_identidad)
        
        if not identidad:
            raise HTTPException(
                status_code=404,
                detail=f"Identidad digital {id_identidad} no encontrada"
            )
        
        # Construir información de progreso según el estado
        progreso = None
        if identidad['estado'] == 'procesando':
            progreso = {"mensaje": "Análisis en curso..."}
        elif identidad['estado'] == 'analizado':
            progreso = {"mensaje": "Análisis completado"}
        elif identidad['estado'] == 'error':
            progreso = {"mensaje": "El análisis falló"}
        
        return AnalysisStatusResponse(
            id_identidad=id_identidad,
            estado=identidad['estado'],
            mensaje_error=identidad.get('mensaje_error'),
            progreso=progreso,
            ultimo_analisis=identidad['ultimo_analisis'],
            ruta_grafo_ftp=identidad['ruta_grafo_ftp']
        )
        
    finally:
        conn.close()


@router.post("/reset/{id_identidad}")
async def reset_analysis(id_identidad: int):
    """
    Resetea el estado de una identidad a 'pendiente'.
    
    Útil cuando un análisis quedó en 'procesando' por un error.
    
    Args:
        id_identidad: ID de la identidad digital
    
    Returns:
        Confirmación del reset
    
    Raises:
        404: Identidad digital no encontrada
    """
    conn = get_conn()
    
    try:
        identidad = get_identidad_digital(conn, id_identidad)
        
        if not identidad:
            raise HTTPException(
                status_code=404,
                detail=f"Identidad digital {id_identidad} no encontrada"
            )
        
        update_identidad_estado(conn, id_identidad, 'pendiente', mensaje_error=None)
        
        logger.info(f"Estado de identidad {id_identidad} reseteado a 'pendiente'")
        
        return {
            "id_identidad": id_identidad,
            "mensaje": "Estado reseteado a 'pendiente'. Puedes iniciar el análisis nuevamente.",
            "estado_anterior": identidad['estado']
        }
        
    finally:
        conn.close()


@router.get("/result/{id_identidad}")
async def get_analysis_result(id_identidad: int):
    """
    Obtiene el resultado del análisis (grafo JSON desde FTP).
    
    Args:
        id_identidad: ID de la identidad digital
    
    Returns:
        JSON del grafo generado
    
    Raises:
        404: Identidad no encontrada o análisis no completado
        500: Error al recuperar archivo de FTP
    """
    conn = get_conn()
    
    try:
        identidad = get_identidad_digital(conn, id_identidad)
        
        if not identidad:
            raise HTTPException(
                status_code=404,
                detail=f"Identidad digital {id_identidad} no encontrada"
            )
        
        if identidad['estado'] != 'analizado':
            raise HTTPException(
                status_code=404,
                detail=f"Análisis no completado. Estado actual: {identidad['estado']}"
            )
        
        if not identidad['ruta_grafo_ftp']:
            raise HTTPException(
                status_code=404,
                detail="Ruta del grafo no disponible"
            )
        
        # Obtener archivo desde FTP
        from src.utils.ftp_storage import get_ftp_client
        import json
        
        ftp_client = get_ftp_client()
        
        try:
            # TODO: Implementar método download en FTPClient
            # Por ahora retornar metadata
            return {
                "id_identidad": id_identidad,
                "ruta_ftp": identidad['ruta_grafo_ftp'],
                "plataforma": identidad['plataforma'],
                "ultimo_analisis": identidad['ultimo_analisis'],
                "mensaje": "Descarga desde FTP pendiente de implementación"
            }
            
        except Exception as e:
            logger.error(f"Error al obtener grafo desde FTP: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al recuperar archivo: {str(e)}"
            )
        
    finally:
        conn.close()


def _merge_graphs(graphs_data: List[dict]) -> dict:
    """Fusiona múltiples grafos JSON en una estructura consolidada."""
    merged = {
        "schema_version": 2,
        "root_profiles": [],
        "profiles": [],
        "relations": [],
        "warnings": [],
        "meta": {
            "schema_version": 2,
            "roots_requested": 0,
            "roots_processed": 0,
            "generated_at": datetime.now().isoformat(),
            "roots_timings": {},
            "platform_limits": {}
        }
    }
    
    profiles_map = {}
    relations_set = set()
    root_profiles_set = set()
    
    for g in graphs_data:
        # Merge root_profiles
        for rp in g.get("root_profiles", []):
            if rp not in root_profiles_set:
                merged["root_profiles"].append(rp)
                root_profiles_set.add(rp)
        
        # Merge profiles
        for p in g.get("profiles", []):
            key = (p.get("platform"), p.get("username"))
            if not key[0] or not key[1]:
                continue
                
            if key not in profiles_map:
                profiles_map[key] = p
            else:
                # Merge sources
                existing_sources = set(profiles_map[key].get("sources", []))
                new_sources = set(p.get("sources", []))
                profiles_map[key]["sources"] = sorted(list(existing_sources | new_sources))
                
                # Merge other fields if needed (e.g. take the one with more info)
                if not profiles_map[key].get("photo_url") and p.get("photo_url"):
                    profiles_map[key]["photo_url"] = p.get("photo_url")
                    
        # Merge relations
        for r in g.get("relations", []):
            # Create a hashable representation
            r_tuple = (r.get("platform"), r.get("source"), r.get("target"), r.get("type"))
            if r_tuple not in relations_set:
                merged["relations"].append(r)
                relations_set.add(r_tuple)
                
        # Merge warnings
        merged["warnings"].extend(g.get("warnings", []))
        
        # Merge meta
        if "meta" in g:
            merged["meta"]["roots_processed"] += g["meta"].get("roots_processed", 0)
            if "roots_timings" in g["meta"]:
                merged["meta"]["roots_timings"].update(g["meta"]["roots_timings"])

    merged["profiles"] = list(profiles_map.values())
    merged["meta"]["roots_requested"] = len(merged["root_profiles"])
    
    return merged


@router.get("/graph/{identidades_ids}")
def get_analysis_graph(identidades_ids: str, id_caso: int):
    """
    Descarga y fusiona los JSON de los grafos desde el FTP.
    Acepta un ID único o una lista separada por comas (ej: "29,27,26").
    Requiere id_caso para identificar los análisis específicos.
    """
    conn = get_conn()
    try:
        # 1. Parsear IDs
        try:
            ids_list = [int(x.strip()) for x in identidades_ids.split(',') if x.strip()]
        except ValueError:
             raise HTTPException(status_code=400, detail="Formato de IDs inválido. Debe ser una lista de enteros separados por comas.")
        
        if not ids_list:
             raise HTTPException(status_code=400, detail="No se proporcionaron IDs válidos.")

        # 2. Buscar estados y rutas en BD
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id_identidad, estado, ruta_grafo_ftp
                FROM casos.analisis_identidad
                WHERE id_identidad = ANY(%s) AND idcaso = %s
            """, (ids_list, id_caso))
            analisis_rows = cur.fetchall()

        if not analisis_rows:
            raise HTTPException(status_code=404, detail="No se encontraron análisis para las identidades especificadas en este caso")
            
        # 3. Descargar y acumular grafos
        from src.utils.ftp_storage import get_ftp_client
        import json
        
        ftp = get_ftp_client()
        graphs_data = []
        
        for row in analisis_rows:
            if row['estado'] == 'analizado' and row['ruta_grafo_ftp']:
                try:
                    content = ftp.download_file(row['ruta_grafo_ftp'])
                    graphs_data.append(json.loads(content))
                except Exception as e:
                    logger.error(f"Error descargando grafo {row['id_identidad']}: {e}")
                    # Podríamos agregar un warning al resultado final en lugar de fallar todo
            else:
                # Análisis no listo o sin archivo
                pass

        if not graphs_data:
             # Si pedimos varios y ninguno está listo, es un 404 o 400.
             # Si al menos uno falló pero otros no, devolvemos lo que hay.
             # Si la lista estaba vacía desde el principio (ninguno analizado), error.
             raise HTTPException(status_code=404, detail="Ninguno de los análisis solicitados tiene un grafo disponible.")

        # 4. Fusionar grafos
        merged_graph = _merge_graphs(graphs_data)
        
        return merged_graph
            
    finally:
        conn.close()
