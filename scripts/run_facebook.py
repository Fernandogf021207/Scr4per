import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from playwright.async_api import async_playwright
from src.utils.logging_config import setup_logging
from src.scrapers.facebook.scraper import (
    obtener_datos_usuario_principal,
    scrap_amigos,
    scrap_seguidores,
    scrap_seguidos,
    scrap_comentadores_facebook,
    scrap_lista_usuarios  # Para compatibilidad
)
from src.utils.output import guardar_resultados

logger = setup_logging()

def mostrar_menu():
    print("\n📋 Menú de Opciones:")
    print("1. Scrapear amigos")
    print("2. Scrapear seguidores")
    print("3. Scrapear seguidos")
    print("4. Scrapear comentadores")
    print("5. Scrapear todo (amigos, seguidores, seguidos y comentadores)")
    print("6. Salir")
    return input("Selecciona una opción (1-6): ")

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

                if opcion not in ['1', '2', '3', '4', '5', '6']:
                    print("❌ Opción inválida. Por favor, selecciona una opción válida (1-6).")
                    continue

                if opcion == '6':
                    print("👋 Saliendo del programa...")
                    break

                datos_usuario = await obtener_datos_usuario_principal(page, url)
                username = datos_usuario['username']

                amigos = []
                seguidores = []
                seguidos = []
                comentadores = []

                if opcion in ['1', '5']:  # Scrapear amigos
                    print("\n🔍 Scrapeando amigos...")
                    amigos = await scrap_amigos(page, url)

                if opcion in ['2', '5']:  # Scrapear seguidores
                    print("\n🔍 Scrapeando seguidores...")
                    seguidores = await scrap_seguidores(page, url)

                if opcion in ['3', '5']:  # Scrapear seguidos
                    print("\n🔍 Scrapeando seguidos...")
                    seguidos = await scrap_seguidos(page, url)

                if opcion in ['4', '5']:  # Scrapear comentadores
                    print("\n🔍 Scrapeando comentadores...")
                    comentadores = await scrap_comentadores_facebook(page, url)

                # Verificar si se encontraron datos
                total_usuarios = len(amigos) + len(seguidores) + len(seguidos) + len(comentadores)
                
                if total_usuarios == 0:
                    print("⚠️ No se encontraron usuarios. Posibles causas:")
                    print("  - Perfil privado o restringido")
                    print("  - Sesión no autenticada correctamente")
                    print("  - Configuración de privacidad del usuario")
                    print("  - Facebook ha cambiado su estructura")
                    continue

                # Mostrar resumen
                print(f"\n📊 Resumen de datos extraídos:")
                if amigos:
                    print(f"  👥 Amigos: {len(amigos)}")
                if seguidores:
                    print(f"  👥 Seguidores: {len(seguidores)}")
                if seguidos:
                    print(f"  👥 Seguidos: {len(seguidos)}")
                if comentadores:
                    print(f"  💬 Comentadores: {len(comentadores)}")

                # Guardar resultados - para Facebook, los amigos pueden ir en seguidores o crear una categoría especial
                todos_usuarios = []
                
                # Combinar todos los usuarios con etiquetas de tipo
                for amigo in amigos:
                    amigo_copia = amigo.copy()
                    amigo_copia['tipo_relacion'] = 'amigo'
                    todos_usuarios.append(amigo_copia)
                
                for seguidor in seguidores:
                    seguidor_copia = seguidor.copy()
                    seguidor_copia['tipo_relacion'] = 'seguidor'
                    todos_usuarios.append(seguidor_copia)
                
                for seguido in seguidos:
                    seguido_copia = seguido.copy()
                    seguido_copia['tipo_relacion'] = 'seguido'
                    todos_usuarios.append(seguido_copia)
                
                # Guardar usando la función estándar
                archivo_creado = guardar_resultados(
                    username, 
                    datos_usuario, 
                    todos_usuarios,  # Todos los usuarios en la categoría de seguidores
                    [],              # Seguidos vacío para evitar duplicados
                    comentadores if comentadores else [],
                    platform='facebook'
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
                   ▀     ▀    (Facebook VERSION)           
    """
    print(banner)

if __name__ == "__main__":
    imprimir_banner()
    asyncio.run(main_facebook())