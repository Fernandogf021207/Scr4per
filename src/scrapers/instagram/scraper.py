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
    
    # Scroll robusto en el modal para cargar más usuarios
    print(f"📜 Haciendo scroll en modal de {tipo_lista}...")

    # Intentar identificar el contenedor scrolleable real dentro del modal
    container = None
    try:
        container = await page.evaluate_handle("""
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
        """)
    except Exception:
        container = None

    scroll_attempts = 0
    max_scrolls = 60
    no_new_users_count = 0
    max_no_new_users = 6

    while scroll_attempts < max_scrolls and no_new_users_count < max_no_new_users:
        try:
            current_user_count = len(usuarios_dict)

            if container:
                try:
                    await container.evaluate("el => el.scrollTop = Math.min(el.scrollTop + 800, el.scrollHeight)")
                except Exception:
                    # Fallback a scroll de ventana
                    await page.evaluate("window.scrollBy(0, 600)")
            else:
                await page.evaluate("window.scrollBy(0, 600)")

            await page.wait_for_timeout(1200)

            # Procesar usuarios después del scroll
            await procesar_usuarios_en_modal(page, usuarios_dict, usuario_principal, tipo_lista)

            # Verificar si se agregaron nuevos usuarios
            if len(usuarios_dict) > current_user_count:
                no_new_users_count = 0
                print(f"  📊 {tipo_lista}: {len(usuarios_dict)} usuarios encontrados (scroll {scroll_attempts + 1})")
            else:
                no_new_users_count += 1
                print(f"  ⏳ Sin nuevos usuarios en scroll {scroll_attempts + 1} (intentos: {no_new_users_count})")

            scroll_attempts += 1

            # Pausa cada 12 scrolls para evitar rate limiting
            if scroll_attempts % 12 == 0:
                print(f"  🔄 Pausa para evitar rate limiting... ({len(usuarios_dict)} usuarios hasta ahora)")
                await page.wait_for_timeout(2500)

            # Verificar si llegamos al final del contenedor
            is_at_bottom = False
            try:
                if container:
                    is_at_bottom = await container.evaluate(
                        "el => (el.scrollTop + el.clientHeight) >= (el.scrollHeight - 120)"
                    )
                else:
                    is_at_bottom = await page.evaluate(
                        "() => (window.innerHeight + window.pageYOffset) >= (document.body.scrollHeight - 200)"
                    )
            except Exception:
                is_at_bottom = False

            if is_at_bottom and no_new_users_count >= 3:
                print(f"  ✅ Llegamos al final de la lista de {tipo_lista}")
                break

        except Exception as e:
            logger.warning(f"Error en scroll {scroll_attempts}: {e}")
            no_new_users_count += 1
            await page.wait_for_timeout(1000)

    print(f"✅ Scroll completado para {tipo_lista}. Total de scrolls: {scroll_attempts}")
    print(f"📊 Usuarios únicos extraídos: {len(usuarios_dict)}")
    
    return list(usuarios_dict.values())

