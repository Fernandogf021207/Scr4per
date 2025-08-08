import logging
from src.scrapers.facebook.utils import (
    obtener_foto_perfil_facebook,
    obtener_nombre_usuario_facebook,
    procesar_usuarios_en_pagina
)
logger = logging.getLogger(__name__)

async def obtener_datos_usuario_principal(page, perfil_url):
    print("Obteniendo datos del perfil principal de Facebook...")
    await page.goto(perfil_url)
    await page.wait_for_timeout(5000)
    datos_usuario = await obtener_nombre_usuario_facebook(page)
    foto = await obtener_foto_perfil_facebook(page)
    datos_usuario['foto_perfil'] = foto
    datos_usuario['url_usuario'] = perfil_url
    print(f"Usuario detectado: @{datos_usuario['username']} ({datos_usuario['nombre_completo']})")
    return datos_usuario

async def scrap_lista_usuarios(page, url_amigos):
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    print("\n🔄 Navegando a la lista de amigos...")
    try:
        await page.goto(url_amigos)
        await page.wait_for_timeout(3000)

        usuarios_dict = {}
        scroll_attempts = 0
        while scroll_attempts < FACEBOOK_CONFIG['max_scroll_attempts']:
            count = await procesar_usuarios_en_pagina(page, usuarios_dict)
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await page.wait_for_timeout(FACEBOOK_CONFIG['scroll_pause_ms'])
            scroll_attempts += 1

        print(f"✅ Amigos extraídos: {len(usuarios_dict)}")
        return list(usuarios_dict.values())
    except Exception as e:
        print(f"❌ Error extrayendo amigos: {e}")
        return []
