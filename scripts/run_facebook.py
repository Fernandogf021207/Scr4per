import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from playwright.async_api import async_playwright
from src.utils.logging_config import setup_logging
from src.scrapers.facebook.scraper import (
    obtener_datos_usuario_principal,
    scrap_lista_usuarios
)
from src.utils.output import guardar_resultados

logger = setup_logging()

def mostrar_menu():
    print("\n📋 Menú de Opciones:")
    print("1. Scrapear amigos")
    print("2. Salir")
    return input("Selecciona una opción (1-2): ")

async def main_facebook():
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    try:
        print("📋 Instrucciones:")
        print("1. Inicia sesión en Facebook en una sesión autenticada")
        print("2. Guarda el estado con: await context.storage_state(path='data/storage/facebook_storage_state.json')")
        print()

        url = input("Ingresa la URL del perfil de Facebook (ej: https://www.facebook.com/usuario): ")
        if not url.endswith('/friends'):
            url_amigos = url.rstrip('/') + '/friends'
        else:
            url_amigos = url

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(storage_state=FACEBOOK_CONFIG["storage_state_path"])
            page = await context.new_page()

            while True:
                opcion = mostrar_menu()
                if opcion == '2':
                    print("👋 Saliendo del programa...")
                    break
                elif opcion == '1':
                    datos_usuario = await obtener_datos_usuario_principal(page, url)
                    amigos = await scrap_lista_usuarios(page, url_amigos)
                    if not amigos:
                        print("⚠️ No se encontraron amigos. Verifica la sesión o la privacidad del perfil.")
                        continue
                    archivo = guardar_resultados(datos_usuario['username'], datos_usuario, amigos, [], [], platform='facebook')
                    print(f"\n🎉 ¡Scraping completado! {archivo}")
                    if input("\n¿Desea realizar otra operación? (s/n): ").lower() != 's':
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
                  ▀     ▀    (FACEBOOK)
    """)

if __name__ == "__main__":
    imprimir_banner()
    asyncio.run(main_facebook())