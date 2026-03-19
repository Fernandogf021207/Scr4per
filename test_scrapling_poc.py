import asyncio
import logging
import os
import sys
import time
from playwright.async_api import async_playwright

# Asegurar que importamos del src local
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.scrapers.facebook.scrapling_spider import (
    login_facebook,
    get_profile_data_scrapling,
    scrap_list_network_scrapling,
    scrap_photo_engagements_scrapling,
    export_to_csv,
)
from src.scrapers.facebook.scraper import (
    obtener_datos_usuario_facebook,
    scrap_friends_all,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


async def run_comparison():
    TARGET_PROFILE = "https://www.facebook.com/johana.romero.520357"
    STATE_PATH = "facebook_storage_state.json"
    CSV_OUTPUT = os.path.join(os.path.dirname(__file__), "scrapling_export.csv")

    context_args = {}
    if os.path.exists(STATE_PATH):
        context_args['storage_state'] = STATE_PATH
        logger.info(f"Usando storage state de {STATE_PATH}")
    else:
        logger.warning(f"No se encontro {STATE_PATH}. La prueba fallara si Facebook pide login.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(**context_args)

        # ------------------------------------------------------------------
        # PRUEBA 1: PLAYWRIGHT PURO (referencia de rendimiento)
        # ------------------------------------------------------------------
        logger.info("=" * 50)
        logger.info("PRUEBA 1: PLAYWRIGHT PURO")
        logger.info("=" * 50)

        page1 = await context.new_page()
        start_time_pw = time.time()
        try:
            datos_pw = await obtener_datos_usuario_facebook(page1, TARGET_PROFILE)
            logger.info(f"Perfil PW: {datos_pw.get('nombre_completo')}")
            amigos_pw = await scrap_friends_all(page1, TARGET_PROFILE, datos_pw.get('username', ''))
            logger.info(f"Amigos PW: {len(amigos_pw)}")
        except Exception as e:
            import traceback
            logger.error(f"Error en Playwright puro:\n{traceback.format_exc()}")
        time_pw = time.time() - start_time_pw
        await page1.close()

        # ------------------------------------------------------------------
        # PRUEBA 2: SCRAPLING + NETWORK INTERCEPTION
        # ------------------------------------------------------------------
        logger.info("=" * 50)
        logger.info("PRUEBA 2: SCRAPLING + NETWORK INTERCEPTION")
        logger.info("=" * 50)

        page2 = await context.new_page()
        start_time_scrap = time.time()
        results = {}

        try:
            is_logged_in = await login_facebook(page2)

            if is_logged_in or not os.path.exists(STATE_PATH):
                # --- Perfil ---
                logger.info("Extrayendo perfil...")
                results['profile'] = await get_profile_data_scrapling(page2, TARGET_PROFILE)
                logger.info(f"  -> {results['profile'].get('nombre_completo')}")

                # --- Amigos ---
                logger.info("Extrayendo amigos (red)...")
                results['friends'] = await scrap_list_network_scrapling(page2, TARGET_PROFILE, 'friends_all')
                logger.info(f"  -> {len(results['friends'])} amigos")

                # --- Followers ---
                logger.info("Extrayendo followers (red)...")
                results['followers'] = await scrap_list_network_scrapling(page2, TARGET_PROFILE, 'followers')
                logger.info(f"  -> {len(results['followers'])} seguidores")

                # --- Following ---
                logger.info("Extrayendo following (red)...")
                results['followed'] = await scrap_list_network_scrapling(page2, TARGET_PROFILE, 'followed')
                logger.info(f"  -> {len(results['followed'])} seguidos")

                # --- Reacciones y comentarios en fotos ---
                logger.info("Extrayendo engagements de fotos (red)...")
                engagements = await scrap_photo_engagements_scrapling(page2, TARGET_PROFILE, max_photos=3)
                results['reactions'] = engagements.get('reactions', [])
                results['comments'] = engagements.get('comments', [])
                logger.info(f"  -> {len(results['reactions'])} reacciones, {len(results['comments'])} comentarios")

                # --- Exportar por pandas (ya en requirements.txt) ---
                export_to_csv(results, CSV_OUTPUT)

            else:
                logger.error("No se pudo validar la sesion de Facebook.")

        except Exception as e:
            import traceback
            logger.error(f"Error en Scrapling:\n{traceback.format_exc()}")

        time_scrap = time.time() - start_time_scrap
        await page2.close()
        await browser.close()

        # ------------------------------------------------------------------
        # RESULTADOS
        # ------------------------------------------------------------------
        logger.info("=" * 50)
        logger.info("RESULTADOS FINALES:")
        logger.info(f"  Playwright puro : {time_pw:.2f} s")
        logger.info(f"  Scrapling + Red  : {time_scrap:.2f} s")
        logger.info("=" * 50)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_comparison())
