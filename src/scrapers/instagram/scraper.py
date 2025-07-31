import asyncio
from src.utils.common import limpiar_url
from src.utils.output import guardar_resultados
from src.scrapers.instagram.utils import (
    obtener_foto_perfil_instagram,
    obtener_nombre_usuario_instagram,
    extraer_usuarios_instagram,
    extraer_posts_del_perfil,
    extraer_comentarios_post,
    navegar_a_lista_instagram
)

async def scrap_usuarios_instagram(perfil_url, extraer_comentarios=True, max_posts=5):
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(storage_state=INSTAGRAM_CONFIG["storage_state_path"])
        page = await context.new_page()

        print(f"Navegando al perfil de Instagram: {perfil_url}")
        await page.goto(perfil_url)
        await page.wait_for_timeout(5000)

        print("Obteniendo datos del perfil principal...")
        
        datos_usuario_ig = await obtener_nombre_usuario_instagram(page)
        username = datos_usuario_ig['username']
        nombre_completo = datos_usuario_ig['nombre_completo']
        
        foto_perfil = await obtener_foto_perfil_instagram(page)
        
        print(f"Usuario detectado: @{username} ({nombre_completo})")
        
        usuario_id = 1
        datos_usuario = {
            'id_usuario': [usuario_id],
            'nombre_completo': [nombre_completo],  # Changed from nombre_usuario to nombre_completo
            'username': [username],
            'url_usuario': [perfil_url],
            'url_foto_perfil': [foto_perfil if foto_perfil else ""]
        }

        print("\n🔄 Extrayendo seguidores...")
        seguidores = []
        if await navegar_a_lista_instagram(page, perfil_url, "followers"):
            seguidores = await extraer_usuarios_instagram(page, "seguidores", username)
            print(f"📊 Seguidores encontrados: {len(seguidores)}")
        else:
            print("❌ No se pudieron extraer seguidores")

        print("\n🔄 Extrayendo seguidos...")
        seguidos = []
        if await navegar_a_lista_instagram(page, perfil_url, "following"):
            seguidos = await extraer_usuarios_instagram(page, "seguidos", username)
            print(f"📊 Seguidos encontrados: {len(seguidos)}")
        else:
            print("❌ No se pudieron extraer seguidos")

        comentarios = []
        if extraer_comentarios:
            print(f"\n💬 Extrayendo comentarios de los últimos {max_posts} posts...")
            
            await page.goto(perfil_url)
            await page.wait_for_timeout(3000)
            
            urls_posts = await extraer_posts_del_perfil(page, max_posts)
            
            for i, url_post in enumerate(urls_posts, 1):
                comentarios_post = await extraer_comentarios_post(page, url_post, i)
                comentarios.extend(comentarios_post)
                await asyncio.sleep(2)
            
            print(f"📊 Total de comentarios únicos encontrados: {len(comentarios)}")

        if len(seguidores) == 0 and len(seguidos) == 0 and len(comentarios) == 0:
            print("⚠️ No se encontraron datos. Posibles causas:")
            print("  - El perfil es privado")
            print("  - No hay sesión iniciada")
            print("  - Instagram cambió su estructura")
            print("  - Necesitas seguir al usuario para ver estas listas")
            await browser.close()
            return None
        
        archivo_creado = guardar_resultados(username, datos_usuario, seguidores, seguidos, comentarios, platform="instagram")
        
        await browser.close()
        return archivo_creado