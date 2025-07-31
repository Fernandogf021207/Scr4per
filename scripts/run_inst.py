import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from src.utils.logging_config import setup_logging
from src.scrapers.instagram.scraper import scrap_usuarios_instagram

logger = setup_logging()

def imprimir_banner():
    banner = """
 ▗▄▄▖▗▞▀▘ ▄▄▄ ▄  ▗▖▄▄▄▄  ▄▄▄▄  ▗▞▀▚▖ ▄▄▄ 
▐▌   ▝▚▄▖█    █  ▐▌█   █ █   █ ▐▛▀▀▘█    
 ▝▀▚▖    █    ▀▀▀▜▌█▄▄▄▀ █▄▄▄▀ ▝▚▄▄▖█    
▗▄▄▞▘            ▐▌█     █               
                   ▀     ▀    (INSTAGRAM ASYNC VERSION)           
    """
    print(banner)

async def main_instagram():
    try:
        imprimir_banner()
        
        print("📋 Instrucciones:")
        print("1. Asegúrate de tener una sesión iniciada en Instagram")
        print("2. El perfil debe ser público o debes seguir al usuario")
        print("3. Guarda tu sesión ejecutando: await context.storage_state(path='data/storage/instagram_storage_state.json')")
        print("4. Este scraper extraerá seguidores, seguidos y comentarios")
        print()
        
        url = input("Ingresa la URL del perfil de Instagram (ej: https://www.instagram.com/usuario/): ")
        
        respuesta_comentarios = input("¿Extraer comentarios de los posts? (s/n) [s]: ").lower()
        extraer_comentarios = respuesta_comentarios != 'n'
        
        max_posts = 5
        if extraer_comentarios:
            try:
                max_posts = int(input("¿Cuántos posts analizar para comentarios? [5]: ") or "5")
            except ValueError:
                max_posts = 5
        
        archivo_creado = await scrap_usuarios_instagram(url, extraer_comentarios, max_posts)
        
        if archivo_creado:
            print(f"\n🎉 ¡Scraping completado! {archivo_creado}")
        else:
            print("\n❌ El scraping no se completó correctamente")
    
    except KeyboardInterrupt:
        print("\n⚠️ Proceso interrumpido por el usuario")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")

if __name__ == "__main__":
    imprimir_banner()
    asyncio.run(main_instagram())