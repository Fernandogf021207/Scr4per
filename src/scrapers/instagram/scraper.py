import asyncio
import logging
from urllib.parse import urljoin
from src.utils.common import limpiar_url

logger = logging.getLogger(__name__)

async def obtener_foto_perfil_instagram(page):
    """Intentar obtener la foto de perfil del usuario principal de Instagram"""
    try:
        selectores_foto = [
            'img[alt*="foto de perfil"]',
            'img[data-testid="user-avatar"]',
            'header img',
            'article header img',
            'div[role="button"] img',
        ]
        
        for selector in selectores_foto:
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
        
        selectores_nombre = [
            'header section div div h2',
            'header h2',
            'article header h2',
            'h1',
            'h2'
        ]
        
        nombre_completo = None
        for selector in selectores_nombre:
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

async def obtener_datos_usuario_principal(page, perfil_url):
    """Obtener datos del perfil principal"""
    print("Obteniendo datos del perfil principal de Instagram...")
    await page.goto(perfil_url)
    await page.wait_for_timeout(5000)
    
    datos_usuario_ig = await obtener_nombre_usuario_instagram(page)
    username = datos_usuario_ig['username']
    nombre_completo = datos_usuario_ig['nombre_completo']
    foto_perfil = await obtener_foto_perfil_instagram(page)
    
    print(f"Usuario detectado: @{username} ({nombre_completo})")
    
    return {
        'username': username,
        'nombre_completo': nombre_completo,
        'foto_perfil': foto_perfil or "",
        'url_usuario': perfil_url
    }

async def extraer_usuarios_instagram(page, tipo_lista="seguidores", usuario_principal=""):
    """Extraer usuarios de una lista de Instagram (seguidores o seguidos)"""
    print(f"Cargando {tipo_lista}...")
    usuarios_dict = {}
    
    # Scroll en la lista para cargar más usuarios
    for i in range(30):
        try:
            await (await page.query_selector('a > div > div > span[dir="auto"]')).scroll_into_view_if_needed()
            await asyncio.sleep(1.5)
            
            if i % 5 == 0:
                print(f"  Scroll {i+1}/30 para {tipo_lista}...")
                
        except Exception as e:
            logger.warning(f"Error en scroll {i}: {e}")

    print(f"Procesando {tipo_lista}...")
    
    try:
        # Selectores para encontrar el contenedor de usuarios
        selectores_contenedor = [
            'div[role="dialog"] div[style*="flex-direction: column"]',
            'div[role="dialog"] div',
            f'div[aria-label="{tipo_lista.capitalize()}"]',
            'div[aria-label="Seguidores"]',
            'div[aria-label="Followers"]',
            'div[aria-label="Following"]'
        ]
        
        elementos_usuarios = []
        for selector in selectores_contenedor:
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

async def navegar_a_lista_instagram(page, perfil_url, tipo_lista="followers"):
    """Navegar a la lista de seguidores o seguidos en Instagram"""
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(3000)
        
        if tipo_lista == "followers":
            selectores_enlace = [
                'a[href*="/followers/"]',
                'a:has-text("seguidores")',
                'a:has-text("followers")',
                'header a[href*="followers"]'
            ]
            nombre_lista = "seguidores"
        else:
            selectores_enlace = [
                'a[href*="/following/"]',
                'a:has-text("seguidos")',
                'a:has-text("following")',
                'header a[href*="following"]'
            ]
            nombre_lista = "seguidos"
        
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

async def scrap_seguidores(page, perfil_url, username):
    """Scrapear seguidores del usuario"""
    print("\n🔄 Extrayendo seguidores...")
    try:
        if await navegar_a_lista_instagram(page, perfil_url, "followers"):
            seguidores = await extraer_usuarios_instagram(page, "seguidores", username)
            print(f"📊 Seguidores encontrados: {len(seguidores)}")
            return seguidores
        else:
            print("❌ No se pudieron extraer seguidores")
            return []
    except Exception as e:
        print(f"❌ Error extrayendo seguidores: {e}")
        return []

