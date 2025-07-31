import asyncio
import logging
from src.utils.common import limpiar_url

logger = logging.getLogger(__name__)

async def obtener_foto_perfil_instagram(page):
    """Intentar obtener la foto de perfil del usuario principal de Instagram"""
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    try:
        for selector in INSTAGRAM_CONFIG["foto_selectors"]:
            foto_element = await page.query_selector(selector)
            if foto_element:
                src = await foto_element.get_attribute("src")
                if src and not src.startswith("data:"):
                    return src
        return None
    except Exception as e:
        logger.warning(f"No se pudo obtener foto de perfil: {e}")
        return None

async def obtener_nombre_usuario_instagram(page):
    """Obtener el nombre de usuario y nombre completo de Instagram"""
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    try:
        current_url = page.url
        username_from_url = current_url.split('/')[-2] if current_url.endswith('/') else current_url.split('/')[-1]
        username_from_url = username_from_url.split('?')[0]
        
        if username_from_url in ['followers', 'following']:
            parts = current_url.split('/')
            for i, part in enumerate(parts):
                if part in ['followers', 'following'] and i > 0:
                    username_from_url = parts[i-1]
                    break
        
        nombre_completo = None
        for selector in INSTAGRAM_CONFIG["nombre_selectors"]:
            element = await page.query_selector(selector)
            if element:
                text = await element.inner_text()
                text = text.strip()
                if text and text != username_from_url:
                    nombre_completo = text
                    break
        
        return {
            'username': username_from_url,
            'nombre_completo': nombre_completo or username_from_url
        }
    except Exception as e:
        logger.warning(f"Error obteniendo nombre de usuario: {e}")
        return {'username': 'unknown', 'nombre_completo': 'unknown'}

async def extraer_usuarios_instagram(page, tipo_lista="seguidores", usuario_principal=""):
    """Extraer usuarios de una lista de Instagram (seguidores o seguidos)"""
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    print(f"Cargando {tipo_lista}...")
    usuarios_dict = {}
    
    for i in range(INSTAGRAM_CONFIG["scroll_attempts"]):
        try:
            element = await page.query_selector('a > div > div > span[dir="auto"]')
            if element:
                await element.scroll_into_view_if_needed()
            await asyncio.sleep(INSTAGRAM_CONFIG["scroll_pause_ms"] / 1000)
            
            if i % 5 == 0:
                print(f"  Scroll {i+1}/{INSTAGRAM_CONFIG['scroll_attempts']} para {tipo_lista}...")
                
        except Exception as e:
            logger.warning(f"Error en scroll {i}: {e}")

    print(f"Procesando {tipo_lista}...")
    
    try:
        elementos_usuarios = []
        for selector in INSTAGRAM_CONFIG["contenedor_selectors"]:
            contenedor = await page.query_selector(selector)
            if contenedor:
                elementos_usuarios = await contenedor.query_selector_all('div:has(a[role="link"])')
                if elementos_usuarios:
                    break
        
        if not elementos_usuarios:
            elementos_usuarios = await page.query_selector_all('div[role="dialog"] a[role="link"]')
        
        print(f"Elementos encontrados para {tipo_lista}: {len(elementos_usuarios)}")
        
        for elemento in elementos_usuarios:
            try:
                enlace = await elemento.query_selector('a[role="link"]') or elemento
                if not enlace:
                    continue
                    
                href = await enlace.get_attribute("href")
                if not href or not href.startswith('/'):
                    continue
                    
                url_usuario = f"https://www.instagram.com{href}"
                url_limpia = limpiar_url(url_usuario)
                
                username_usuario = href.strip('/').split('/')[-1]
                
                img_element = await elemento.query_selector('img')
                url_foto = await img_element.get_attribute("src") if img_element else ""
                
                texto_elemento = await elemento.inner_text()
                lineas = texto_elemento.strip().split('\n')
                nombre_completo_usuario = lineas[0] if lineas else username_usuario
                
                if url_limpia not in usuarios_dict and username_usuario != usuario_principal:
                    usuarios_dict[url_limpia] = {
                        "nombre_usuario": nombre_completo_usuario,
                        "username_usuario": username_usuario,
                        "link_usuario": url_limpia,
                        "foto_usuario": url_foto if url_foto and not url_foto.startswith("data:") else ""
                    }

            except Exception as e:
                logger.warning(f"Error procesando usuario en {tipo_lista}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error general procesando {tipo_lista}: {e}")

    return list(usuarios_dict.values())