async def procesar_usuarios_en_modal(page, usuarios_dict, usuario_principal, tipo_lista):
    """Procesar usuarios visibles en el modal actual"""
    try:
        # Selectores específicos para elementos de usuarios en el modal
        selectores_contenedor = [
            'div[role="dialog"] div[style*="flex-direction: column"] > div',
            'div[role="dialog"] div > div:has(a[role="link"])',
            'div[aria-modal="true"] div:has(a[role="link"])',
            f'div[aria-label="{tipo_lista.capitalize()}"] div:has(a)',
            'div[role="dialog"] a[role="link"]'
        ]
        
        elementos_usuarios = []
        for selector in selectores_contenedor:
            try:
                elementos = await page.query_selector_all(selector)
                if elementos:
                    # Filtrar elementos que realmente contienen información de usuario
                    elementos_validos = []
                    for elemento in elementos:
                        try:
                            # Verificar que tiene enlace de perfil
                            enlace = await elemento.query_selector('a[role="link"]') or elemento
                            if enlace:
                                href = await enlace.get_attribute("href")
                                if href and href.startswith('/') and len(href.split('/')) >= 2:
                                    elementos_validos.append(elemento)
                        except:
                            continue
                    
                    if elementos_validos:
                        elementos_usuarios = elementos_validos
                        print(f"  ✓ Encontrados {len(elementos_usuarios)} elementos con: {selector}")
                        break
            except:
                continue
        
        if not elementos_usuarios:
            print(f"  ⚠️ No se encontraron usuarios en este scroll")
            return
        
        # Procesar cada elemento de usuario
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
                
                # Evitar procesar el usuario principal
                if username_usuario == usuario_principal:
                    continue
                
                # Evitar duplicados
                if url_limpia in usuarios_dict:
                    continue
                
                # Obtener imagen de perfil
                img_element = await elemento.query_selector('img')
                url_foto = ""
                if img_element:
                    url_foto = await img_element.get_attribute("src") or ""
                
                # Obtener nombre completo
                texto_elemento = await elemento.inner_text()
                lineas = texto_elemento.strip().split('\n')
                nombre_completo_usuario = lineas[0] if lineas and lineas[0] else username_usuario
                
                usuarios_dict[url_limpia] = {
                    "nombre_usuario": nombre_completo_usuario,
                    "username_usuario": username_usuario,
                    "link_usuario": url_limpia,
                    "foto_usuario": url_foto if url_foto and not url_foto.startswith("data:") else ""
                }

            except Exception as e:
                logger.warning(f"Error procesando usuario individual: {e}")
                continue
                
    except Exception as e:
        logger.warning(f"Error procesando usuarios en modal: {e}")

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
    """Extraer URLs de posts del perfil principal con scroll manual mejorado"""
    print("🔍 Buscando posts en el perfil...")
    
    try:
        urls_posts = set()
        scroll_attempts = 0
        max_scrolls = 10
        no_new_posts_count = 0
        max_no_new_posts = 3
        
        while len(urls_posts) < max_posts and scroll_attempts < max_scrolls and no_new_posts_count < max_no_new_posts:
            current_posts_count = len(urls_posts)
            
            # Scroll manual en la página del perfil
            await page.evaluate("""
                () => {
                    window.scrollBy(0, window.innerHeight * 0.8);
                }
            """)
            
            await page.wait_for_timeout(2000)
            
            # Buscar posts después del scroll
            selectores_posts = [
                'article a[href*="/p/"]',
                'article a[href*="/reel/"]',
                'a[href*="/p/"]',
                'a[href*="/reel/"]',
                'div a[href*="/p/"]',
                'div a[href*="/reel/"]'
            ]
            
            for selector in selectores_posts:
                try:
                    elementos_posts = await page.query_selector_all(selector)
                    for elemento in elementos_posts:
                        if len(urls_posts) >= max_posts:
                            break
                        try:
                            href = await elemento.get_attribute("href")
                            if href:
                                if href.startswith('/'):
                                    url_completa = f"https://www.instagram.com{href}"
                                else:
                                    url_completa = href
                                
                                # Verificar que es un post o reel válido
                                if '/p/' in url_completa or '/reel/' in url_completa:
                                    urls_posts.add(url_completa)
                        except:
                            continue
                except:
                    continue
            
            # Verificar progreso
            if len(urls_posts) > current_posts_count:
                no_new_posts_count = 0
                print(f"  📊 Posts encontrados: {len(urls_posts)} (scroll {scroll_attempts + 1})")
            else:
                no_new_posts_count += 1
                print(f"  ⏳ Sin nuevos posts en scroll {scroll_attempts + 1}")
            
            scroll_attempts += 1
            
            # Verificar si llegamos al final de la página
            is_at_bottom = await page.evaluate("""
                () => {
                    return (window.innerHeight + window.pageYOffset) >= document.body.scrollHeight - 1000;
                }
            """)
            
            if is_at_bottom:
                print("  ✅ Llegamos al final del perfil")
                break
        
        urls_posts = list(urls_posts)[:max_posts]
        print(f"📋 Posts finales encontrados: {len(urls_posts)}")
        return urls_posts
        
    except Exception as e:
        logger.error(f"Error extrayendo posts: {e}")
        return []

