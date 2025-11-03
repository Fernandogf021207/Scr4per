import asyncio
import logging
from typing import Dict, List

from src.scrapers.facebook.config import FACEBOOK_CONFIG
from src.scrapers.facebook.utils import normalize_profile_url, get_text, get_attr, absolute_url_keep_query
from src.utils.dom import find_scroll_container, scroll_collect
from src.utils.list_parser import build_user_item
from src.utils.common import limpiar_url
from src.utils.url import normalize_input_url, normalize_post_url

logger = logging.getLogger(__name__)


# ---------- Perfil principal ----------
async def obtener_datos_usuario_facebook(page, perfil_url: str) -> dict:
	"""Obtiene nombre, username (slug o id) y foto del perfil principal."""
	perfil_url = normalize_input_url('facebook', perfil_url)
	await page.goto(perfil_url)
	await page.wait_for_timeout(3000)

	# Intentar obtener nombre
	nombre = None
	selectores_nombre = [
		'h1 span',
		'div[data-pagelet="ProfileTilesFeed_0"] h1 span',
		'div[role="main"] h1',
		'h2[dir="auto"]',
	]
	for sel in selectores_nombre:
		el = await page.query_selector(sel)
		if el:
			nombre = await get_text(el)
			if nombre:
				break

	# Username a partir de la URL
	current = page.url
	cleaned = limpiar_url(current)
	username = cleaned.split('facebook.com/')[-1].strip('/')
	if '?' in username:
		username = username.split('?')[0]

	# Intentar obtener foto
	foto = None
	foto_selectores = [
		'image[height][width]',
		'image[aria-label*="profile"][xlink\:href]',
		'img[alt*="profile"], img[src*="scontent"]',
		'image', 'img'
	]
	for fs in foto_selectores:
		try:
			el = await page.query_selector(fs)
			if el:
				src = await get_attr(el, 'xlink:href') or await get_attr(el, 'src')
				if src and not src.startswith('data:'):
					foto = src
					break
		except Exception:
			continue

	return {
		'username': username or 'unknown',
		'nombre_completo': nombre or username or 'unknown',
		'foto_perfil': foto or '',
		'url_usuario': cleaned or perfil_url,
	}


# ---------- Navegación a listas ----------
async def navegar_a_lista(page, perfil_url: str, lista: str) -> bool:
	"""Navega a /friends_all, /followers o /followed según lista."""
	suffix = {
		'friends_all': 'friends_all',
		'followers': 'followers',
		'followed': 'following',  # Facebook usa /following para las páginas/people seguidas
	}.get(lista, lista)

	# Normalizar URL base del perfil
	perfil_url = normalize_input_url('facebook', perfil_url)
	base = perfil_url.rstrip('/')
	target = f"{base}/{suffix}/"
	try:
		await page.goto(target)
		await page.wait_for_timeout(3000)
		return True
	except Exception as e:
		logger.error(f"No se pudo navegar a {lista}: {e}")
		return False


