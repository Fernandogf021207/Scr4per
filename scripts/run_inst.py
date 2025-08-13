import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from playwright.async_api import async_playwright
from src.utils.logging_config import setup_logging
from src.scrapers.instagram.scraper import (
    obtener_datos_usuario_principal,
    scrap_seguidores,
    scrap_seguidos,
    scrap_comentadores_instagram
)
from src.utils.output import guardar_resultados

logger = setup_logging()

def mostrar_menu():
    print("\n📋 Menú de Opciones:")
    print("1. Scrapear seguidores")
    print("2. Scrapear seguidos") 
    print("3. Scrapear comentadores")
    print("4. Scrapear todo (seguidores, seguidos y comentadores)")
    print("5. Salir")
    return input("Selecciona una opción (1-5): ")

async def main_instagram():
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    try:
        print("📋 Instrucciones:")
        print("1. Asegúrate de tener una sesión iniciada en Instagram")
        print("2. El perfil debe ser público o debes seguir al usuario")
        print("3. Guarda tu sesión ejecutando: await context.storage_state(path='data/storage/instagram_storage_state.json')")
        print("4. Este scraper extraerá seguidores, seguidos Y comentarios")
        print()

        url = input("Ingresa la URL del perfil de Instagram (ej: https://www.instagram.com/usuario/): ")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(storage_state=INSTAGRAM_CONFIG["storage_state_path"])
            page = await context.new_page()

            while True:
                opcion = mostrar_menu()

                if opcion not in ['1', '2', '3', '4', '5']:
                    print("❌ Opción inválida. Por favor, selecciona una opción válida (1-5).")
                    continue

                if opcion == '5':
                    print("👋 Saliendo del programa...")
                    break

                datos_usuario = await obtener_datos_usuario_principal(page, url)
                username = datos_usuario['username']

                seguidores = []
                seguidos = []
                comentadores = []

                if opcion in ['1', '4']:  # Scrapear seguidores
                    print("\n🔍 Scrapeando seguidores...")
                    seguidores = await scrap_seguidores(page, url, username)

                if opcion in ['2', '4']:  # Scrapear seguidos
                    print("\n🔍 Scrapeando seguidos...")
                    seguidos = await scrap_seguidos(page, url, username)

                if opcion in ['3', '4']:  # Scrapear comentadores
                    print("\n🔍 Scrapeando comentadores...")
                    max_posts = 5
                    try:
                        max_posts_input = input("¿Cuántos posts analizar para comentarios? [5]: ").strip()
                        if max_posts_input:
                            max_posts = int(max_posts_input)
                    except ValueError:
                        max_posts = 5
                    
                    comentadores = await scrap_comentadores_instagram(page, url, username, max_posts)

                # Verificar si se encontraron datos
                total_usuarios = len(seguidores) + len(seguidos) + len(comentadores)
                
                if total_usuarios == 0:
                    print("⚠️ No se encontraron usuarios. Posibles causas:")
                    print("  - El perfil es privado")
                    print("  - No hay sesión iniciada correctamente")
                    print("  - Instagram cambió su estructura")
                    print("  - Necesitas seguir al usuario para ver estas listas")
                    continue

                # Mostrar resumen
                print(f"\n📊 Resumen de datos extraídos:")
                if seguidores:
                    print(f"  👥 Seguidores: {len(seguidores)}")
                if seguidos:
                    print(f"  👥 Seguidos: {len(seguidos)}")
                if comentadores:
                    print(f"  💬 Comentadores: {len(comentadores)}")

                # Guardar resultados
                archivo_creado = guardar_resultados(
                    username, 
                    datos_usuario, 
                    seguidores if seguidores else [], 
                    seguidos if seguidos else [], 
                    comentadores if comentadores else [], 
                    platform='instagram'
                )
                print(f"\n🎉 ¡Scraping completado! {archivo_creado}")

                continuar = input("\n¿Desea realizar otra operación? (s/n): ").lower()
                if continuar != 's':
                    print("👋 Saliendo del programa...")
                    break

            await browser.close()

    except KeyboardInterrupt:
        print("\n⚠️ Proceso interrumpido por el usuario")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")

def imprimir_banner():
    banner = """
 ▗▄▄▖▗▞▀▘ ▄▄▄ ▄  ▗▖▄▄▄▄  ▄▄▄▄  ▗▞▀▚▖ ▄▄▄ 
▐▌   ▝▚▄▖█    █  ▐▌█   █ █   █ ▐▛▀▀▘█    
 ▝▀▚▖    █    ▀▀▀▜▌█▄▄▄▀ █▄▄▄▀ ▝▚▄▄▖█    
▗▄▄▞▘            ▐▌█     █               
                   ▀     ▀    (INSTAGRAM VERSION)           
    """
    print(banner)

if __name__ == "__main__":
    imprimir_banner()
    asyncio.run(main_instagram())
