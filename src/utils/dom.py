from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


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
        # Try Facebook-specific selectors first
        fb_selectors = [
            'div[role="main"]',
            'div[aria-label*="Friends"]',
            'div[aria-label*="Followers"]',
            'div[aria-label*="Following"]',
        ]
        for sel in fb_selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    # Check if scrollable
                    is_scrollable = await el.evaluate('''
                        el => {
                            const style = getComputedStyle(el);
                            const overflow = style.overflowY;
                            return (overflow === 'auto' || overflow === 'scroll' || el.scrollHeight > el.clientHeight);
                        }
                    ''')
                    if is_scrollable:
                        logger.debug("find_scroll_container found FB container: %s", sel)
                        return el
            except Exception:
                continue
        
        # Generic modal detection
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
    """Scroll an element - simple and direct like Instagram."""
    try:
        await el_handle.evaluate(f'el => el.scrollTop += {dy}')
    except Exception as e:
        logger.debug("scroll.element failed: %s", e)


async def scroll_window(page, dy: int = 600):
    """Scroll the window - simple and direct like Instagram."""
    try:
        await page.evaluate(f'window.scrollBy(0, {dy})')
    except Exception as e:
        logger.debug("scroll.window failed: %s", e)


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
    pause_ms: int = 3500,
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
            try:
                # Log metrics at exit
                if container:
                    metrics = await container.evaluate("el => ({scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight})")
                    logger.info("scroll.bottom element scrollTop=%s scrollHeight=%s clientHeight=%s", metrics.get('scrollTop'), metrics.get('scrollHeight'), metrics.get('clientHeight'))
                else:
                    metrics = await page.evaluate("() => ({scrollY: window.pageYOffset, innerHeight: window.innerHeight, scrollHeight: document.body.scrollHeight})")
                    logger.info("scroll.bottom window scrollY=%s innerHeight=%s scrollHeight=%s", metrics.get('scrollY'), metrics.get('innerHeight'), metrics.get('scrollHeight'))
            except Exception:
                pass
            break

        # Scroll (more aggressive for Facebook lists)
        if container:
            await scroll_element(container, 1200)
        else:
            await scroll_window(page, 1000)

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

    logger.info("scroll.done scrolls=%d total_new=%d no_new=%d", scrolls, total_new, no_new)
    return total_new
