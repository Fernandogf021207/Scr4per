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
        return archivo_excel
    except ImportError:
        print("\n⚠️ No se pudo guardar como Excel. Usando CSV...")
        datos_usuario_df.to_csv(f"data/output/{base}_usuario.csv", index=False)
        if not df_seguidores.empty:
            df_seguidores.to_csv(f"data/output/{base}_seguidores.csv", index=False)
        if not df_seguidos.empty:
            df_seguidos.to_csv(f"data/output/{base}_seguidos.csv", index=False)
        if not df_comentadores.empty:
            df_comentadores.to_csv(f"data/output/{base}_comentadores.csv", index=False)
        return base
