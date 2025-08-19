import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from playwright.async_api import async_playwright
from src.utils.logging_config import setup_logging
from src.scrapers.facebook.scraper import (
	obtener_datos_usuario_facebook,
	scrap_friends_all,
	scrap_followers,
	scrap_followed,
	scrap_reacciones_fotos,
	scrap_comentarios_fotos,
)
from src.scrapers.facebook.config import FACEBOOK_CONFIG
from src.utils.output import guardar_resultados

logger = setup_logging()


def mostrar_menu():
	print("\n📋 Menú de Opciones (Facebook):")
	print("1. Scrapear amigos (/friends_all)")
	print("2. Scrapear seguidores (/followers)")
	print("3. Scrapear seguidos (/followed)")
	print("4. Scrapear todo")
	print("5. Scrapear reacciones en fotos")
	print("6. Scrapear comentarios en fotos")
	print("7. Salir")
	return input("Selecciona una opción (1-7): ")


async def main_facebook():
	try:
		print("📋 Instrucciones:")
		print("1. Debes tener la sesión iniciada en Facebook en tu storage state")
		print("2. Guarda tu sesión ejecutando: await context.storage_state(path='data/storage/facebook_storage_state.json')")
		print("3. Este scraper navega a /friends_all, /followers y /following")
		print()

		url = input("Ingresa la URL del perfil de Facebook (ej: https://www.facebook.com/usuario): ")

		async with async_playwright() as p:
			browser = await p.chromium.launch(headless=False)
			context = await browser.new_context(storage_state=FACEBOOK_CONFIG["storage_state_path"])
			page = await context.new_page()

			while True:
				opcion = mostrar_menu()
				if opcion not in ['1', '2', '3', '4', '5', '6', '7']:
					print("❌ Opción inválida. Por favor, selecciona una opción válida (1-7).")
					continue
				if opcion == '7':
					print("👋 Saliendo del programa...")
					break

				datos_usuario = await obtener_datos_usuario_facebook(page, url)
				username = datos_usuario['username']

				amigos = []
				seguidores = []
				seguidos = []
				reacciones = []
				comentarios_foto = []

				if opcion in ['1', '4']:
					print("\n🔍 Scrapeando amigos (/friends_all)...")
					amigos = await scrap_friends_all(page, url, username)

				if opcion in ['2', '4']:
					print("\n🔍 Scrapeando seguidores (/followers)...")
					seguidores = await scrap_followers(page, url, username)

				if opcion in ['3', '4']:
					print("\n🔍 Scrapeando seguidos (/followed)...")
					seguidos = await scrap_followed(page, url, username)

				if opcion == '5':
					print("\n📸 Reacciones en fotos")
					try:
						max_fotos = int(input("¿Cuántas fotos analizar? [5]: ") or "5")
					except ValueError:
						max_fotos = 5
					incluir_comentarios = (input("¿Incluir reacciones en comentarios? (s/n) [n]: ").strip().lower() == 's')
					reacciones = await scrap_reacciones_fotos(page, url, username, max_fotos=max_fotos, incluir_comentarios=incluir_comentarios)

				if opcion == '6':
					print("\n💬 Comentarios en fotos")
					try:
						max_fotos = int(input("¿Cuántas fotos analizar? [5]: ") or "5")
					except ValueError:
						max_fotos = 5
					comentarios_foto = await scrap_comentarios_fotos(page, url, username, max_fotos=max_fotos)

				total = len(amigos) + len(seguidores) + len(seguidos) + len(reacciones) + len(comentarios_foto)
				if total == 0:
					print("⚠️ No se encontraron usuarios. Posibles causas:")
					print("  - El perfil es privado o restringido")
					print("  - No hay sesión iniciada correctamente")
					print("  - Facebook cambió su estructura")
					continue

				# Reutilizamos 'comentadores' para almacenar reacciones (estructura similar con post_url -> photo_url)
				archivo_creado = guardar_resultados(
					username,
					datos_usuario,
					seguidores,
					seguidos,
					comentadores=(reacciones or []) + (comentarios_foto or []),
					platform='facebook',
					amigos=amigos,
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
				   ▀     ▀    (FACEBOOK VERSION)           
	"""
	print(banner)


if __name__ == "__main__":
	imprimir_banner()
	asyncio.run(main_facebook())

