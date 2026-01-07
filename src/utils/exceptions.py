"""
Sistema de Excepciones para Scraper con Pool Global.

Jerarquía de errores que permite al SessionManager tomar decisiones
inteligentes sobre la salud y disponibilidad de las cuentas en el pool.

Cada excepción indica una acción específica:
- SessionExpiredException → Suspender cuenta (cookies expiradas)
- AccountBannedException → Marcar como banned (cuenta bloqueada permanentemente)
- NetworkException → No penalizar cuenta (problema de infraestructura)
- LayoutChangeException → Alerta técnica (cambios en la plataforma)
- StorageException → Error de infraestructura (FTP)
"""


class ScraperException(Exception):
    """
    Excepción base para todos los errores del scraper.
    
    Attributes:
        message: Descripción del error
        account_id: ID de la cuenta que estaba siendo usada (opcional)
        platform: Plataforma donde ocurrió el error (opcional)
    """
    
    def __init__(self, message: str, account_id: int = None, platform: str = None):
        self.message = message
        self.account_id = account_id
        self.platform = platform
        super().__init__(message)


class SessionExpiredException(ScraperException):
    """
    La sesión de la cuenta ha expirado o fue invalidada.
    
    Disparadores:
    - Redirección a login.php
    - Página de login detectada visualmente (input[name='email'])
    - Botón "Crear cuenta" visible
    - Usuario deslogueado
    
    Acción del Sistema:
    - Marcar cuenta como SUSPENDED
    - Notificar al administrador
    - Remover cuenta del pool hasta que se actualicen cookies
    
    Example:
        raise SessionExpiredException(
            "Detectado input de login en página",
            account_id=42,
            platform="facebook"
        )
    """
    
    def __init__(self, message: str, account_id: int = None, platform: str = None, detected_element: str = None):
        super().__init__(message, account_id, platform)
        self.detected_element = detected_element  # Elemento que disparó la detección


class AccountBannedException(ScraperException):
    """
    La cuenta ha sido bloqueada o inhabilitada por la plataforma.
    
    Disparadores:
    - Checkpoint de Facebook detectado
    - Mensaje "Tu cuenta ha sido inhabilitada"
    - Mensaje "Temporary block"
    - URL contiene /checkpoint/
    - Captcha recurrente
    
    Acción del Sistema:
    - Marcar cuenta como BANNED
    - Remover permanentemente del pool
    - Alerta crítica al administrador
    - No reintentar con esta cuenta
    
    Example:
        raise AccountBannedException(
            "Detectado checkpoint de seguridad",
            account_id=42,
            platform="facebook",
            ban_type="checkpoint"
        )
    """
    
    def __init__(self, message: str, account_id: int = None, platform: str = None, ban_type: str = None):
        super().__init__(message, account_id, platform)
        self.ban_type = ban_type  # Tipo de bloqueo: "checkpoint", "disabled", "temp_block", etc.


class NetworkException(ScraperException):
    """
    Error de red o timeout que no es culpa de la cuenta.
    
    Disparadores:
    - Timeout de carga de página
    - Error de conexión TCP
    - DNS resolution failure
    - Proxy no responde
    - 502/503/504 HTTP errors
    
    Acción del Sistema:
    - NO penalizar la cuenta
    - Incrementar error_count levemente (sin cambiar estado)
    - Reintentar operación (con backoff)
    - Si es recurrente, revisar infraestructura de red
    
    Example:
        raise NetworkException(
            "Timeout al cargar página después de 30s",
            account_id=42,
            platform="facebook",
            timeout_seconds=30
        )
    """
    
    def __init__(self, message: str, account_id: int = None, platform: str = None, timeout_seconds: int = None):
        super().__init__(message, account_id, platform)
        self.timeout_seconds = timeout_seconds


class LayoutChangeException(ScraperException):
    """
    Los selectores CSS/XPath esperados no se encuentran en la página.
    
    Disparadores:
    - Selector crítico no encontrado (ej: div[role='navigation'])
    - Estructura HTML cambió
    - Elementos movidos o renombrados
    - Atributos data-* modificados
    
    Acción del Sistema:
    - NO penalizar la cuenta (no es culpa de ella)
    - Alerta técnica al equipo de desarrollo
    - Log detallado para debugging
    - Reintentar con otra cuenta (por si es A/B testing)
    - Si es recurrente, actualizar selectores
    
    Example:
        raise LayoutChangeException(
            "No se encontró selector: div[role='navigation']",
            account_id=42,
            platform="facebook",
            missing_selector="div[role='navigation']"
        )
    """
    
    def __init__(self, message: str, account_id: int = None, platform: str = None, missing_selector: str = None):
        super().__init__(message, account_id, platform)
        self.missing_selector = missing_selector


class StorageException(ScraperException):
    """
    Error al interactuar con el sistema de almacenamiento (FTP, S3, etc).
    
    Disparadores:
    - Fallo al conectar con FTP
    - Error al subir archivo
    - Disco lleno en servidor remoto
    - Permisos insuficientes
    - Timeout de transferencia
    
    Acción del Sistema:
    - Abortar operación actual
    - NO penalizar la cuenta
    - HTTP 500 Internal Server Error
    - Alerta de infraestructura crítica
    - Verificar salud del servicio de storage
    
    Example:
        raise StorageException(
            "Timeout al subir archivo a FTP después de 60s",
            account_id=42,
            platform="facebook",
            file_path="/storage/facebook/user123/profile.jpg"
        )
    """
    
    def __init__(self, message: str, account_id: int = None, platform: str = None, file_path: str = None):
        super().__init__(message, account_id, platform)
        self.file_path = file_path


# Utility para logging estructurado
def log_exception(exception: ScraperException, logger):
    """
    Helper para logging estructurado de excepciones del scraper.
    
    Args:
        exception: Instancia de ScraperException o subclase
        logger: Logger de Python (logging.Logger)
    
    Example:
        try:
            # ... scraping code ...
        except ScraperException as e:
            log_exception(e, logger)
            raise
    """
    log_data = {
        "exception_type": type(exception).__name__,
        "message": exception.message,
        "account_id": exception.account_id,
        "platform": exception.platform
    }
    
    # Agregar atributos específicos según el tipo
    if isinstance(exception, SessionExpiredException):
        log_data["detected_element"] = getattr(exception, "detected_element", None)
    elif isinstance(exception, AccountBannedException):
        log_data["ban_type"] = getattr(exception, "ban_type", None)
    elif isinstance(exception, NetworkException):
        log_data["timeout_seconds"] = getattr(exception, "timeout_seconds", None)
    elif isinstance(exception, LayoutChangeException):
        log_data["missing_selector"] = getattr(exception, "missing_selector", None)
    elif isinstance(exception, StorageException):
        log_data["file_path"] = getattr(exception, "file_path", None)
    
    logger.error(f"Scraper Exception: {log_data}")
