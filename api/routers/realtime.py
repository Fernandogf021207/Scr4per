from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from src.utils.event_manager import event_manager

router = APIRouter(prefix="/realtime", tags=["Real Time Updates"])

@router.get("/sse/status")
async def sse_status_stream(request: Request):
    """
    Endpoint de Server-Sent Events.
    El Frontend se conecta aquí y mantiene la conexión abierta para recibir actualizaciones.
    """
    return StreamingResponse(
        event_manager.subscribe(request),
        media_type="text/event-stream"
    )
