def guardar_resultados(username, datos_usuario, seguidores, seguidos, comentadores, platform="x"):
    import pandas as pd
    import os

    id_usuario = 1
    datos_usuario_df = pd.DataFrame([{
        'id_usuario': id_usuario,
        'nombre_usuario': datos_usuario['nombre_completo'],
        'username': datos_usuario['username'],
        'url_usuario': datos_usuario['url_usuario'],
        'url_foto_perfil': datos_usuario['foto_perfil']
    }])

    def crear_df(lista, tipo):
        df = pd.DataFrame()
        if tipo == "seguidores":
            df = pd.DataFrame([{
                'id_seguidor': i + 1,
                'id_usuario_principal': id_usuario,
                'nombre_seguidor': u['nombre_usuario'],
                'username_seguidor': u['username_usuario'],
                'url_seguidor': u['link_usuario'],
                'url_foto_perfil_seguidor': u['foto_usuario']
            } for i, u in enumerate(lista)])
        elif tipo == "seguidos":
            df = pd.DataFrame([{
                'id_seguido': i + 1,
                'id_usuario_principal': id_usuario,
                'nombre_seguido': u['nombre_usuario'],
                'username_seguido': u['username_usuario'],
                'url_seguido': u['link_usuario'],
                'url_foto_perfil_seguido': u['foto_usuario']
            } for i, u in enumerate(lista)])
        elif tipo == "comentadores":
            df = pd.DataFrame([{
                'id_comentador': i + 1,
                'id_usuario_principal': id_usuario,
                'nombre_comentador': u['nombre_usuario'],
                'username_comentador': u['username_usuario'],
                'url_comentador': u['link_usuario'],
                'url_foto_perfil_comentador': u['foto_usuario'],
                'url_post': u.get('post_url', '')
            } for i, u in enumerate(lista)])
        return df

    df_seguidores = crear_df(seguidores, "seguidores")
    df_seguidos = crear_df(seguidos, "seguidos")
    df_comentadores = crear_df(comentadores, "comentadores")

    os.makedirs('data/output', exist_ok=True)
    base = f"{platform}_scraper_{username}"
    archivo_excel = f"data/output/{base}.xlsx"

    # Write to Excel/CSV and capture output result without early return
    output_result = None
    try:
        with pd.ExcelWriter(archivo_excel, engine='openpyxl') as writer:
            datos_usuario_df.to_excel(writer, sheet_name="Usuario", index=False)
            if not df_seguidores.empty:
                df_seguidores.to_excel(writer, sheet_name="Seguidores", index=False)
            if not df_seguidos.empty:
                df_seguidos.to_excel(writer, sheet_name="Seguidos", index=False)
            if not df_comentadores.empty:
                df_comentadores.to_excel(writer, sheet_name="Comentadores", index=False)
        print(f"\n✅ Archivo Excel creado: {archivo_excel}")
        output_result = archivo_excel
    except ImportError:
        print("\n⚠️ No se pudo guardar como Excel. Usando CSV...")
        datos_usuario_df.to_csv(f"data/output/{base}_usuario.csv", index=False)
        if not df_seguidores.empty:
            df_seguidores.to_csv(f"data/output/{base}_seguidores.csv", index=False)
        if not df_seguidos.empty:
            df_seguidos.to_csv(f"data/output/{base}_seguidos.csv", index=False)
        if not df_comentadores.empty:
            df_comentadores.to_csv(f"data/output/{base}_comentadores.csv", index=False)
        output_result = base

    # Alternate API insertion mode
    save_to_api = str(os.getenv('SAVE_TO_API', '0')).lower() in ('1', 'true', 'yes')
    if save_to_api:
        try:
            from scripts.api_client import create_or_update_profile, create_relationship, create_post, create_comment
        except Exception as e:
            print(f"\n⚠️ No se pudo cargar api_client. Omitiendo envío a API. Detalle: {e}")
        else:
            try:
                # Owner profile
                owner_username = datos_usuario.get('username')
                owner_full_name = datos_usuario.get('nombre_completo')
                owner_url = datos_usuario.get('url_usuario')
                owner_photo = datos_usuario.get('foto_perfil')
                create_or_update_profile(platform, owner_username, owner_full_name, owner_url, owner_photo)

                # Followers
                for u in seguidores or []:
                    uname = u.get('username_usuario')
                    if not uname:
                        continue
                    # Upsert related profile with metadata first
                    create_or_update_profile(platform, uname, u.get('nombre_usuario'), u.get('link_usuario'), u.get('foto_usuario'))
                    create_relationship(platform, owner_username, uname, 'follower')

                # Following
                for u in seguidos or []:
                    uname = u.get('username_usuario')
                    if not uname:
                        continue
                    create_or_update_profile(platform, uname, u.get('nombre_usuario'), u.get('link_usuario'), u.get('foto_usuario'))
                    create_relationship(platform, owner_username, uname, 'following')

                # Comments
                if comentadores:
                    urls = {c.get('post_url') for c in comentadores if c.get('post_url')}
                    for post_url in urls:
                        create_post(platform, owner_username, post_url)
                    for c in comentadores:
                        post_url = c.get('post_url')
                        commenter = c.get('username_usuario')
                        if post_url and commenter:
                            create_or_update_profile(platform, commenter, c.get('nombre_usuario'), c.get('link_usuario'), c.get('foto_usuario'))
                            create_comment(platform, post_url, commenter)
                print("\n✅ Envío a API completado")
            except Exception as e:
                print(f"\n❌ Error enviando a la API: {e}")

    # Optional DB insertion controlled by env var SAVE_TO_DB (fallback if not using API)
    save_to_db = (not save_to_api) and (str(os.getenv('SAVE_TO_DB', '0')).lower() in ('1', 'true', 'yes'))
    if save_to_db:
        try:
            from db.insert import get_conn, upsert_profile, add_relationship, add_post, add_comment
        except Exception as e:
            print(f"\n⚠️ No se pudo cargar helpers de DB (db/insert.py). Omitiendo inserción. Detalle: {e}")
        else:
            try:
                owner_username = datos_usuario.get('username')
                owner_full_name = datos_usuario.get('nombre_completo')
                owner_url = datos_usuario.get('url_usuario')
                owner_photo = datos_usuario.get('foto_perfil')

                followers_inserted = 0
                following_inserted = 0
                posts_inserted = 0
                comments_inserted = 0

                with get_conn() as conn:
                    with conn.cursor() as cur:
                        # Upsert main profile (with metadata)
                        upsert_profile(cur, platform, owner_username, owner_full_name, owner_url, owner_photo)

                        # Pre-upsert followers with available metadata, then relationships
                        for u in seguidores or []:
                            try:
                                uname = u.get('username_usuario')
                                if uname:
                                    upsert_profile(
                                        cur,
                                        platform,
                                        uname,
                                        u.get('nombre_usuario'),
                                        u.get('link_usuario'),
                                        u.get('foto_usuario')
                                    )
                                    rel_id = add_relationship(cur, platform, owner_username, uname, 'follower')
                                    if rel_id is not None:
                                        followers_inserted += 1
                            except Exception as e:
                                print(f"⚠️ Error insertando seguidor @{u.get('username_usuario')}: {e}")

                        # Pre-upsert following with available metadata, then relationships
                        for u in seguidos or []:
                            try:
                                uname = u.get('username_usuario')
                                if uname:
                                    upsert_profile(
                                        cur,
                                        platform,
                                        uname,
                                        u.get('nombre_usuario'),
                                        u.get('link_usuario'),
                                        u.get('foto_usuario')
                                    )
                                    rel_id = add_relationship(cur, platform, owner_username, uname, 'following')
                                    if rel_id is not None:
                                        following_inserted += 1
                            except Exception as e:
                                print(f"⚠️ Error insertando seguido @{u.get('username_usuario')}: {e}")

                        # Comments (ensure posts exist first)
                        if comentadores:
                            # Create posts (unique by URL)
                            urls = {c.get('post_url') for c in comentadores if c.get('post_url')}
                            for post_url in urls:
                                try:
                                    post_id = add_post(cur, platform, owner_username, post_url)
                                    if post_id is not None:
                                        posts_inserted += 1
                                except Exception as e:
                                    print(f"⚠️ Error insertando post {post_url}: {e}")

                            # Upsert commenters with metadata, then add comments
                            for c in comentadores:
                                try:
                                    post_url = c.get('post_url')
                                    commenter = c.get('username_usuario')
                                    if post_url and commenter:
                                        upsert_profile(
                                            cur,
                                            platform,
                                            commenter,
                                            c.get('nombre_usuario'),
                                            c.get('link_usuario'),
                                            c.get('foto_usuario')
                                        )
                                        cid = add_comment(cur, platform, post_url, commenter)
                                        if cid is not None:
                                            comments_inserted += 1
                                except Exception as e:
                                    print(f"⚠️ Error insertando comentario de @{c.get('username_usuario')} en {c.get('post_url')}: {e}")

                print(f"\n✅ Inserción en DB completada ({platform}):")
                print(f"   - Seguidores nuevos: {followers_inserted}")
                print(f"   - Seguidos nuevos: {following_inserted}")
                print(f"   - Posts nuevos: {posts_inserted}")
                print(f"   - Comentarios nuevos: {comments_inserted}")
            except Exception as e:
                print(f"\n❌ Error general insertando en DB: {e}")

    return output_result
