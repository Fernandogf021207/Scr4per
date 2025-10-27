from io import BytesIO
from typing import Union
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ..schemas import ExportInput, MultiExportInput, ExportBlock

router = APIRouter()

@router.post("/export")
def export_to_excel(payload: Union[ExportInput, MultiExportInput]):
    try:
        # Normalize payload into a list of export blocks
        if isinstance(payload, MultiExportInput):
            blocks: list[ExportBlock] = payload.bloques or []
        else:
            # Single-objective backward-compatible path
            blocks = [ExportBlock(perfil_objetivo=payload.perfil_objetivo, perfiles_relacionados=payload.perfiles_relacionados)]

        rows = []
        first_objetivo_str_for_filename = None
        for block in blocks:
            objetivo = block.perfil_objetivo or {}
            relacionados = block.perfiles_relacionados or []

            objetivo_str = None
            for key in ["username", "nombre_usuario", "nombre_completo", "full_name", "profile_url", "url_usuario", "updated_at"]:
                if objetivo.get(key):
                    objetivo_str = str(objetivo.get(key))
                    break
            objetivo_str = objetivo_str or ""

            if first_objetivo_str_for_filename is None:
                first_objetivo_str_for_filename = objetivo_str

            for item in relacionados:
                tipo = item.get("tipo de relacion") or item.get("tipo") or ""
                rel_username = item.get("username") or item.get("username_usuario") or ""
                rel_name = item.get("full_name") or item.get("nombre_usuario") or ""
                rel_url = item.get("profile_url") or item.get("link_usuario") or ""
                if rel_username:
                    asociado = rel_username
                    if rel_name and rel_name != rel_username:
                        asociado = f"{rel_username} ({rel_name})"
                elif rel_name:
                    asociado = rel_name
                else:
                    asociado = rel_url or ""
                rows.append({
                    "Perfil objetivo": objetivo_str,
                    "Tipo de relacion": tipo,
                    "Perfiles asociados": asociado,
                })

        df = pd.DataFrame(rows, columns=["Perfil objetivo", "Tipo de relacion", "Perfiles asociados"])
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="export")
        output.seek(0)

        # Build filename
        if len(blocks) > 1:
            filename = "export_multi.xlsx"
        else:
            filename = f"export_{first_objetivo_str_for_filename or 'perfil'}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))