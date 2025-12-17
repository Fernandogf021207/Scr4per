"""
Excepciones personalizadas para el sistema de scraping.
"""


class ScraperException(Exception):
    """Excepción base para todos los errores de scraping."""
    pass


class SessionExpiredException(ScraperException):
    """
    Se lanza cuando se detecta que la sesión ha caducado.
    Indicadores: presencia de formulario de login, redirect a login, etc.
    """
    def __init__(self, platform: str, message: str = "La sesión ha caducado"):
        self.platform = platform
        self.message = f"[{platform}] {message}"
        super().__init__(self.message)


class AccountBannedException(ScraperException):
    """
    Se lanza cuando se detecta que la cuenta está bloqueada o en checkpoint.
    Indicadores: URL contiene 'checkpoint', mensajes de verificación, etc.
    """
    def __init__(self, platform: str, message: str = "Cuenta bloqueada o en checkpoint"):
        self.platform = platform
        self.message = f"[{platform}] {message}"
        super().__init__(self.message)


class LayoutChangeException(ScraperException):
    """
    Se lanza cuando los selectores CSS/XPath no funcionan debido a cambios en el layout.
    Útil para detectar redesigns o cambios en la estructura DOM.
    """
    def __init__(self, platform: str, selector: str, message: str = "Selector no encontrado"):
        self.platform = platform
        self.selector = selector
        self.message = f"[{platform}] {message}: {selector}"
        super().__init__(self.message)


class ProxyException(ScraperException):
    """
    Se lanza cuando hay problemas con el proxy configurado.
    """
    def __init__(self, proxy_url: str, message: str = "Error de proxy"):
        self.proxy_url = proxy_url
        self.message = f"Proxy {proxy_url}: {message}"
        super().__init__(self.message)


class RateLimitException(ScraperException):
    """
    Se lanza cuando se detecta rate limiting de la plataforma.
    """
    def __init__(self, platform: str, message: str = "Rate limit detectado"):
        self.platform = platform
        self.message = f"[{platform}] {message}"
        super().__init__(self.message)


class SessionNotFoundException(ScraperException):
    """
    Se lanza cuando no se encuentra una sesión válida en la base de datos.
    """
    def __init__(self, user_id: int, platform: str):
        self.user_id = user_id
        self.platform = platform
        self.message = f"No se encontró sesión activa para usuario {user_id} en plataforma {platform}"
        super().__init__(self.message)
