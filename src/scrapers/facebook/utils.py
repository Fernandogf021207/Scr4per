import logging
from urllib.parse import urljoin
from src.utils.common import limpiar_url

logger = logging.getLogger(__name__)


def build_fb_url(path: str) -> str:
	if not path:
		return ""
	if path.startswith("http"):
		return path
	return urljoin("https://www.facebook.com/", path)


async def get_text(el):
	try:
		if not el:
			return None
		txt = await el.inner_text()
		return (txt or "").strip()
	except Exception:
		return None


async def get_attr(el, name: str):
	try:
		if not el:
			return None
		return await el.get_attribute(name)
	except Exception:
		return None


def normalize_profile_url(href: str) -> str:
	"""Normaliza hrefs de perfiles a URLs completas limpias.
	Acepta patrones como '/profile.php?id=...', '/username', 'https://www.facebook.com/username?sk=...'"""
	if not href:
		return ""
	href = href.strip()
	if href.startswith("/" ):
		href = urljoin("https://www.facebook.com", href)
	if not href.startswith("http"):
		href = urljoin("https://www.facebook.com/", href)
	return limpiar_url(href)


def absolute_url_keep_query(href: str) -> str:
	"""Convierte a URL absoluta manteniendo parámetros de consulta intactos.
	No limpia la query; útil para photo.php?fbid=... y similares."""
	if not href:
		return ""
	href = href.strip()
	if href.startswith("http"):
		return href
	if href.startswith("/"):
		return urljoin("https://www.facebook.com", href)
	return urljoin("https://www.facebook.com/", href)

