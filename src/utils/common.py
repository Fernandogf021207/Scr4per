# src/utils/common.py
def limpiar_url(url):
    """Limpiar parámetros de consulta de una URL."""
    return url.split("?")[0] if url else ""