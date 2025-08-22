from typing import List, Optional


async def safe_text(el) -> Optional[str]:
    try:
        if not el:
            return None
        txt = await el.inner_text()
        return (txt or "").strip() or None
    except Exception:
        return None


async def safe_attr(el, name: str) -> Optional[str]:
    try:
        if not el:
            return None
        return await el.get_attribute(name)
    except Exception:
        return None


async def query_all_first(page, selectors: List[str]):
    """Return first non-empty list of elements found for the given selectors array."""
    for sel in selectors:
        try:
            els = await page.query_selector_all(sel)
            if els:
                return els
        except Exception:
            continue
    return []


async def find_scroll_container(page):
    """Try to find the most likely scrollable container inside a modal; return handle or None."""
    try:
        handle = await page.evaluate_handle(
            """
            () => {
                const modal = document.querySelector('div[role="dialog"], div[aria-modal="true"]');
                if (!modal) return null;
                let best = modal; let maxScore = 0;
                const all = modal.querySelectorAll('*');
                for (const n of all) {
                    const sh = n.scrollHeight || 0;
                    const ch = n.clientHeight || 0;
                    if (sh > ch + 40) {
                        const st = getComputedStyle(n).overflowY;
                        const score = (sh - ch);
                        if ((st === 'auto' || st === 'scroll') && score > maxScore) {
                            maxScore = score; best = n;
                        }
                    }
                }
                return best;
            }
            """
        )
        return handle
    except Exception:
        return None


async def scroll_element(el_handle, dy: int = 800):
    try:
        await el_handle.evaluate('el => el.scrollTop = Math.min(el.scrollTop + 800, el.scrollHeight)')
    except Exception:
        pass


async def scroll_window(page, dy: int = 600):
    try:
        await page.evaluate('window.scrollBy(0, 600)')
    except Exception:
        pass


async def _is_at_bottom_window(page, margin: int = 800) -> bool:
    try:
        return await page.evaluate(
            f"() => (window.innerHeight + window.pageYOffset) >= (document.body.scrollHeight - {margin})"
        )
    except Exception:
        return False


async def _is_at_bottom_element(el_handle) -> bool:
    try:
        return await el_handle.evaluate(
            "el => (el.scrollTop + el.clientHeight) >= (el.scrollHeight - 120)"
        )
    except Exception:
        return False


async def scroll_collect(
    page,
    process_cb,
    *,
    container=None,
    max_scrolls: int = 60,
    pause_ms: int = 1500,
    no_new_threshold: int = 6,
    bottom_margin: int = 800,
    pause_every: int | None = None,
    pause_every_ms: int = 2500,
):
    """Generic loop: process -> scroll -> pause until saturation or bottom.

    process_cb signature: async def process_cb(page, container) -> int  (returns number of new items)
    """
    scrolls = 0
    no_new = 0
    total_new = 0

    while scrolls < max_scrolls and no_new < no_new_threshold:
        try:
            added = await process_cb(page, container)
        except Exception:
            added = 0

        if added > 0:
            total_new += added
            no_new = 0
        else:
            no_new += 1

        # Check bottom
        at_bottom = False
        if container:
            at_bottom = await _is_at_bottom_element(container)
        else:
            at_bottom = await _is_at_bottom_window(page, bottom_margin)
        if at_bottom and no_new >= 3:
            break

        # Scroll
        if container:
            await scroll_element(container, 800)
        else:
            await scroll_window(page, 600)

        # Pause
        try:
            await page.wait_for_timeout(pause_ms)
        except Exception:
            pass
        scrolls += 1

        if pause_every and (scrolls % pause_every == 0):
            try:
                await page.wait_for_timeout(pause_every_ms)
            except Exception:
                pass

    return total_new
