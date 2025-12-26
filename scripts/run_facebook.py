import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import argparse
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


def parse_args():
	parser = argparse.ArgumentParser(description="Run Facebook scraper interactively")
	parser.add_argument("--url", help="Perfil objetivo de Facebook (https://www.facebook.com/<username>)", default=None)
	parser.add_argument("--headless", help="Ejecutar navegador en modo headless (true/false)", default="false")
	parser.add_argument("--storage-state", dest="storage_state", help="Ruta al storage_state.json de Facebook", default=None)
	parser.add_argument("--slow-mo", dest="slow_mo", help="Retardo en ms entre acciones del navegador (para depurar)", type=int, default=0)
	return parser.parse_args()


def mostrar_menu():
	print("\n📋 Menú de Opciones (Facebook):")
	print("1. Scrapear amigos, seguidores y seguidos")
	print("2. Scrapear fotos (comentarios y reacciones)")
	print("3. Scrapear todo")
	print("4. Salir")
	return input("Selecciona una opción (1-4): ")


async def main_facebook():
	args = parse_args()
	try:
		print("📋 Instrucciones:")
		print("1. Debes tener la sesión iniciada en Facebook en tu storage state")
		print("2. Guarda tu sesión ejecutando: await context.storage_state(path='data/storage/facebook_storage_state.json')")
		print("3. Este scraper navega a /friends_all, /followers y /following")
		print()

		url = args.url or input("Ingresa la URL del perfil de Facebook (ej: https://www.facebook.com/usuario): ")

		# Determinar headless
		headless_flag = str(args.headless).strip().lower() in ["1", "true", "yes", "y"]

		# Determinar storage state
		storage_state_path = (
			args.storage_state
			or os.environ.get("FACEBOOK_STORAGE_STATE")
			or FACEBOOK_CONFIG.get("storage_state_path")
		)

		if not storage_state_path or not os.path.exists(storage_state_path):
			print(f"❌ storage_state no encontrado: {storage_state_path or '(no especificado)'}")
			print("   Configura --storage-state o la variable FACEBOOK_STORAGE_STATE, o revisa FACEBOOK_CONFIG.")
			return

		async with async_playwright() as p:
			browser = await p.chromium.launch(headless=headless_flag, slow_mo=args.slow_mo)
			context = await browser.new_context(storage_state=storage_state_path)
			page = await context.new_page()

			# Comprobación rápida de sesión válida
			try:
				await page.goto("https://www.facebook.com/")
				await page.wait_for_timeout(1500)
				redirected = "login" in page.url.lower()
				login_selector = await page.query_selector("input[name='email']")
				if redirected or login_selector:
					print("⚠️ La sesión de Facebook no está activa. Actualiza el storage_state e inténtalo de nuevo.")
					await browser.close()
					return
			except Exception:
				# Si falla, continuamos; el flujo de listas volverá a fallar y mostrará pistas
				pass

			while True:
				opcion = mostrar_menu()
				if opcion not in ['1', '2', '3', '4']:
					print("❌ Opción inválida. Por favor, selecciona una opción válida (1-4).")
					continue
				if opcion == '4':
					print("👋 Saliendo del programa...")
					break

				datos_usuario = await obtener_datos_usuario_facebook(page, url)
				username = datos_usuario['username']

				amigos = []
				seguidores = []
				seguidos = []
				reacciones = []
				comentarios_foto = []

				# Opción 1: Listas (amigos, seguidores, seguidos) y también en 'todo'
				if opcion in ['1', '3']:
					print("\n🔍 Scrapeando amigos (/friends_all)...")
					amigos = await scrap_friends_all(page, url, username)
					print("\n🔍 Scrapeando seguidores (/followers)...")
					seguidores = await scrap_followers(page, url, username)
					print("\n🔍 Scrapeando seguidos (/followed)...")
					seguidos = await scrap_followed(page, url, username)

				# Opción 2: Scrapear fotos (comentarios primero, luego reacciones) y también en 'todo'
				if opcion in ['2', '3']:
					print("\n📸 Scrapear fotos (comentarios y reacciones)")
					try:
						max_fotos = int(input("¿Cuántas fotos analizar? [5]: ") or "5")
					except ValueError:
						max_fotos = 5
					# Primero comentarios
					print("\n💬 Comentarios en fotos")
					comentarios_foto = await scrap_comentarios_fotos(page, url, username, max_fotos=max_fotos)
					# Luego reacciones (incluyendo reacciones en comentarios SIEMPRE)
					print("\n� Reacciones en fotos (incluyendo reacciones en comentarios)")
					reacciones = await scrap_reacciones_fotos(page, url, username, max_fotos=max_fotos, incluir_comentarios=True)

				total = len(amigos) + len(seguidores) + len(seguidos) + len(reacciones) + len(comentarios_foto)
				if total == 0:
					print("⚠️ No se encontraron usuarios. Posibles causas:")
					print("  - El perfil es privado o restringido")
					print("  - No hay sesión iniciada correctamente")
					print("  - Facebook cambió su estructura")
					print("  - Selectores desactualizados o barreras de UI (cookies/captcha)")
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

