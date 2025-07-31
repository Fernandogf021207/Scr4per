import pandas as pd
import os

def guardar_resultados(username, datos_usuario, seguidores, seguidos, comentadores, platform="x"):
    """Guardar los resultados en Excel o CSV, compatible con Instagram y X"""
    usuario_id = 1
    
    # Map platform-specific keys to unified column names
    key_mapping = {
        "x": {
            "user_name_key": "nombre_completo",
            "follower_name_key": "nombre_usuario",
            "follower_username_key": "username_usuario",
            "follower_url_key": "link_usuario",
            "follower_photo_key": "foto_usuario",
            "following_name_key": "nombre_usuario",
            "following_username_key": "username_usuario",
            "following_url_key": "link_usuario",
            "following_photo_key": "foto_usuario",
            "commenter_name_key": "nombre_usuario",
            "commenter_username_key": "username_usuario",
            "commenter_url_key": "link_usuario",
            "commenter_photo_key": "foto_usuario",
            "commenter_post_url_key": "post_url"
        },
        "instagram": {
            "user_name_key": "nombre_completo",
            "follower_name_key": "nombre_usuario",
            "follower_username_key": "username_usuario",
            "follower_url_key": "link_usuario",
            "follower_photo_key": "foto_usuario",
            "following_name_key": "nombre_usuario",
            "following_username_key": "username_usuario",
            "following_url_key": "link_usuario",
            "following_photo_key": "foto_usuario",
            "commenter_name_key": "nombre_mostrado",
            "commenter_username_key": "username",
            "commenter_url_key": "url_perfil",
            "commenter_photo_key": "url_foto",
            "commenter_post_url_key": "url_post"
        }
    }

    keys = key_mapping.get(platform.lower(), key_mapping["x"])

    # Usuario DataFrame
    datos_usuario_df = {
        'id_usuario': [usuario_id],
        'nombre_usuario': [datos_usuario[keys["user_name_key"]]],
        'username': [datos_usuario['username']],
        'url_usuario': [datos_usuario['url_usuario']],
        'url_foto_perfil': [datos_usuario['url_foto_perfil']]
    }
    
    # Seguidores DataFrame
    datos_seguidores = {
        'id_seguidor': [],
        'id_usuario_principal': [],
        'nombre_seguidor': [],
        'username_seguidor': [],
        'url_seguidor': [],
        'url_foto_perfil_seguidor': []
    }
    
    # Seguidos DataFrame
    datos_seguidos = {
        'id_seguido': [],
        'id_usuario_principal': [],
        'nombre_seguido': [],
        'username_seguido': [],
        'url_seguido': [],
        'url_foto_perfil_seguido': []
    }
    
    # Comentadores DataFrame (named differently for Instagram and X)
    datos_comentadores = {
        'id_comentador': [],
        'id_usuario_principal': [],
        'nombre_comentador': [],
        'username_comentador': [],
        'url_comentador': [],
        'url_foto_perfil_comentador': [],
        'url_post': []
    }
    if platform.lower() == "instagram":
        datos_comentadores['post_id'] = []  # Instagram includes post_id

    # Populate Seguidores
    for i, seguidor in enumerate(seguidores, start=1):
        datos_seguidores['id_seguidor'].append(i)
        datos_seguidores['id_usuario_principal'].append(usuario_id)
        datos_seguidores['nombre_seguidor'].append(seguidor[keys["follower_name_key"]])
        datos_seguidores['username_seguidor'].append(seguidor[keys["follower_username_key"]])
        datos_seguidores['url_seguidor'].append(seguidor[keys["follower_url_key"]])
        datos_seguidores['url_foto_perfil_seguidor'].append(seguidor[keys["follower_photo_key"]])
    
    # Populate Seguidos
    for i, seguido in enumerate(seguidos, start=1):
        datos_seguidos['id_seguido'].append(i)
        datos_seguidos['id_usuario_principal'].append(usuario_id)
        datos_seguidos['nombre_seguido'].append(seguido[keys["following_name_key"]])
        datos_seguidos['username_seguido'].append(seguido[keys["following_username_key"]])
        datos_seguidos['url_seguido'].append(seguido[keys["following_url_key"]])
        datos_seguidos['url_foto_perfil_seguido'].append(seguido[keys["following_photo_key"]])
    
    # Populate Comentadores
    for i, comentador in enumerate(comentadores, start=1):
        datos_comentadores['id_comentador'].append(i)
        datos_comentadores['id_usuario_principal'].append(usuario_id)
        datos_comentadores['nombre_comentador'].append(comentador[keys["commenter_name_key"]])
        datos_comentadores['username_comentador'].append(comentador[keys["commenter_username_key"]])
        datos_comentadores['url_comentador'].append(comentador[keys["commenter_url_key"]])
        datos_comentadores['url_foto_perfil_comentador'].append(comentador[keys["commenter_photo_key"]])
        datos_comentadores['url_post'].append(comentador[keys["commenter_post_url_key"]])
        if platform.lower() == "instagram":
            datos_comentadores['post_id'].append(comentador.get('post_id', ''))

    df_usuario = pd.DataFrame(datos_usuario_df)
    df_seguidores = pd.DataFrame(datos_seguidores)
    df_seguidos = pd.DataFrame(datos_seguidos)
    df_comentadores = pd.DataFrame(datos_comentadores)
    
    # Adjust sheet name for Instagram
    commenter_sheet_name = 'Comentarios' if platform.lower() == "instagram" else 'Comentadores'
    nombre_base = f"{platform.lower()}_scraper_{username}"
    
    try:
        os.makedirs('data/output', exist_ok=True)
        nombre_archivo_excel = f"data/output/{nombre_base}.xlsx"
        with pd.ExcelWriter(nombre_archivo_excel, engine='openpyxl') as writer:
            df_usuario.to_excel(writer, sheet_name='Usuario', index=False)
            if not df_seguidores.empty:
                df_seguidores.to_excel(writer, sheet_name='Seguidores', index=False)
            if not df_seguidos.empty:
                df_seguidos.to_excel(writer, sheet_name='Seguidos', index=False)
            if not df_comentadores.empty:
                df_comentadores.to_excel(writer, sheet_name=commenter_sheet_name, index=False)
            
        print(f"\n✅ Archivo Excel creado: {nombre_archivo_excel}")
        print(f"📄 Página 'Usuario': {len(df_usuario)} registro")
        if not df_seguidores.empty:
            print(f"📄 Página 'Seguidores': {len(df_seguidores)} registros")
        if not df_seguidos.empty:
            print(f"📄 Página 'Seguidos': {len(df_seguidos)} registros")
        if not df_comentadores.empty:
            print(f"📄 Página '{commenter_sheet_name}': {len(df_comentadores)} registros")
        return nombre_archivo_excel
        
    except ImportError:
        print("\n⚠️ openpyxl no está instalado. Guardando como archivos CSV...")
        
        nombre_archivo = f"Archivos CSV creados para {username}"
        archivo_usuario = f"data/output/{nombre_base}_usuario.csv"
        df_usuario.to_csv(archivo_usuario, index=False)
        print(f"📄 Usuario: {archivo_usuario}")
        
        if not df_seguidores.empty:
            archivo_seguidores = f"data/output/{nombre_base}_seguidores.csv"
            df_seguidores.to_csv(archivo_seguidores, index=False)
            print(f"📄 Seguidores: {archivo_seguidores}")
        
        if not df_seguidos.empty:
            archivo_seguidos = f"data/output/{nombre_base}_seguidos.csv"
            df_seguidos.to_csv(archivo_seguidos, index=False)
            print(f"📄 Seguidos: {archivo_seguidos}")
        
        if not df_comentadores.empty:
            archivo_comentadores = f"data/output/{nombre_base}_{commenter_sheet_name.lower()}.csv"
            df_comentadores.to_csv(archivo_comentadores, index=False)
            print(f"📄 {commenter_sheet_name}: {archivo_comentadores}")
        
        return nombre_archivo