import pandas as pd
import os

def guardar_resultados(username, datos_usuario, seguidores, seguidos, comentadores):
    """Guardar los resultados en Excel o CSV"""
    usuario_id = 1
    datos_usuario_df = {
        'id_usuario': [usuario_id],
        'nombre_usuario': [datos_usuario['nombre_completo']],
        'username': [datos_usuario['username']],
        'url_usuario': [datos_usuario['url_usuario']],
        'url_foto_perfil': [datos_usuario['foto_perfil']]
    }
    
    datos_seguidores = {
        'id_seguidor': [],
        'id_usuario_principal': [],
        'nombre_seguidor': [],
        'username_seguidor': [],
        'url_seguidor': [],
        'url_foto_perfil_seguidor': []
    }
    
    datos_seguidos = {
        'id_seguido': [],
        'id_usuario_principal': [],
        'nombre_seguido': [],
        'username_seguido': [],
        'url_seguido': [],
        'url_foto_perfil_seguido': []
    }
    
    datos_comentadores = {
        'id_comentador': [],
        'id_usuario_principal': [],
        'nombre_comentador': [],
        'username_comentador': [],
        'url_comentador': [],
        'url_foto_perfil_comentador': [],
        'url_post': []
    }
    
    for i, seguidor in enumerate(seguidores, start=1):
        datos_seguidores['id_seguidor'].append(i)
        datos_seguidores['id_usuario_principal'].append(usuario_id)
        datos_seguidores['nombre_seguidor'].append(seguidor['nombre_usuario'])
        datos_seguidores['username_seguidor'].append(seguidor['username_usuario'])
        datos_seguidores['url_seguidor'].append(seguidor['link_usuario'])
        datos_seguidores['url_foto_perfil_seguidor'].append(seguidor['foto_usuario'])
    
    for i, seguido in enumerate(seguidos, start=1):
        datos_seguidos['id_seguido'].append(i)
        datos_seguidos['id_usuario_principal'].append(usuario_id)
        datos_seguidos['nombre_seguido'].append(seguido['nombre_usuario'])
        datos_seguidos['username_seguido'].append(seguido['username_usuario'])
        datos_seguidos['url_seguido'].append(seguido['link_usuario'])
        datos_seguidos['url_foto_perfil_seguido'].append(seguido['foto_usuario'])
    
    for i, comentador in enumerate(comentadores, start=1):
        datos_comentadores['id_comentador'].append(i)
        datos_comentadores['id_usuario_principal'].append(usuario_id)
        datos_comentadores['nombre_comentador'].append(comentador['nombre_usuario'])
        datos_comentadores['username_comentador'].append(comentador['username_usuario'])
        datos_comentadores['url_comentador'].append(comentador['link_usuario'])
        datos_comentadores['url_foto_perfil_comentador'].append(comentador['foto_usuario'])
        datos_comentadores['url_post'].append(comentador['post_url'])
    
    df_usuario = pd.DataFrame(datos_usuario_df)
    df_seguidores = pd.DataFrame(datos_seguidores)
    df_seguidos = pd.DataFrame(datos_seguidos)
    df_comentadores = pd.DataFrame(datos_comentadores)
    
    nombre_base = f"x_scraper_{username}"
    
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
                df_comentadores.to_excel(writer, sheet_name='Comentadores', index=False)
            
        print(f"\n✅ Archivo Excel creado: {nombre_archivo_excel}")
        print(f"📄 Página 'Usuario': {len(df_usuario)} registro")
        if not df_seguidores.empty:
            print(f"📄 Página 'Seguidores': {len(df_seguidores)} registros")
        if not df_seguidos.empty:
            print(f"📄 Página 'Seguidos': {len(df_seguidos)} registros")
        if not df_comentadores.empty:
            print(f"📄 Página 'Comentadores': {len(df_comentadores)} registros")
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
            archivo_comentadores = f"data/output/{nombre_base}_comentadores.csv"
            df_comentadores.to_csv(archivo_comentadores, index=False)
            print(f"📄 Comentadores: {archivo_comentadores}")
        
        return nombre_archivo