from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from ..db import get_conn
from src.utils.ftp_storage import get_ftp_client

router = APIRouter()

@router.get("/health")
def health():
    """
    Health check profundo que verifica toda la infraestructura crítica.
    
    Verifica:
    1. Base de datos PostgreSQL (SELECT 1)
    2. FTP Storage (conexión y comando NOOP)
    
    Returns:
        200 OK: {"status": "ok", "database": "ok", "storage": "ok"}
        503 Service Unavailable: {"status": "degraded", "database": "ok", "storage": "disconnected"}
    """
    health_status = {
        "status": "ok",
        "database": "unknown",
        "storage": "unknown"
    }
    
    # Check 1: Database
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                result = cur.fetchone()["ok"]
                if result == 1:
                    health_status["database"] = "ok"
                else:
                    health_status["database"] = "error"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check 2: FTP Storage
    try:
        ftp_client = get_ftp_client()
        if ftp_client.check_connection():
            health_status["storage"] = "ok"
        else:
            health_status["storage"] = "disconnected"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["storage"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
    
    # Determinar código de respuesta
    if health_status["status"] == "degraded":
        return JSONResponse(
            status_code=503,
            content=health_status
        )
    
    return health_status
