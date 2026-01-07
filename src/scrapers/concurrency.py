import asyncio
import logging
from typing import Iterable, Awaitable, Callable, Any, List, Dict

logger = logging.getLogger(__name__)

class TaskResult:
    __slots__ = ("ok", "value", "error", "index", "meta")
    def __init__(self, ok: bool, value: Any = None, error: Exception | None = None, index: int = -1, meta: Dict | None = None):
        self.ok = ok
        self.value = value
        self.error = error
        self.index = index
        self.meta = meta or {}

    def __repr__(self):
        if self.ok:
            return f"TaskResult(ok index={self.index})"
        return f"TaskResult(err index={self.index} error={self.error})"

async def run_limited(coros: Iterable[Callable[[], Awaitable[Any]]], limit: int = 3, label: str = "group") -> List[TaskResult]:
    """Ejecuta callables que retornan coroutines con un Semaphore limitado.

    Cada elemento de `coros` debe ser un callable sin argumentos que devuelva la coroutine real al invocarse.
    Devuelve lista de TaskResult en el mismo orden de entrada.
    """
    semaphore = asyncio.Semaphore(limit)
    results: List[TaskResult] = [None] * len(list(coros))  # type: ignore
    coros_list = list(coros)

    async def _runner(idx: int, fn: Callable[[], Awaitable[Any]]):
        async with semaphore:
            try:
                val = await fn()
                results[idx] = TaskResult(True, val, None, idx)
            except Exception as e:  # noqa
                logger.warning(f"concurrent task error label={label} idx={idx} error={e}")
                results[idx] = TaskResult(False, None, e, idx)

    tasks = [asyncio.create_task(_runner(i, fn)) for i, fn in enumerate(coros_list)]
    await asyncio.gather(*tasks)
    return results
