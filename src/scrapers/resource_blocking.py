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
        try:
            request = route.request
            rtype = request.resource_type
            url = request.url.lower()
            # Regla principal: bloquear por tipo o extensión
            if (rtype in BLOCK_RESOURCE_TYPES) or url.endswith(BLOCK_EXTENSIONS):
                self.blocked += 1
                try:
                    await route.abort()
                except Exception:
                    pass
                return
            self.allowed += 1
            await route.continue_()
        except Exception:
            # Fallback: permitir para no romper flujo
            try:
                await route.continue_()
            except Exception:
                pass

    async def start(self):
        if self._active:
            return self
        self._start_ts = time.time()
        await self.page.route(self._pattern, self._handler)
        self._active = True
        logger.info(f"resblock.start platform={self.platform} phase={self.phase}")
        return self

    async def stop(self) -> Dict[str, float]:
        if not self._active:
            return {"blocked": self.blocked, "allowed": self.allowed, "duration_ms": 0.0}
        try:
            await self.page.unroute(self._pattern, self._handler)
        except Exception:
            pass
        duration_ms = (time.time() - self._start_ts) * 1000.0
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

async def start_list_blocking(page, platform: str, phase: str = 'list') -> ListResourceBlocker:
    blocker = ListResourceBlocker(page, platform, phase)
    return await blocker.start()
