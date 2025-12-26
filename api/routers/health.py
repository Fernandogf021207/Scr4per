from fastapi import APIRouter, HTTPException
from ..db import get_conn
from src.utils.ftp_storage import get_ftp_client

router = APIRouter()

@router.get("/health")
def health():
    """
    Health check endpoint con verificaciones profundas de DB y FTP.
    
    Returns:
        200: Si DB y FTP están operativos
        503: Si algún servicio falla
        
    Response:
        {
            "status": "ok" | "degraded" | "error",
            "services": {
                "database": {"status": "ok" | "error", "message": str},
                "ftp": {"status": "ok" | "error", "message": str}
            }
        }
    """
    db_status = {"status": "error", "message": ""}
    ftp_status = {"status": "error", "message": ""}
    overall_status = "error"
    
    # Check Database
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                result = cur.fetchone()
                if result and result["ok"] == 1:
                    db_status = {"status": "ok", "message": "Database connection successful"}
                else:
                    db_status = {"status": "error", "message": "Unexpected database response"}
    except Exception as e:
        db_status = {"status": "error", "message": f"Database error: {str(e)}"}
    
    # Check FTP
    try:
        ftp_client = get_ftp_client()
        if ftp_client.check_connection():
            ftp_status = {"status": "ok", "message": "FTP connection successful"}
        else:
            ftp_status = {"status": "error", "message": "FTP connection failed"}
    except Exception as e:
        ftp_status = {"status": "error", "message": f"FTP error: {str(e)}"}
    
    # Determine overall status
    if db_status["status"] == "ok" and ftp_status["status"] == "ok":
        overall_status = "ok"
        status_code = 200
    elif db_status["status"] == "ok" or ftp_status["status"] == "ok":
        overall_status = "degraded"
        status_code = 503
    else:
        overall_status = "error"
        status_code = 503
    
    response = {
        "status": overall_status,
        "services": {
            "database": db_status,
            "ftp": ftp_status
        }
    }
    
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=response)
    
    return response