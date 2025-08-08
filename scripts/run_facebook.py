import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from playwright.async_api import async_playwright
from src.utils.logging_config import setup_logging
from src.scrapers.facebook.scraper import (
    obtener_datos_usuario_principal,
    scrap_lista_usuarios,
    scrap_comentadores_facebook
)
from src.utils.output import guardar_resultados

logger = setup_logging()

def mostrar_menu():
    print("\n📋 Menú de Opciones:")
    print("1. Scrapear amigos")
    print("2. Scrapear comentadores")
    print("3. Scrapear todo")
    print("4. Salir")
    return input("Selecciona una opción (1-4): ")

async def main_facebook():
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    try:
        print("📋 Instrucciones:")
        print("1. Inicia sesión en Facebook manualmente con una cuenta válida")
        print("2. Guarda tu sesión ejecutando: await context.storage_state(path='data/storage/facebook_storage_state.json')")
        print("3. Se recomienda acceder a perfiles públicos o amigos que permitan la visibilidad")
        print()

        url = input("Ingresa la URL del perfil de Facebook (ej: https://www.facebook.com/usuario): ")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(storage_state=FACEBOOK_CONFIG['storage_state_path'])
            page = await context.new_page()

            while True:
                opcion = mostrar_menu()

                if opcion not in ['1', '2', '3', '4']:
                    print("❌ Opción inválida. Por favor, selecciona una opción válida (1-4).")
                    continue

                if opcion == '4':
                    print("👋 Saliendo del programa...")
                    break

                datos_usuario = await obtener_datos_usuario_principal(page, url)
                username = datos_usuario['username']

                amigos = []
                comentadores = []

                if opcion in ['1', '3']:
                    amigos = await scrap_lista_usuarios(page, url)

                if opcion in ['2', '3']:
                    comentadores = await scrap_comentadores_facebook(page, url)

                if opcion == '1' and not amigos:
                    print("⚠️ No se encontraron amigos. Verifica la sesión o la privacidad del perfil.")
                    continue
                if opcion == '2' and not comentadores:
                    print("⚠️ No se encontraron comentadores. Posibles causas: privacidad, sesión inválida o sin comentarios visibles.")
                    continue
                if opcion == '3' and not amigos and not comentadores:
                    print("⚠️ No se extrajo información. Verifica la sesión, permisos o que el perfil tenga contenido visible.")
                    continue

                archivo_creado = guardar_resultados(username, datos_usuario, amigos, [], comentadores, platform='facebook')
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
                   ▀     ▀    (Facebook VERSION)           
    """
    print(banner)

if __name__ == "__main__":
    imprimir_banner()
    asyncio.run(main_facebook())