# ---------- Extracción genérica de usuarios en listados ----------
async def extraer_usuarios_listado(page, tipo_lista: str, usuario_principal: str) -> List[dict]:
	"""Hace scroll y extrae tarjetas de usuarios en un listado (friends/followers/followed).
	Optimizado: extracción en lote por evaluate, espera adaptativa corta, y procesar-solo-nuevos.
	"""
	usuarios: Dict[str, dict] = {}

	cfg = FACEBOOK_CONFIG.get('scroll', {})
	max_scrolls = int(cfg.get('max_scrolls', 60))
	pause_ms = int(cfg.get('pause_ms', 1500))
	max_no_new = int(cfg.get('max_no_new', 6))

	async def _extract_visible_batch(page_) -> List[dict]:
		js = '''
		() => {
		  const root = document.querySelector('div[role="main"]') || document;
		  const anchors = Array.from(root.querySelectorAll('a[href^="/"]'));
		  const out = [];
		  for (const a of anchors) {
			const href = a.getAttribute('href') || '';
			// excluir rutas obvias no-perfil y estados
			if (!href || href.includes('/status/') || href.includes('/groups/') || href.includes('/events/')) continue;
			const text = (a.textContent || '').trim();
			let img = '';
			const cont = a.closest('div');
			const imgel = cont ? (cont.querySelector('img, image') || a.querySelector('img, image')) : a.querySelector('img, image');
			if (imgel) {
			  img = imgel.currentSrc || imgel.src || imgel.getAttribute('xlink:href') || '';
			}
			out.push({ href, text, img });
		  }
		  return out;
		}
		'''
		try:
			data = await page_.evaluate(js)
			return data or []
		except Exception:
			return []

	async def process_cb(page_, _container) -> int:
		from time import perf_counter
		t0 = perf_counter()
		before = len(usuarios)
		raw = await _extract_visible_batch(page_)
		# Mapear y filtrar sólo nuevos
		invalid_paths = [
			'photo', 'groups', 'events', 'pages', 'watch', 'marketplace', 'reel',
			'reviews_given', 'reviews_written', 'video_movies_watch', 'profile_songs',
			'places_recent', 'posts/'
		]
		for rec in raw:
			try:
				href = rec.get('href') or ''
				if not href:
					continue
				url = normalize_profile_url(href)
				if not url:
					continue
				if any(f"/{pat}" in url for pat in invalid_paths):
					continue
				slug = url.split('facebook.com/')[-1].strip('/')
				if slug in ('', 'friends', 'followers', 'following'):
					continue
				if slug == usuario_principal:
					continue
				if url in usuarios:
					continue
				nombre = (rec.get('text') or '').strip() or slug.split('?')[0]
				foto = rec.get('img') or ''
				usuarios[url] = build_user_item('facebook', url, nombre, foto)
			except Exception:
				continue
		added = len(usuarios) - before
		ms = int((perf_counter() - t0) * 1000)
		logger.info("fb.list.cycle tipo=%s added=%d total=%d ms=%d", tipo_lista, added, len(usuarios), ms)
		# Espera adaptativa corta entre ciclos para permitir render
		try:
			await page_.wait_for_timeout(400)
		except Exception:
			pass
		return added

	await scroll_collect(
		page,
		process_cb,
		container=None,  # listado usa scroll de ventana
		max_scrolls=max_scrolls,
		pause_ms=pause_ms,
		no_new_threshold=max_no_new,
		bottom_margin=800,
		pause_every=10,
		pause_every_ms=1500,
	)
	return list(usuarios.values())


async def procesar_tarjetas_usuario(page, usuarios: Dict[str, dict], usuario_principal: str):
	"""Intenta identificar tarjetas/enlaces de perfiles y agregarlos al diccionario."""
	# Varias heurísticas, Facebook cambia mucho
	selectores = [
		# Enlaces de perfil dentro de tarjetas
		'div[role="main"] a[href^="/profile.php?id="]',
		'div[role="main"] a[href^="/"][href*="?sk="]',
		'div[role="main"] a[href^="/"]:not([href*="photo"])',
		# Contenedores ricos
		'div[role="main"] div:has(a[href^="/profile.php"], a[href^="/"])',
	]

	for sel in selectores:
		try:
			links = await page.query_selector_all(sel)
		except Exception:
			links = []

		for a in links:
			try:
				href = await get_attr(a, 'href')
				if not href:
					continue

				url = normalize_profile_url(href)
				if not url:
					continue

				# Filtrar no-perfiles comunes
				invalid_paths = [
					'photo', 'groups', 'events', 'pages', 'watch', 'marketplace', 'reel',
					'reviews_given', 'reviews_written', 'video_movies_watch', 'profile_songs',
					'places_recent', 'posts/'
				]
				if any(f"/{pat}" in url for pat in invalid_paths):
					continue

				# Username/id
				slug = url.split('facebook.com/')[-1].strip('/')
				if slug in ('', 'friends', 'followers', 'following'):
					continue

				if slug == usuario_principal:
					continue

				if url in usuarios:
					continue

				# Intentar encontrar nombre visible asociado al enlace
				nombre = await get_text(a)
				if not nombre:
					try:
						cont = await a.evaluate_handle('el => el.closest("div")')
						nombre_el = await cont.query_selector('span, strong, h2, h3') if cont else None
						nombre = await get_text(nombre_el)
					except Exception:
						nombre = None

				# Foto de perfil cercana
				foto = ''
				try:
					cont = await a.evaluate_handle('el => el.closest("div")')
					img = await cont.query_selector('img, image') if cont else None
					src = await get_attr(img, 'src') or await get_attr(img, 'xlink:href')
					if src and not src.startswith('data:'):
						foto = src
				except Exception:
					pass

				# Nombre de usuario ideal (cuando no es profile.php)
				username = slug.split('?')[0]
				if 'profile.php' in username:
					# mantener id como username
					pass

				usuarios[url] = build_user_item('facebook', url, nombre or username, foto or '')
			except Exception:
				continue


