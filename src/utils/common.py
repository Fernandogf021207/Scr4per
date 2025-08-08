def limpiar_url(url):
    """Remove query parameters from a URL"""
    return url.split("?")[0] if url else ""