async def extraer_comentarios_post(page, url_post, post_id):
    """Extraer comentarios de un post específico con scroll manual mejorado"""
    print(f"💬 Extrayendo comentarios del post {post_id}...")
    
    try:
        await page.goto(url_post)
        await page.wait_for_timeout(3000)
        
        comentarios_dict = {}
        
        # Primero intentar cargar más comentarios con botones
        print(f"  🔄 Intentando cargar más comentarios...")
        for _ in range(3):
            try:
                botones_cargar = [
                    'button:has-text("Cargar más comentarios")',
                    'button:has-text("Load more comments")',
                    'button[aria-label="Load more comments"]',
                    'span:has-text("Cargar más comentarios")',
                    'button:has-text("Ver más comentarios")',
                    'button:has-text("View more comments")'
                ]
                
                button_clicked = False
                for selector_boton in botones_cargar:
                    boton = await page.query_selector(selector_boton)
                    if boton:
                        await boton.click()
                        button_clicked = True
                        await page.wait_for_timeout(2000)
                        print(f"  ✓ Botón 'cargar más' clickeado")
                        break
                if not button_clicked:
                    break
            except Exception as e:
                logger.warning(f"No se pudo cargar más comentarios con botón: {e}")
                break
        
        # Scroll manual para cargar más comentarios
        print(f"  📜 Haciendo scroll para cargar comentarios...")
        scroll_attempts = 0
        max_scrolls = 15
        no_new_comments_count = 0
        max_no_new_comments = 3
        
        while scroll_attempts < max_scrolls and no_new_comments_count < max_no_new_comments:
            current_comments_count = len(comentarios_dict)
            
            # Scroll manual específico en el área de comentarios
            await page.evaluate("""
                () => {
                    // Buscar el contenedor de comentarios
                    const commentSection = document.querySelector('article section') ||
                                         document.querySelector('div[role="button"] section') ||
                                         document.querySelector('section');
                    
                    if (commentSection) {
                        // Buscar el área scrolleable de comentarios
                        const scrollableArea = commentSection.querySelector('div[style*="overflow"]') ||
                                             commentSection.querySelector('div[style*="max-height"]') ||
                                             commentSection;
                        
                        // Hacer scroll hacia abajo
                        scrollableArea.scrollTop += 300;
                    } else {
                        // Fallback: scroll en la página
                        window.scrollBy(0, 300);
                    }
                }
            """)
            
            await page.wait_for_timeout(1500)
            
            # Procesar comentarios después del scroll
            await procesar_comentarios_en_post(page, comentarios_dict, url_post)
            
            # Verificar progreso
            if len(comentarios_dict) > current_comments_count:
                no_new_comments_count = 0
                print(f"  📊 Comentarios encontrados: {len(comentarios_dict)} (scroll {scroll_attempts + 1})")
            else:
                no_new_comments_count += 1
                print(f"  ⏳ Sin nuevos comentarios en scroll {scroll_attempts + 1}")
            
            scroll_attempts += 1
            
            # Pausa cada 5 scrolls
            if scroll_attempts % 5 == 0:
                await page.wait_for_timeout(2000)
        
        comentarios = list(comentarios_dict.values())
        print(f"💬 Comentarios únicos encontrados en post {post_id}: {len(comentarios)}")
        return comentarios
        
    except Exception as e:
        logger.error(f"Error extrayendo comentarios del post: {e}")
        return []