# ---------- API públicas ----------
async def scrap_friends_all(page, perfil_url: str, username: str) -> List[dict]:
	if not await navegar_a_lista(page, perfil_url, 'friends_all'):
		return []
	# Preferir extractor específico basado en estructura aportada
	return await extraer_amigos_facebook(page, username)


async def scrap_followers(page, perfil_url: str, username: str) -> List[dict]:
	if not await navegar_a_lista(page, perfil_url, 'followers'):
		return []
	return await extraer_usuarios_listado(page, 'followers', username)


async def scrap_followed(page, perfil_url: str, username: str) -> List[dict]:
	if not await navegar_a_lista(page, perfil_url, 'followed'):
		return []
	return await extraer_usuarios_listado(page, 'followed', username)


# Alias similar a Instagram
async def scrap_lista_facebook(page, perfil_url: str, tipo: str) -> List[dict]:
	datos = await obtener_datos_usuario_facebook(page, perfil_url)
	username = datos.get('username', '')
	if tipo == 'friends_all':
		return await scrap_friends_all(page, perfil_url, username)
	if tipo == 'followers':
		return await scrap_followers(page, perfil_url, username)
	if tipo == 'followed':
		return await scrap_followed(page, perfil_url, username)
	return []


# ---------- Extractor específico de amigos (/friends_all) ----------
async def extraer_amigos_facebook(page, usuario_principal: str) -> List[dict]:
	"""Extrae amigos usando la estructura probada del archivo adjunto (async)."""
	# Scroll fuerte con rueda del mouse como en la versión sync
	try:
		for i in range(50):
			try:
				await page.mouse.wheel(0, 3000)
			except Exception:
				# Fallback a window.scrollBy si wheel falla
				try:
					await page.evaluate("window.scrollBy(0, 3000)")
				except Exception:
					pass
			await asyncio.sleep(2)
	except Exception:
		pass

	amigos_dict: Dict[str, dict] = {}

	tarjetas = []
	try:
		tarjetas = await page.query_selector_all('div[role="main"] div:has(a[tabindex="0"])')
	except Exception:
		tarjetas = []

	invalid_segments = [
		"/followers", "/following", "/friends", "/videos", "/photo", "/photos",
		"/tv", "/events", "/past_events", "/likes", "/likes_all",
		"/music", "/sports", "/map", "/movies", "/pages",
		"/groups", "/watch", "/reel", "/story", "/video_tv_shows_watch",
		"/games", "/reviews_given", "/reviews_written", "/video_movies_watch",
		"/profile_songs", "/places_recent", "/posts/"
	]

	for tarjeta in tarjetas:
		try:
			a_nombre = await tarjeta.query_selector('a[tabindex="0"]')
			a_img = await tarjeta.query_selector('a[tabindex="-1"] img')

			nombre = (await get_text(a_nombre)) or "Sin nombre"
			perfil = await get_attr(a_nombre, "href") if a_nombre else None
			imagen = await get_attr(a_img, "src") if a_img else None

			if not perfil:
				continue

			perfil_limpio = normalize_profile_url(perfil)

			# Filtrado similar a la versión de referencia
			low = (nombre or "").lower().strip()
			if low.startswith(("1 amigo", "2 amigos", "3 amigos")):
				continue
			if any(seg in perfil_limpio for seg in invalid_segments):
				continue

			# Evitar self
			slug = perfil_limpio.split('facebook.com/')[-1].strip('/')
			if slug == usuario_principal:
				continue

			if perfil_limpio in amigos_dict:
				continue

			username = slug.split('?')[0]
			amigos_dict[perfil_limpio] = build_user_item('facebook', perfil_limpio, nombre, imagen or '')
		except Exception:
			continue

	return list(amigos_dict.values())


