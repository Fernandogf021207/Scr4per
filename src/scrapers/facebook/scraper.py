import logging
from urllib.parse import urljoin
from src.scrapers.facebook.utils import (
    obtener_foto_perfil_facebook,
    obtener_nombre_usuario_facebook,
    procesar_usuarios_en_pagina
)
from src.utils.common import limpiar_url
logger = logging.getLogger(__name__)

async def obtener_datos_usuario_principal(page, perfil_url):
    print("Obteniendo datos del perfil principal de Facebook...")
    await page.goto(perfil_url)
    await page.wait_for_timeout(5000)
    datos_usuario = await obtener_nombre_usuario_facebook(page)
    foto = await obtener_foto_perfil_facebook(page)
    datos_usuario['foto_perfil'] = foto
    datos_usuario['url_usuario'] = perfil_url
    print(f"Usuario detectado: @{datos_usuario['username']} ({datos_usuario['nombre_completo']})")
    return datos_usuario

async def scrap_lista_usuarios(page, perfil_url):
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    print("\n🔄 Navegando a la lista de amigos...")
    try:
        amigos_url = urljoin(perfil_url, "friends_all")
        await page.goto(amigos_url)
        await page.wait_for_timeout(6000)

        print("Cargando amigos...")
        for i in range(FACEBOOK_CONFIG['max_scroll_attempts']):
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(FACEBOOK_CONFIG['scroll_pause_ms'])
            if i % 10 == 0:
                print(f"  Scroll {i+1}/{FACEBOOK_CONFIG['max_scroll_attempts']}...")

        print("Procesando tarjetas de amigos...")
        tarjetas = await page.query_selector_all('div[role="main"] div:has(a[tabindex="0"])')
        amigos_dict = {}

        for tarjeta in tarjetas:
            try:
                a_nombre = await tarjeta.query_selector('a[tabindex="0"]')
                a_img = await tarjeta.query_selector('a[tabindex="-1"] img')

                nombre = await a_nombre.inner_text() if a_nombre else "Sin nombre"
                nombre = nombre.strip()
                perfil = await a_nombre.get_attribute("href") if a_nombre else None
                imagen = await a_img.get_attribute("src") if a_img else None
                perfil_limpio = limpiar_url(perfil)

                if not perfil or nombre.lower().startswith(("1 amigo", "2 amigos", "3 amigos")):
                    continue

                if any(b in perfil_limpio for b in FACEBOOK_CONFIG["patterns_to_exclude"]):
                    continue

                if perfil_limpio not in amigos_dict:
                    amigos_dict[perfil_limpio] = {
                        "nombre_usuario": nombre,
                        "username_usuario": nombre.replace(" ", "_"),
                        "link_usuario": perfil_limpio,
                        "foto_usuario": imagen or ""
                    }

            except Exception as e:
                logger.warning(f"Error procesando tarjeta: {e}")

        print(f"✅ Amigos extraídos: {len(amigos_dict)}")
        return list(amigos_dict.values())

    except Exception as e:
        print(f"❌ Error extrayendo amigos: {e}")
        return []

async def scrap_comentadores_facebook(page, perfil_url):
    from src.scrapers.facebook.config import FACEBOOK_CONFIG
    print("\n🔄 Navegando al perfil para extraer comentadores...")
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(5000)

        posts = await page.query_selector_all('div[role="article"]')
        comentadores_dict = {}
        posts_procesados = 0

        for post in posts:
            if posts_procesados >= FACEBOOK_CONFIG['max_posts']:
                break

            try:
                await post.scroll_into_view_if_needed()
                await page.wait_for_timeout(2000)
                comentarios = await post.query_selector_all('div[aria-label="Comentario"]')
                for comentario in comentarios:
                    try:
                        enlace_usuario = await comentario.query_selector('a[href^="/"]')
                        if not enlace_usuario:
                            continue
                        href = await enlace_usuario.get_attribute("href")
                        if not href:
                            continue
                        username_usuario = href.strip('/').split('/')[-1]
                        url_usuario = f"https://www.facebook.com{href}" if href.startswith('/') else href
                        url_limpia = limpiar_url(url_usuario)

                        if url_limpia in comentadores_dict:
                            continue

                        img = await comentario.query_selector('img[src*="scontent"]')
                        foto = await img.get_attribute("src") if img else ""

                        span = await comentario.query_selector('span')
                        nombre = await span.inner_text() if span else username_usuario

                        comentadores_dict[url_limpia] = {
                            "nombre_usuario": nombre,
                            "username_usuario": username_usuario,
                            "link_usuario": url_limpia,
                            "foto_usuario": foto,
                            "post_url": page.url
                        }

                    except Exception as e:
                        logger.warning(f"Error procesando comentario: {e}")

                posts_procesados += 1
                print(f"📝 Post {posts_procesados}/{FACEBOOK_CONFIG['max_posts']} procesado")

            except Exception as e:
                logger.warning(f"Error procesando post: {e}")

        print(f"✅ Comentadores extraídos: {len(comentadores_dict)}")
        return list(comentadores_dict.values())

    except Exception as e:
        print(f"❌ Error extrayendo comentadores: {e}")
        return []