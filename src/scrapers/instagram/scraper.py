import logging
from src.scrapers.instagram.utils import (
    obtener_foto_perfil_instagram,
    obtener_nombre_usuario_instagram,
    procesar_usuarios_en_pagina
)
logger = logging.getLogger(__name__)

async def obtener_datos_usuario_principal(page, perfil_url):
    print("Obteniendo datos del perfil principal de Instagram...")
    await page.goto(perfil_url)
    await page.wait_for_timeout(5000)
    datos_usuario = await obtener_nombre_usuario_instagram(page)
    foto = await obtener_foto_perfil_instagram(page)
    datos_usuario['foto_perfil'] = foto
    datos_usuario['url_usuario'] = perfil_url
    print(f"Usuario detectado: @{datos_usuario['username']} ({datos_usuario['nombre_completo']})")
    return datos_usuario

async def scrap_lista_usuarios(page, perfil_url, tipo):
    print(f"\n🔄 Navegando a {tipo}...")
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(3000)

        if tipo == "seguidores":
            boton = await page.query_selector('a[href$="/followers/"]')
        elif tipo == "seguidos":
            boton = await page.query_selector('a[href$="/following/"]')
        else:
            print("❌ Tipo de lista inválido")
            return []

        if not boton:
            print(f"❌ No se encontró el botón de {tipo}")
            return []

        await boton.click()
        await page.wait_for_timeout(3000)

        usuarios_dict = {}
        scroll_attempts = 0
        while scroll_attempts < INSTAGRAM_CONFIG['max_scroll_attempts']:
            count = await procesar_usuarios_en_pagina(page, usuarios_dict)
            await page.evaluate("document.querySelector('div[role=\"dialog\"] ul').parentNode.scrollTop = document.querySelector('div[role=\"dialog\"] ul').parentNode.scrollHeight")
            await page.wait_for_timeout(INSTAGRAM_CONFIG['scroll_pause_ms'])
            scroll_attempts += 1
        print(f"✅ {tipo.capitalize()} extraídos: {len(usuarios_dict)}")
        return list(usuarios_dict.values())

    except Exception as e:
        print(f"❌ Error extrayendo {tipo}: {e}")
        return []