# ---------- Reacciones en fotos ----------
async def navegar_a_fotos(page, perfil_url: str) -> bool:
	"""Intentar varios sufijos comunes de fotos en perfiles."""
	candidates = ["photos_by", "photos", "photos_all"]
	perfil_url = normalize_input_url('facebook', perfil_url)
	base = perfil_url.rstrip('/')
	for suf in candidates:
		try:
			await page.goto(f"{base}/{suf}/")
			await page.wait_for_timeout(2500)
			# Heurística mínima: verificar si hay imágenes/enlaces a photo.php
			has_photos = await page.query_selector('a[href*="photo.php"], a[href*="/photos/"] img, img[src*="scontent"]')
			if has_photos:
				return True
		except Exception:
			continue
	return False


async def extraer_urls_fotos(page, max_fotos: int = 5) -> List[str]:
	urls: List[str] = []
	seen = set()
	scrolls = 0
	while len(urls) < max_fotos and scrolls < 20:
		try:
			# Capturar enlaces a fotos
			selectores = [
				'a[href*="photo.php"]',
				'a[href*="/photos/"]',
			]
			for sel in selectores:
				try:
					anchors = await page.query_selector_all(sel)
				except Exception:
					anchors = []
				for a in anchors:
					href = await get_attr(a, 'href')
					if not href:
						continue
					# Mantener query para fbid y otros parámetros clave
					full = absolute_url_keep_query(href)
					if full in seen:
						continue
					seen.add(full)
					urls.append(full)
					if len(urls) >= max_fotos:
						break
				if len(urls) >= max_fotos:
					break
			if len(urls) >= max_fotos:
				break
			# Scroll
			await page.evaluate("window.scrollBy(0, window.innerHeight * 0.9)")
			await page.wait_for_timeout(1200)
			scrolls += 1
		except Exception:
			break
	return urls[:max_fotos]


async def procesar_usuarios_en_modal_reacciones(page, reacciones_dict: Dict[str, dict], photo_url: str):
	"""Procesa el modal de reacciones (usuarios que reaccionaron)."""
	try:
		container = await find_scroll_container(page)

		async def process_cb(page_, _container) -> int:
			before = len(reacciones_dict)
			selectores = [
				'div[role="dialog"] a[href^="/"][role="link"]',
				'div[role="dialog"] a[role="link"]',
			]
			enlaces = []
			for sel in selectores:
				try:
					enlaces = await page_.query_selector_all(sel)
				except Exception:
					enlaces = []
				if enlaces:
					break
			for e in enlaces:
				try:
					href = await get_attr(e, 'href')
					if not href:
						continue
					url = normalize_profile_url(href)
					if any(x in url for x in ["/groups/", "/pages/", "/events/"]):
						continue
					username = url.split('facebook.com/')[-1].strip('/')
					if username in ("", "photo.php"):
						continue
					if url in reacciones_dict:
						continue
					nombre = await get_text(e)
					foto = ''
					try:
						cont = await e.evaluate_handle('el => el.closest("div")')
						img = await cont.query_selector('img, image') if cont else None
						src = await get_attr(img, 'src') or await get_attr(img, 'xlink:href')
						if src and not src.startswith('data:'):
							foto = src
					except Exception:
						pass
					item = build_user_item('facebook', url, nombre or username, foto or '')
					item['post_url'] = normalize_post_url('facebook', photo_url)
					reacciones_dict[url] = item
				except Exception:
					continue
			return len(reacciones_dict) - before

		await scroll_collect(
			page,
			process_cb,
			container=container,
			max_scrolls=50,
			pause_ms=900,
			no_new_threshold=6,
		)
	except Exception:
		return