async def extraer_posts_del_perfil(page, max_posts=10):
    """Extraer URLs de posts del perfil principal"""
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    print("🔍 Buscando posts en el perfil...")
    
    try:
        for i in range(INSTAGRAM_CONFIG["post_scroll_attempts"]):
            await page.keyboard.press("End")
            await asyncio.sleep(2)
        
        urls_posts = set()
        
        for selector in INSTAGRAM_CONFIG["post_selectors"]:
            elementos_posts = await page.query_selector_all(selector)
            for elemento in elementos_posts[:max_posts]:
                href = await elemento.get_attribute("href")
                if href:
                    if href.startswith('/'):
                        url_completa = f"https://www.instagram.com{href}"
                    else:
                        url_completa = href
                    urls_posts.add(url_completa)
        
        urls_posts = list(urls_posts)[:max_posts]
        print(f"📋 Posts encontrados: {len(urls_posts)}")
        return urls_posts
        
    except Exception as e:
        logger.error(f"Error extrayendo posts: {e}")
        return []

async def extraer_comentarios_post(page, url_post, post_id):
    """Extraer comentarios de un post específico"""
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    print(f"💬 Extrayendo comentarios del post {post_id}...")
    
    try:
        await page.goto(url_post)
        await page.wait_for_timeout(INSTAGRAM_CONFIG["comment_load_timeout_ms"])
        
        while True:
            try:
                button_clicked = False
                for selector_boton in INSTAGRAM_CONFIG["botones_cargar_comentarios"]:
                    boton = await page.query_selector(selector_boton)
                    if boton:
                        await boton.click()
                        button_clicked = True
                        await page.wait_for_timeout(2000)
                        break
                if not button_clicked:
                    break
            except Exception as e:
                logger.warning(f"No se pudo cargar más comentarios: {e}")
                break
        
        for i in range(INSTAGRAM_CONFIG["comment_scroll_attempts"]):
            try:
                area_comentarios = await page.query_selector('article section div')
                if area_comentarios:
                    await area_comentarios.scroll_into_view_if_needed()
                await page.wait_for_timeout(1000)
            except:
                pass
        
        comentarios = []
        comentarios_dict = {}
        
        elementos_comentarios = []
        for selector in INSTAGRAM_CONFIG["comentario_selectors"]:
            elementos = await page.query_selector_all(selector)
            if elementos:
                elementos_comentarios.extend(elementos)
                break
        
        for elemento in elementos_comentarios:
            try:
                href = await elemento.get_attribute("href")
                if not href or not href.startswith('/'):
                    continue
                
                username = href.strip('/').split('/')[0]
                if username in ['p', 'reel', 'tv']:
                    continue
                
                nombre_mostrado = await elemento.inner_text()
                url_perfil = f"https://www.instagram.com/{username}/"
                
                url_foto = ""
                try:
                    contenedor_padre = elemento.locator('xpath=ancestor::div[1]')
                    img_element = await contenedor_padre.query_selector('img')
                    if img_element:
                        url_foto = await img_element.get_attribute("src") or ""
                except:
                    pass
                
                if username not in comentarios_dict and username != "":
                    comentarios_dict[username] = {
                        "username": username,
                        "nombre_mostrado": nombre_mostrado or username,
                        "url_perfil": url_perfil,
                        "url_foto": url_foto if url_foto and not url_foto.startswith("data:") else "",
                        "post_id": post_id,
                        "url_post": url_post
                    }
            except Exception as e:
                logger.warning(f"Error procesando comentario: {e}")
                continue
        
        comentarios = list(comentarios_dict.values())
        print(f"💬 Comentarios únicos encontrados en post {post_id}: {len(comentarios)}")
        return comentarios
        
    except Exception as e:
        logger.error(f"Error extrayendo comentarios del post: {e}")
        return []

async def navegar_a_lista_instagram(page, perfil_url, tipo_lista="followers"):
    """Navegar a la lista de seguidores o seguidos en Instagram"""
    from src.scrapers.instagram.config import INSTAGRAM_CONFIG
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(3000)
        
        selectores_enlace = INSTAGRAM_CONFIG["follower_selectors"] if tipo_lista == "followers" else INSTAGRAM_CONFIG["following_selectors"]
        nombre_lista = "seguidores" if tipo_lista == "followers" else "seguidos"
        
        print(f"Buscando enlace de {nombre_lista}...")
        
        enlace_lista = None
        for selector in selectores_enlace:
            enlace_lista = await page.query_selector(selector)
            if enlace_lista:
                break
        
        if not enlace_lista:
            print(f"❌ No se pudo encontrar el enlace de {nombre_lista}. ¿El perfil es público?")
            return False
        
        print(f"Haciendo clic en {nombre_lista}...")
        await enlace_lista.click()
        await page.wait_for_timeout(3000)
        return True
        
    except Exception as e:
        print(f"❌ Error navegando a {nombre_lista}: {e}")
        return False