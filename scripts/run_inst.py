import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from playwright.async_api import async_playwright
from src.utils.logging_config import setup_logging
from src.scrapers.instagram.scraper import (
    obtener_datos_usuario_principal,
    scrap_lista_usuarios
)
from src.utils.output import guardar_resultados

logger = setup_logging()

def mostrar_menu():
    print("\n📋 Menú de Opciones:")
    print("1. Scrapear seguidores")
    print("2. Scrapear seguidos")
    print("3. Scrapear todo")
    print("4. Salir")
    return input("Selecciona una opción (1-4): ")

async def main_instagram():
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    try:
        print("📋 Instrucciones:")
        print("1. Inicia sesión en Instagram en una sesión autenticada")
        print("2. Guarda el estado con: await context.storage_state(path='data/storage/instagram_storage_state.json')")
        print()

        url = input("Ingresa la URL del perfil de Instagram (ej: https://www.instagram.com/usuario/): ")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(storage_state=INSTAGRAM_CONFIG["storage_state_path"])
            page = await context.new_page()

            while True:
                opcion = mostrar_menu()

                if opcion not in ['1', '2', '3', '4']:
                    print("❌ Opcion invalida. Selecciona 1-4")
                    continue

                if opcion == '4':
                    print("👋 Saliendo del programa...")
                    break

                datos_usuario = await obtener_datos_usuario_principal(page, url)
                username = datos_usuario['username']

                seguidores, seguidos = [], []

                if opcion in ['1', '3']:
                    seguidores = await scrap_lista_usuarios(page, url, "seguidores")
                if opcion in ['2', '3']:
                    seguidos = await scrap_lista_usuarios(page, url, "seguidos")

                if not seguidores and not seguidos:
                    print("⚠️ No se encontraron datos. Verifica sesión, privacidad del perfil o estructura de Instagram")
                    continue

                archivo = guardar_resultados(username, datos_usuario, seguidores, seguidos, [], platform='instagram')
                print(f"\n🎉 ¡Scraping completado! {archivo}")

                if input("\n¿Desea realizar otra operacion? (s/n): ").lower() != 's':
                    break

            await browser.close()

    except KeyboardInterrupt:
        print("\n⚠️ Proceso interrumpido por el usuario")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")

def imprimir_banner():
    print("""
 ▗▄▖▗▞▀▘ ▄▄▄ ▄  ▗▖▄▄▄▄  ▄▄▄▄   ▗▞▀▚▖ ▄▄▄ 
▐▌   ▝▚▄▖█    █  ▐▌█   █ █   █ ▐▛▀▀▘█    
 ▝▀▚▖    █    ▀▀▀▜▌█▄▄▄▀ █▄▄▄▀ ▝▚▄▄▖█    
▗▄▄▞▘            ▐▌█     █               
                  ▀     ▀    (INSTAGRAM)
    """)

if __name__ == "__main__":
    imprimir_banner()
    asyncio.run(main_instagram())