async def abrir_y_scrapear_modal_reacciones(page, reacciones_dict: Dict[str, dict], photo_url: str):
	"""Abre el modal de reacciones de la foto y extrae usuarios."""
	botones = [
		'div[role="button"]:has-text("Ver quién reaccionó")',  # Español
		'div[role="button"]:has-text("See who reacted")',      # Inglés
		'a[role="button"]:has-text("reaccion")',
		'div[role="button"][aria-label*="reaccion"]',
		'div[role="button"][aria-label*="react"]',
	]
	for sel in botones:
		try:
			btn = await page.query_selector(sel)
			if btn:
				await btn.click()
				await page.wait_for_timeout(1500)
				await procesar_usuarios_en_modal_reacciones(page, reacciones_dict, photo_url)
				# Cerrar modal
				try:
					close_btn = await page.query_selector('div[role="dialog"] [aria-label*="Cerrar"], div[role="dialog"] [aria-label*="Close"]')
					if close_btn:
						await close_btn.click()
						await page.wait_for_timeout(500)
				except Exception:
					pass
				return True
		except Exception:
			continue
	return False


async def abrir_y_scrapear_reacciones_en_comentarios(page, reacciones_dict: Dict[str, dict], photo_url: str):
	"""Opcional: abre modales de reacciones dentro de comentarios y extrae usuarios."""
	try:
		# Posibles botones de reacciones en comentarios
		botones_sel = [
			'div[role="button"]:has-text("reacciones")',
			'div[role="button"][aria-label*="reacciones"]',
			'div[role="button"][aria-label*="reactions"]',
			'a[role="button"][aria-label*="reac"]',
		]
		vistos = set()
		for sel in botones_sel:
			try:
				botones = await page.query_selector_all(sel)
			except Exception:
				botones = []
			for b in botones:
				try:
					key = await b.inner_text() or await get_attr(b, 'aria-label') or ''
					if key in vistos:
						continue
					vistos.add(key)
					await b.click()
					await page.wait_for_timeout(1200)
					await procesar_usuarios_en_modal_reacciones(page, reacciones_dict, photo_url)
					# Cerrar modal
					try:
						close_btn = await page.query_selector('div[role="dialog"] [aria-label*="Cerrar"], div[role="dialog"] [aria-label*="Close"]')
						if close_btn:
							await close_btn.click()
							await page.wait_for_timeout(400)
					except Exception:
						pass
				except Exception:
					continue
	except Exception:
		return


async def scrap_reacciones_fotos(page, perfil_url: str, username: str, max_fotos: int = 5, incluir_comentarios: bool = False) -> List[dict]:
	if not await navegar_a_fotos(page, perfil_url):
		return []

	urls = await extraer_urls_fotos(page, max_fotos=max_fotos)
	reacciones: Dict[str, dict] = {}

	for i, photo_url in enumerate(urls, 1):
		try:
			await page.goto(photo_url)
			await page.wait_for_timeout(2500)
			# Abrir reacciones de la foto
			await abrir_y_scrapear_modal_reacciones(page, reacciones, photo_url)
			# Opcional: reacciones en comentarios
			if incluir_comentarios:
				await abrir_y_scrapear_reacciones_en_comentarios(page, reacciones, photo_url)
			# Pausas para rate limiting
			if i % 3 == 0:
				await asyncio.sleep(2)
		except Exception:
			continue
	return list(reacciones.values())