async def extraer_comentarios_en_modal(page, url_post, post_id):
    """Extraer comentarios cuando se abren en un modal"""
    print(f"💬 Buscando comentarios en modal para post {post_id}...")
    
    try:
        comentarios_dict = {}
        
        # Buscar y hacer click en el botón de comentarios
        botones_comentarios = [
            'svg[aria-label="Comentar"]',
            'svg[aria-label="Comment"]',
            'button[aria-label="Comentar"]',
            'button[aria-label="Comment"]',
            '[role="button"]:has(svg[aria-label*="omment"])',
            'div[role="button"]:has(svg[fill="#262626"])',
            'button:has(svg[height="24"][width="24"])',
            'svg[height="24"][viewBox="0 0 24 24"]:has(path[d*="20.656"])'
        ]
        
        modal_abierto = False
        for selector_boton in botones_comentarios:
            try:
                boton_comentarios = await page.query_selector(selector_boton)
                if boton_comentarios:
                    await boton_comentarios.click()
                    await page.wait_for_timeout(2000)
                    
                    # Verificar si se abrió un modal
                    modal = await page.query_selector('div[role="dialog"]')
                    if modal:
                        print(f"  ✓ Modal de comentarios abierto")
                        modal_abierto = True
                        break
            except Exception as e:
                logger.debug(f"No se pudo hacer click en botón de comentarios: {e}")
                continue
        
        if not modal_abierto:
            print(f"  ❌ No se pudo abrir modal de comentarios")
            return []
        
        # Hacer scroll manual dentro del modal
        print(f"  📜 Haciendo scroll en modal de comentarios...")
        scroll_attempts = 0
        max_scrolls = 20
        no_new_comments_count = 0
        max_no_new_comments = 3
        
        while scroll_attempts < max_scrolls and no_new_comments_count < max_no_new_comments:
            current_comments_count = len(comentarios_dict)
            
            # Scroll específico en el modal
            await page.evaluate("""
                () => {
                    // Buscar el modal de comentarios
                    const modal = document.querySelector('div[role="dialog"]');
                    if (modal) {
                        // Buscar el área scrolleable dentro del modal
                        const scrollableArea = modal.querySelector('div[style*="overflow"]') ||
                                             modal.querySelector('div[style*="max-height"]') ||
                                             modal.querySelector('div[style*="height"]') ||
                                             modal;
                        
                        // Hacer scroll hacia abajo en el modal
                        scrollableArea.scrollTop += 400;
                    }
                }
            """)
            
            await page.wait_for_timeout(1500)
            
            # Procesar comentarios en el modal
            await procesar_comentarios_en_modal(page, comentarios_dict, url_post)
            
            # Verificar progreso
            if len(comentarios_dict) > current_comments_count:
                no_new_comments_count = 0
                print(f"  📊 Comentarios en modal: {len(comentarios_dict)} (scroll {scroll_attempts + 1})")
            else:
                no_new_comments_count += 1
                print(f"  ⏳ Sin nuevos comentarios en modal (scroll {scroll_attempts + 1})")
            
            scroll_attempts += 1
            
            # Pausa cada 5 scrolls
            if scroll_attempts % 5 == 0:
                await page.wait_for_timeout(2000)
        
        # Cerrar modal
        try:
            boton_cerrar = await page.query_selector('div[role="dialog"] button[aria-label*="Cerrar"], div[role="dialog"] button[aria-label*="Close"], div[role="dialog"] svg[aria-label*="Cerrar"], div[role="dialog"] svg[aria-label*="Close"]')
            if boton_cerrar:
                await boton_cerrar.click()
                await page.wait_for_timeout(1000)
        except Exception as e:
            logger.debug(f"No se pudo cerrar modal: {e}")
        
        comentarios = list(comentarios_dict.values())
        print(f"💬 Comentarios únicos encontrados en modal: {len(comentarios)}")
        return comentarios
        
    except Exception as e:
        logger.error(f"Error extrayendo comentarios en modal: {e}")
        return []

