import asyncio
import logging
from urllib.parse import urljoin
from src.utils.common import limpiar_url
from src.utils.output import guardar_resultados
from src.scrapers.facebook.utils import (
    obtener_foto_perfil_facebook,
    obtener_nombre_usuario_facebook,
    procesar_usuarios_en_pagina_facebook,
    obtener_comentadores_facebook
)

logger = logging.getLogger(__name__)

async def extraer_usuarios_pagina(page, tipo_lista="seguidores"):
    """Extraer usuarios de una lista (seguidores o amigos) con scroll mejorado"""
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    print(f"Cargando {tipo_lista}...")
    usuarios_dict = {}
    
    scroll_attempts = 0
    max_scroll_attempts = FACEBOOK_CONFIG["max_scroll_attempts"]
    no_new_content_count = 0
    max_no_new_content = FACEBOOK_CONFIG["max_no_new_content"]
    
    await page.wait_for_timeout(3000)
    
    while scroll_attempts < max_scroll_attempts and no_new_content_count < max_no_new_content:
        try:
            current_user_count = len(usuarios_dict)

            await page.query_selector_all('div[role="main"] div:has(a[tabindex="0"])')

            await page.wait_for_timeout(FACEBOOK_CONFIG["scroll_pause_ms"])
            nuevos_usuarios_encontrados = await procesar_usuarios_en_pagina_facebook(page, usuarios_dict, tipo_lista)
            
            if len(usuarios_dict) > current_user_count:
                no_new_content_count = 0
                print(f"  📊 {tipo_lista}: {len(usuarios_dict)} usuarios encontrados (scroll {scroll_attempts + 1})")
            else:
                no_new_content_count += 1
                print(f"  ⏳ Sin nuevos usuarios en scroll {scroll_attempts + 1} (intentos sin contenido: {no_new_content_count})")
            
            scroll_attempts += 1
            
            if scroll_attempts % 10 == 0:
                print(f"  🔄 Pausa para evitar rate limiting... ({len(usuarios_dict)} usuarios hasta ahora)")
                await page.wait_for_timeout(FACEBOOK_CONFIG["rate_limit_pause_ms"])
            
            is_at_bottom = await page.evaluate("""
                () => {
                    return (window.innerHeight + window.pageYOffset) >= document.body.scrollHeight - 100;
                }
            """)
            
            if is_at_bottom and no_new_content_count >= 3:
                print(f"  ✅ Llegamos al final de la lista de {tipo_lista}")
                break
                
        except Exception as e:
            logger.warning(f"Error en scroll {scroll_attempts}: {e}")
            no_new_content_count += 1
            
        await page.wait_for_timeout(1000)

    print(f"✅ Scroll completado para {tipo_lista}. Total de scrolls: {scroll_attempts}")
    print(f"📊 Usuarios únicos extraídos: {len(usuarios_dict)}")
    
    return list(usuarios_dict.values())

async def obtener_datos_usuario_principal(page, perfil_url):
    """Obtener datos del usuario principal"""
    print("Obteniendo datos del perfil principal...")
    await page.goto(perfil_url)
    await page.wait_for_timeout(5000)
    
    datos_usuario_fb = await obtener_nombre_usuario_facebook(page)
    username = datos_usuario_fb['username']
    nombre_completo = datos_usuario_fb['nombre_completo']
    foto_perfil = await obtener_foto_perfil_facebook(page)
    
    print(f"Usuario detectado: @{username} ({nombre_completo})")
    
    return {
        'id_usuario': [1],
        'username': [username],
        'nombre_usuario': [nombre_completo],
        'url_usuario': [perfil_url],
        'url_foto_perfil': [foto_perfil or ""]
    }

async def scrap_seguidores(page, perfil_url, username):
    """Scrapear seguidores del usuario"""
    print("\n🔄 Navegando a seguidores...")
    try:
        followers_url = urljoin(perfil_url, "followers")
        await page.goto(followers_url)
        await page.wait_for_timeout(3000)
        seguidores = await extraer_usuarios_pagina(page, "seguidores")
        print(f"📊 Seguidores encontrados: {len(seguidores)}")
        return seguidores
    except Exception as e:
        print(f"❌ Error extrayendo seguidores: {e}")
        return []

async def scrap_seguidos(page, perfil_url, username):
    """Scrapear usuarios seguidos/amigos por el usuario"""
    print("\n🔄 Navegando a amigos...")
    try:
        friends_url = urljoin(perfil_url, "friends_all")
        await page.goto(friends_url)
        await page.wait_for_timeout(3000)
        seguidos = await extraer_usuarios_pagina(page, "amigos")
        print(f"📊 Amigos encontrados: {len(seguidos)}")
        return seguidos
    except Exception as e:
        print(f"❌ Error extrayendo amigos: {e}")
        return []

async def scrap_comentadores(page, perfil_url, username):
    """Scrapear usuarios que comentaron los posts del usuario"""
    print("\n🔄 Navegando al perfil para extraer comentadores...")
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(3000)
        comentadores = await obtener_comentadores_facebook(page)
        print(f"📊 Comentadores encontrados: {len(comentadores)}")
        return comentadores
    except Exception as e:
        print(f"❌ Error extrayendo comentadores: {e}")
        return []