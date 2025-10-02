import time
import logging
import asyncio
from typing import Callable, Awaitable, Optional, Any, Literal

logger = logging.getLogger(__name__)

EarlyExitReason = Literal['empty','stagnation','bottom','max']

class ScrollStats(dict):
    @property
    def duration_ms(self) -> int:
        return self.get('duration_ms', 0)

async def scroll_loop(
    *,
    process_once: Callable[[], Awaitable[int]],
    do_scroll: Callable[[], Awaitable[None]],
    max_scrolls: int = 40,
    pause_ms: int = 900,
    stagnation_limit: int = 4,
    empty_limit: int = 2,
    bottom_check: Optional[Callable[[], Awaitable[bool]]] = None,
    adaptive: bool = False,
    adaptive_decay_threshold: float = 0.3,
    min_scrolls_after_decay: int = 2,
    log_prefix: str = "scroll",
) -> ScrollStats:
    """Generic scroll loop with early-exit and optional adaptive mode.
    process_once must return number of NEW items added this iteration.
    do_scroll performs scrolling action.
    bottom_check returns True if bottom likely reached.
    """
    start = time.time()
    total = 0
    stagnation_seq = 0
    empty_seq = 0
    reason: EarlyExitReason | None = None
    effective_max = max_scrolls
    for i in range(max_scrolls):
        new_items = 0
        try:
            new_items = await process_once()
            total += new_items
        except Exception as e:
            logger.debug(f"{log_prefix} process_error scroll={i+1} err={e}")
        if new_items == 0:
            stagnation_seq += 1
            empty_seq += 1
        else:
            stagnation_seq = 0
            empty_seq = 0
        logger.info(f"{log_prefix} progress scroll={i+1} new={new_items} total={total} stag_seq={stagnation_seq}")
        # Adaptive contraction
        if adaptive and i+1 >= 3:
            avg_rate = total / (i+1)
            if avg_rate < adaptive_decay_threshold and effective_max - (i+1) > min_scrolls_after_decay:
                effective_max = (i+1) + min_scrolls_after_decay
                logger.info(f"{log_prefix} adaptive_shrink new_max={effective_max} avg_rate={avg_rate:.2f}")
        # Early exits
        if total == 0 and empty_seq >= empty_limit:
            reason = 'empty'
            break
        if stagnation_seq >= stagnation_limit:
            reason = 'stagnation'
            break
        if i+1 >= effective_max:
            reason = 'max'
            break
        # Scroll
        try:
            await do_scroll()
        except Exception:
            pass
        # Optional bottom check after scroll
        if bottom_check:
            try:
                if await bottom_check():
                    reason = 'bottom'
                    break
            except Exception:
                pass
        # Pause
        await asyncio.sleep(pause_ms / 1000)
    duration_ms = int((time.time() - start) * 1000)
    if reason is None:
        reason = 'max'
    logger.info(f"{log_prefix} end total={total} reason={reason} duration_ms={duration_ms}")
    return ScrollStats(total=total, reason=reason, duration_ms=duration_ms, scrolls=i+1)