# ---------- Comentarios en fotos ----------
async def procesar_comentarios_en_modal_foto(page, comentarios_dict: Dict[str, dict], photo_url: str):
	"""Busca perfiles de personas en la sección de comentarios del modal de fotos."""
	try:
		# 1) Ubicar bloques de comentario (role=article) dentro o fuera del dialog
		selectores_articulo = [
			'div[role="dialog"] [role="article"][aria-label^="Comentario"]',
			'div[role="dialog"] [role="article"]',
			'[role="article"][aria-label^="Comentario"]',
			'[role="article"]',
		]
		articulos = []
		for s in selectores_articulo:
			try:
				articulos = await page.query_selector_all(s)
			except Exception:
				articulos = []
			if articulos:
				break

		if not articulos:
			return

		for art in articulos:
			try:
				# Dentro del artículo, priorizar el ancla visible con el nombre del usuario
				candidatos = []
				for sel in [
					'a[role="link"][aria-hidden="false"]',
					'a[role="link"]',
					'a[href^="https://www.facebook.com/"]',
					'a[href^="/"]',
				]:
					try:
						cand = await art.query_selector_all(sel)
					except Exception:
						cand = []
					if cand:
						candidatos.extend(cand)

				elegido = None
				for e in candidatos:
					try:
						href = await get_attr(e, 'href')
						if not href:
							continue
						# Saltar anchors de timestamp que apuntan a la foto con comment_id
						if ('/photo/?' in href) or ('/photo.php' in href and 'fbid=' in href and 'comment_id' in href):
							continue
						# Normalizar a perfil
						url = normalize_profile_url(href)
						if not url or 'facebook.com' not in url:
							continue
						if any(x in url for x in ["/groups/", "/pages/", "/events/"]):
							continue
						username = url.split('facebook.com/')[-1].strip('/')
						if username in ("", "photo.php"):
							continue
						elegido = (e, url, username)
						break
					except Exception:
						continue

				if not elegido:
					continue

				e, url, username = elegido
				if url in comentarios_dict:
					continue

				nombre = await get_text(e)
				foto = ''
				try:
					cont = await e.evaluate_handle('el => el.closest("div")')
					img = await cont.query_selector('img, image') if cont else None
					src = await get_attr(img, 'src') or await get_attr(img, 'xlink:href')
					if src and not src.startswith('data:'):
						foto = src
				except Exception:
					pass

				item = build_user_item('facebook', url, nombre or username, foto or '')
				item['post_url'] = normalize_post_url('facebook', photo_url)
				comentarios_dict[url] = item
			except Exception:
				continue
	except Exception:
		return


async def scrap_comentarios_fotos(page, perfil_url: str, username: str, max_fotos: int = 5) -> List[dict]:
	if not await navegar_a_fotos(page, perfil_url):
		return []
	urls = await extraer_urls_fotos(page, max_fotos=max_fotos)
	comentarios: Dict[str, dict] = {}
	for i, photo_url in enumerate(urls, 1):
		try:
			await page.goto(photo_url)
			await page.wait_for_timeout(2000)
			# Scroll del modal/página para cargar comentarios
			for s in range(15):
				try:
					# Click 'Ver más comentarios' si existe
					botones = [
						'div[role="button"]:has-text("Ver más comentarios")',
						'div[role="button"]:has-text("View more comments")',
						'div[role="button"]:has-text("Cargar más comentarios")',
						'div[role="button"][aria-label*="comentarios"]',
						# Fallback: buscar el span y ascender al botón
						'span:has-text("Ver más comentarios")',
						'span:has-text("Mostrar más comentarios")',
						'span:has-text("View more comments")',
						'div[role="button"]:has-text("Ver más")',
						'div[role="button"]:has-text("Mostrar más")',
						'div[role="button"]:has-text("Ver respuestas")',
						'div[role="button"]:has-text("Mostrar respuestas")',
					]
					clicked = False
					for bsel in botones:
						b = await page.query_selector(bsel)
						if b:
							# Si es el span, subir al contenedor con role=button
							try:
								role_btn = await b.evaluate_handle('el => el.closest("[role=\\"button\\"]") || el')
								await role_btn.click()
							except Exception:
								await b.click()
							await page.wait_for_timeout(900)
							clicked = True
							break
				except Exception:
					pass
				# Scroll en el contenedor del modal si existe, si no en la página
				try:
					await page.evaluate("""
						() => {
							const modal = document.querySelector('div[role="dialog"]');
							let el = modal;
							if (modal) {
								// buscar el contenedor scrolleable más grande dentro del modal
								let best = modal;
								const nodes = modal.querySelectorAll('div, section, main, article');
								nodes.forEach(n => {
									const sh = n.scrollHeight || 0;
									const ch = n.clientHeight || 0;
									const st = getComputedStyle(n).overflowY;
									if (sh > ch + 50 && (st === 'auto' || st === 'scroll')) {
										best = n;
									}
								});
								el = best;
							}
							(el || document.scrollingElement || document.body).scrollTop += 800;
						}
					""")
				except Exception:
					pass
				await page.wait_for_timeout(800)
				await procesar_comentarios_en_modal_foto(page, comentarios, photo_url)
			# Pequeña pausa cada 3 fotos
			if i % 3 == 0:
				await asyncio.sleep(2)
		except Exception:
			continue
	return list(comentarios.values())