async def procesar_comentarios_en_modal(page, comentarios_dict, url_post):
    """Procesar comentarios visibles en el modal actual"""
    try:
        # Selectores específicos para modal de comentarios
        selectores_modal = [
            'div[role="dialog"] span[dir="auto"] a[href^="/"]',
            'div[role="dialog"] div div span a[href^="/"][href$="/"]',
            'div[role="dialog"] section div span a',
            'div[role="dialog"] a[href^="/"][role="link"]',
            'div[role="dialog"] h3 a[href^="/"]',
            'div[role="dialog"] div[style*="flex"] a[href^="/"]'
        ]
        
        elementos_comentarios = []
        for selector in selectores_modal:
            try:
                elementos = await page.query_selector_all(selector)
                if elementos:
                    # Filtrar elementos válidos
                    elementos_validos = []
                    for elemento in elementos:
                        try:
                            href = await elemento.get_attribute("href")
                            if href and href.startswith('/') and href.endswith('/'):
                                username = href.strip('/').split('/')[0]
                                # Evitar links que no son de usuarios
                                if username not in ['p', 'reel', 'tv', 'stories', 'explore', 'accounts']:
                                    elementos_validos.append(elemento)
                        except:
                            continue
                    
                    if elementos_validos:
                        elementos_comentarios = elementos_validos
                        print(f"  ✓ Encontrados {len(elementos_comentarios)} comentarios en modal con: {selector}")
                        break
            except:
                continue
        
        if not elementos_comentarios:
            return
        
        # Procesar cada comentario en el modal
        for elemento in elementos_comentarios:
            try:
                href = await elemento.get_attribute("href")
                if not href or not href.startswith('/'):
                    continue
                
                username = href.strip('/').split('/')[0]
                if username in ['p', 'reel', 'tv', 'stories', 'explore', 'accounts'] or username == "":
                    continue
                
                # Evitar duplicados
                if username in comentarios_dict:
                    continue
                
                nombre_mostrado = await elemento.inner_text()
                url_perfil = f"https://www.instagram.com/{username}/"
                
                # Buscar imagen de perfil en el modal
                url_foto = ""
                try:
                    contenedor_padre = await elemento.evaluate_handle("""
                        element => {
                            let current = element.parentElement;
                            let attempts = 0;
                            while (current && attempts < 6) {
                                const img = current.querySelector('img[src*="profile"]') || 
                                          current.querySelector('img:not([src*="data:"])');
                                if (img && img.src && !img.src.startsWith('data:')) {
                                    return current;
                                }
                                current = current.parentElement;
                                attempts++;
                            }
                            return element.parentElement;
                        }
                    """)
                    
                    if contenedor_padre:
                        img_element = await contenedor_padre.query_selector('img')
                        if img_element:
                            url_foto = await img_element.get_attribute("src") or ""
                except Exception as img_error:
                    logger.debug(f"No se pudo obtener imagen para {username} en modal: {img_error}")
                
                comentarios_dict[username] = {
                    "nombre_usuario": nombre_mostrado or username,
                    "username_usuario": username,
                    "link_usuario": url_perfil,
                    "foto_usuario": url_foto if url_foto and not url_foto.startswith("data:") else "",
                    "post_url": url_post
                }
                
            except Exception as e:
                logger.warning(f"Error procesando comentario en modal: {e}")
                continue
                
    except Exception as e:
        logger.warning(f"Error procesando comentarios en modal: {e}")

