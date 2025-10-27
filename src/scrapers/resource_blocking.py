import time
import logging
from typing import Dict

logger = logging.getLogger(__name__)

BLOCK_EXTENSIONS = (
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.avif',
    '.mp4', '.webm', '.mkv', '.mov', '.avi', '.m3u8', '.ts',
    '.woff', '.woff2', '.ttf', '.otf', '.eot'
)

BLOCK_RESOURCE_TYPES = {'image', 'media', 'font'}  # playwright resource_type set

class ListResourceBlocker:
    """Intercepta y bloquea recursos pesados (imágenes, video, fuentes) durante fases de listas.

    Uso:
        blocker = await start_list_blocking(page, platform='facebook', phase='list')
        ... extracción ...
        stats = await blocker.stop()
    """
    def __init__(self, page, platform: str, phase: str = 'list'):
        self.page = page
        self.platform = platform
        self.phase = phase
        self._pattern = "**/*"
        self.blocked = 0
        self.allowed = 0
        self._active = False
        self._start_ts = 0.0

    async def _handler(self, route):
        """Handler de requests con protección contra excepciones que rompen el flujo."""
        try:
            request = route.request
            rtype = request.resource_type
            url = request.url.lower()
            # Regla principal: bloquear por tipo o extensión
            should_block = (rtype in BLOCK_RESOURCE_TYPES) or any(url.endswith(ext) for ext in BLOCK_EXTENSIONS)
            
            if should_block:
                self.blocked += 1
                try:
                    await route.abort()
                except Exception as abort_err:
                    # Si abort falla, intentar continue para no romper el flujo
                    logger.debug(f"resblock.abort_failed platform={self.platform} url={url[:100]} err={abort_err}")
                    try:
                        await route.continue_()
                    except Exception:
                        pass
                return
            
            self.allowed += 1
            await route.continue_()
            
        except Exception as e:
            # Captura cualquier error no previsto y permite la request
            logger.warning(f"resblock.handler_error platform={self.platform} error={type(e).__name__}:{str(e)[:100]}")
            try:
                await route.continue_()
            except Exception:
                # Última línea de defensa: si ni siquiera continue funciona, abandonar silenciosamente
                pass

    async def start(self):
        if self._active:
            return self
        self._start_ts = time.time()
        logger.info(f"resblock.start platform={self.platform} phase={self.phase}")
        try:
            # Timeout de 5s para evitar deadlock si page.route() no responde
            import asyncio
            await asyncio.wait_for(
                self.page.route(self._pattern, self._handler),
                timeout=5.0
            )
            self._active = True
            logger.info(f"resblock.route_installed platform={self.platform} phase={self.phase}")
        except asyncio.TimeoutError:
            logger.error(f"resblock.timeout platform={self.platform} phase={self.phase} - route installation hung")
            self._active = False
            raise RuntimeError(f"Resource blocker timeout for {self.platform}:{self.phase}")
        except Exception as e:
            logger.exception(f"resblock.error platform={self.platform} phase={self.phase}")
            self._active = False
            raise
        return self

    async def stop(self) -> Dict[str, float]:
        if not self._active:
            return {"blocked": self.blocked, "allowed": self.allowed, "duration_ms": 0.0}
        
        duration_ms = (time.time() - self._start_ts) * 1000.0
        logger.info(f"resblock.stopping platform={self.platform} phase={self.phase} blocked={self.blocked} allowed={self.allowed}")
        
        try:
            import asyncio
            # Timeout para unroute también
            await asyncio.wait_for(
                self.page.unroute(self._pattern, self._handler),
                timeout=3.0
            )
            logger.info(f"resblock.unroute_ok platform={self.platform} phase={self.phase}")
        except asyncio.TimeoutError:
            logger.warning(f"resblock.unroute_timeout platform={self.platform} phase={self.phase}")
        except Exception as e:
            logger.warning(f"resblock.unroute_error platform={self.platform} err={e}")
        
        stats = {
            "blocked": self.blocked,
            "allowed": self.allowed,
            "duration_ms": duration_ms
        }
        logger.info(
            f"resblock.end platform={self.platform} phase={self.phase} blocked={self.blocked} allowed={self.allowed} duration_ms={duration_ms:.0f}"
        )
        self._active = False
        return stats

class NoopBlocker:
    """No-op blocker used to bypass routing when instability is detected.
    Keeps the same interface (start/stop) for drop-in replacement.
    """
    def __init__(self, page, platform: str, phase: str = 'list'):
        self.page = page
        self.platform = platform
        self.phase = phase
        self._start_ts = time.time()

    async def start(self):
        logger.info(f"resblock.skip platform={self.platform} phase={self.phase}")
        return self

    async def stop(self) -> Dict[str, float]:
        dur = (time.time() - self._start_ts) * 1000.0
        return {"blocked": 0, "allowed": 0, "duration_ms": dur}

async def start_list_blocking(page, platform: str, phase: str = 'list') -> ListResourceBlocker:
    # Temporary mitigation: skip blocking on Facebook lists due to crash reports during unroute/route.
    if platform.lower() == 'facebook':
        return await NoopBlocker(page, platform, phase).start()
    blocker = ListResourceBlocker(page, platform, phase)
    return await blocker.start()