async def scrap_seguidos(page, perfil_url, username):
    """Scrapear seguidos del usuario"""
    print("\n🔄 Extrayendo seguidos...")
    try:
        if await navegar_a_lista_instagram(page, perfil_url, "following"):
            seguidos = await extraer_usuarios_instagram(page, "seguidos", username)
            print(f"📊 Seguidos encontrados: {len(seguidos)}")
            return seguidos
        else:
            print("❌ No se pudieron extraer seguidos")
            return []
    except Exception as e:
        print(f"❌ Error extrayendo seguidos: {e}")
        return []

async def extraer_posts_del_perfil(page, max_posts=10):
    """Extraer URLs de posts del perfil principal"""
    print("🔍 Buscando posts en el perfil...")
    
    try:
        # Scroll para cargar más posts
        for i in range(5):
            await page.keyboard.press("End")
            await asyncio.sleep(2)
        
        selectores_posts = [
            'article a[href*="/p/"]',
            'article a[href*="/reel/"]',
            'a[href*="/p/"]',
            'a[href*="/reel/"]'
        ]
        
        urls_posts = set()
        
        for selector in selectores_posts:
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
    print(f"💬 Extrayendo comentarios del post {post_id}...")
    
    try:
        await page.goto(url_post)
        await page.wait_for_timeout(3000)
        
        # Intentar cargar más comentarios
        while True:
            try:
                botones_cargar = [
                    'button:has-text("Cargar más comentarios")',
                    'button:has-text("Load more comments")',
                    'button[aria-label="Load more comments"]',
                    'span:has-text("Cargar más comentarios")'
                ]
                
                button_clicked = False
                for selector_boton in botones_cargar:
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
        
        # Scroll para cargar comentarios
        for i in range(10):
            try:
                area_comentarios = await page.query_selector('article section div')
                if area_comentarios:
                    await area_comentarios.scroll_into_view_if_needed()
                await page.wait_for_timeout(1000)
            except:
                pass
        
        comentarios = []
        comentarios_dict = {}
        
        # Selectores para encontrar comentarios
        selectores_comentarios = [
            'article section div div div div span[dir="auto"] a',
            'div[role="button"] span[dir="auto"] a',
            'span:has(a[href*="/"])',
            'article a[href^="/"][href$="/"]'
        ]
        
        elementos_comentarios = []
        for selector in selectores_comentarios:
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
                        "nombre_usuario": nombre_mostrado or username,
                        "username_usuario": username,
                        "link_usuario": url_perfil,
                        "foto_usuario": url_foto if url_foto and not url_foto.startswith("data:") else "",
                        "post_url": url_post
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

async def scrap_comentadores_instagram(page, perfil_url, username, max_posts=5):
    """Scrapear usuarios que comentaron los posts del usuario"""
    print(f"\n💬 Extrayendo comentarios de los últimos {max_posts} posts...")
    
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(3000)
        
        urls_posts = await extraer_posts_del_perfil(page, max_posts)
        
        comentarios = []
        for i, url_post in enumerate(urls_posts, 1):
            comentarios_post = await extraer_comentarios_post(page, url_post, i)
            comentarios.extend(comentarios_post)
            await asyncio.sleep(2)
        
        print(f"📊 Total de comentarios únicos encontrados: {len(comentarios)}")
        return comentarios
        
    except Exception as e:
        print(f"❌ Error extrayendo comentadores: {e}")
        return []

# Funciones alias para mantener compatibilidad
async def scrap_lista_usuarios(page, perfil_url, tipo):
    """Función alias para mantener compatibilidad"""
    username = await obtener_nombre_usuario_instagram(page)
    username_str = username.get('username', '')
    
    if tipo == "seguidores":
        return await scrap_seguidores(page, perfil_url, username_str)
    elif tipo == "seguidos":
        return await scrap_seguidos(page, perfil_url, username_str)
    else:
        print("❌ Tipo de lista inválido")
        return []