async def procesar_comentarios_en_post(page, comentarios_dict, url_post):
    """Procesar comentarios visibles en el post actual"""
    try:
        # Selectores mejorados para encontrar comentarios
        selectores_comentarios = [
            'article section div div div div span[dir="auto"] a',
            'section div span[dir="auto"] a[href^="/"]',
            'div[role="button"] span[dir="auto"] a',
            'span:has(a[href^="/"][href$="/"])',
            'article a[href^="/"][href$="/"]',
            'section a[href^="/"][href$="/"]',
            # Selectores más específicos
            'div[style*="padding"] a[href^="/"]',
            'span a[href^="/"][role="link"]'
        ]
        
        elementos_comentarios = []
        for selector in selectores_comentarios:
            try:
                elementos = await page.query_selector_all(selector)
                if elementos:
                    # Filtrar elementos que parecen ser comentarios reales
                    elementos_validos = []
                    for elemento in elementos:
                        try:
                            href = await elemento.get_attribute("href")
                            if href and href.startswith('/') and href.endswith('/'):
                                username = href.strip('/').split('/')[0]
                                # Evitar links de posts, reels, etc.
                                if username not in ['p', 'reel', 'tv', 'stories', 'explore']:
                                    elementos_validos.append(elemento)
                        except:
                            continue
                    
                    if elementos_validos:
                        elementos_comentarios = elementos_validos
                        print(f"  ✓ Encontrados {len(elementos_comentarios)} comentarios con: {selector}")
                        break
            except:
                continue
        
        if not elementos_comentarios:
            return
        
        # Procesar cada comentario
        for elemento in elementos_comentarios:
            try:
                href = await elemento.get_attribute("href")
                if not href or not href.startswith('/'):
                    continue
                
                username = href.strip('/').split('/')[0]
                if username in ['p', 'reel', 'tv', 'stories', 'explore'] or username == "":
                    continue
                
                # Evitar duplicados
                if username in comentarios_dict:
                    continue
                
                nombre_mostrado = await elemento.inner_text()
                url_perfil = f"https://www.instagram.com/{username}/"
                
                # Buscar imagen de perfil del comentarista
                url_foto = ""
                try:
                    # Buscar en el contenedor padre
                    contenedor_padre = await elemento.evaluate_handle("""
                        element => {
                            // Buscar hacia arriba en el DOM hasta encontrar un contenedor con imagen
                            let current = element.parentElement;
                            let attempts = 0;
                            while (current && attempts < 5) {
                                const img = current.querySelector('img');
                                if (img && img.src && !img.src.startsWith('data:')) {
                                    return current;
                                }
                                current = current.parentElement;
                                attempts++;
                            }
                            return element.parentElement;
                        }
                    """)
                    
                    if contenedor_padre:
                        img_element = await contenedor_padre.query_selector('img')
                        if img_element:
                            url_foto = await img_element.get_attribute("src") or ""
                except Exception as img_error:
                    logger.debug(f"No se pudo obtener imagen para {username}: {img_error}")
                
                comentarios_dict[username] = {
                    "nombre_usuario": nombre_mostrado or username,
                    "username_usuario": username,
                    "link_usuario": url_perfil,
                    "foto_usuario": url_foto if url_foto and not url_foto.startswith("data:") else "",
                    "post_url": url_post
                }
                
            except Exception as e:
                logger.warning(f"Error procesando comentario individual: {e}")
                continue
                
    except Exception as e:
        logger.warning(f"Error procesando comentarios: {e}")

async def scrap_comentadores_instagram(page, perfil_url, username, max_posts=5):
    """Scrapear usuarios que comentaron los posts del usuario"""
    print(f"\n💬 Extrayendo comentarios de los últimos {max_posts} posts...")
    
    try:
        await page.goto(perfil_url)
        await page.wait_for_timeout(3000)
        
        urls_posts = await extraer_posts_del_perfil(page, max_posts)
        
        comentarios = []
        for i, url_post in enumerate(urls_posts, 1):
            print(f"\n🔍 Procesando comentarios del post {i}/{len(urls_posts)}")
            
            # Intentar extracción normal primero
            comentarios_post = await extraer_comentarios_post(page, url_post, i)
            
            # Si no hay comentarios, intentar con modal
            if not comentarios_post:
                print(f"  🔄 Intentando extracción en modal...")
                comentarios_post = await extraer_comentarios_en_modal(page, url_post, i)
            
            comentarios.extend(comentarios_post)
            
            # Rate limiting cada 3 posts
            if i % 3 == 0:
                print(f"⏳ Pausa de rate limiting después de {i} posts...")
                await asyncio.sleep(3)
            else:
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
