import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from playwright.async_api import async_playwright
from src.utils.logging_config import setup_logging
from src.scrapers.x.scraper import (
    obtener_datos_usuario_principal,
    scrap_seguidores,
    scrap_seguidos,
    scrap_comentadores
)
from src.utils.output import guardar_resultados

logger = setup_logging()

def mostrar_menu():
    """Mostrar el menú de opciones"""
    print("\n📋 Menú de Opciones:")
    print("1. Scrapear seguidores")
    print("2. Scrapear seguidos")
    print("3. Scrapear comentadores")
    print("4. Scrapear todo")
    print("5. Salir")
    return input("Selecciona una opción (1-5): ")

async def main_x():
    from src.scrapers.x.config import X_CONFIG
    try:
        print("📋 Instrucciones:")
        print("1. Asegúrate de tener una sesión iniciada en X")
        print("2. El perfil debe ser público o debes seguir al usuario")
        print("3. Guarda tu sesión ejecutando: await context.storage_state(path='data/storage/x_storage_state.json')")
        print("4. X requiere autenticación para ver seguidores, seguidos y comentarios")
        print()
        
        url = input("Ingresa la URL del perfil de X (ej: https://x.com/usuario): ")
        if "twitter.com" in url:
            url = url.replace("twitter.com", "x.com")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(storage_state=X_CONFIG["storage_state_path"])
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
                
                if opcion in ['1', '4']:
                    seguidores = await scrap_seguidores(page, url, username)
                
                if opcion in ['2', '4']:
                    seguidos = await scrap_seguidos(page, url, username)
                
                if opcion in ['3', '4']:
                    max_posts = 10
                    try:
                        max_posts_input = input("¿Cuántos posts analizar para comentarios? [10]: ").strip()
                        if max_posts_input:
                            max_posts = int(max_posts_input)
                    except ValueError:
                        max_posts = 10
                    comentadores = await scrap_comentadores(page, url, username, max_posts=max_posts)
                
                if opcion != '4' and (
                    (opcion == '1' and not seguidores) or
                    (opcion == '2' and not seguidos) or
                    (opcion == '3' and not comentadores)
                ):
                    print("⚠️ No se encontraron datos. Posibles causas:")
                    print("  - El perfil es privado")
                    print("  - No hay sesión iniciada")
                    print("  - X cambió su estructura")
                    print("  - Necesitas estar logueado para ver estas listas")
                    continue
                
                if opcion == '4' and not seguidores and not seguidos and not comentadores:
                    print("⚠️ No se encontraron datos. Posibles causas:")
                    print("  - El perfil es privado")
                    print("  - No hay sesión iniciada")
                    print("  - X cambió su estructura")
                    print("  - Necesitas estar logueado para ver estas listas")
                    continue
                
                archivo_creado = guardar_resultados(username, datos_usuario, seguidores, seguidos, comentadores)
                
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
                   ▀     ▀    (X ASYNC VERSION)           
    """
    print(banner)

if __name__ == "__main__":
    imprimir_banner()
    asyncio.run(main_x())