import asyncio
import json
from datetime import datetime
from typing import List, Optional
from fastapi import Request


# ---------------------------------------------------------------------------
# Pasos estándar del proceso de análisis (para barra de progreso)
# ---------------------------------------------------------------------------
ANALYSIS_STEPS = [
    "iniciando",
    "accediendo_perfil",
    "perfil_obtenido",
    "navegando_seguidores",
    "seguidores_obtenidos",
    "navegando_seguidos",
    "seguidos_obtenidos",
    "navegando_amigos",
    "amigos_obtenidos",
    "analizando_comentarios",
    "comentarios_obtenidos",
    "analizando_reacciones",
    "reacciones_obtenidas",
    "guardando_datos",
    "generando_grafo",
    "completado",
]

STEP_INDEX = {step: i for i, step in enumerate(ANALYSIS_STEPS)}
TOTAL_STEPS = len(ANALYSIS_STEPS)

# Mensajes de usuario por paso
STEP_LABELS = {
    "iniciando":              "Iniciando análisis…",
    "accediendo_perfil":      "Accediendo al perfil…",
    "perfil_obtenido":        "Perfil obtenido",
    "navegando_seguidores":   "Navegando a seguidores…",
    "seguidores_obtenidos":   "Seguidores obtenidos",
    "navegando_seguidos":     "Navegando a seguidos…",
    "seguidos_obtenidos":     "Seguidos obtenidos",
    "navegando_amigos":       "Navegando a lista de amigos…",
    "amigos_obtenidos":       "Amigos obtenidos",
    "analizando_comentarios": "Analizando comentarios…",
    "comentarios_obtenidos":  "Comentarios procesados",
    "analizando_reacciones":  "Analizando reacciones…",
    "reacciones_obtenidas":   "Reacciones procesadas",
    "guardando_datos":        "Guardando en base de datos…",
    "generando_grafo":        "Generando grafo de vínculos…",
    "completado":             "Análisis completado",
    # estados de error / BD
    "procesando":             "Procesando…",
    "analizado":              "Análisis finalizado",
    "error":                  "Error en el análisis",
}


class EventManager:
    """
    Administra las colas de mensajes para Server-Sent Events (SSE).
    Patrón Pub/Sub simple en memoria.

    Emite dos tipos de eventos:
      - status_update : cambio de estado global (procesando, analizado, error)
      - progress      : paso granular dentro del análisis (con step_index / total)
    """

    def __init__(self):
        self.listeners: List[asyncio.Queue] = []

    # ------------------------------------------------------------------
    # Suscripción
    # ------------------------------------------------------------------
    async def subscribe(self, request: Request):
        """Generador SSE que entrega mensajes mientras la conexión esté viva."""
        queue: asyncio.Queue = asyncio.Queue()
        self.listeners.append(queue)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat: mantiene la conexión viva en proxies/load-balancers
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in self.listeners:
                self.listeners.remove(queue)

    # ------------------------------------------------------------------
    # Broadcast interno
    # ------------------------------------------------------------------
    async def _broadcast(self, payload: dict):
        payload.setdefault("ts", datetime.utcnow().isoformat())
        message = json.dumps(payload, ensure_ascii=False)
        for queue in list(self.listeners):
            await queue.put(message)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    async def broadcast_status(self, id_identidad: int, estado: str, id_caso: Optional[int] = None):
        """Cambio de estado global (procesando → analizado / error)."""
        await self._broadcast({
            "event": "status_update",
            "id_identidad": id_identidad,
            "id_caso": id_caso,
            "nuevo_estado": estado,
            "label": STEP_LABELS.get(estado, estado),
        })

    async def broadcast_progress(
        self,
        id_identidad: int,
        step: str,
        detail: Optional[str] = None,
        count: Optional[int] = None,
        id_caso: Optional[int] = None,
    ):
        """
        Evento granular de progreso durante el análisis.

        Payload enviado al frontend:
        {
          "event":        "progress",
          "id_identidad": 42,
          "id_caso":      7,
          "step":         "seguidores_obtenidos",   ← clave interna
          "step_index":   4,                        ← posición 0‑based
          "total_steps":  16,
          "pct":          25,                       ← porcentaje 0‑100
          "label":        "Seguidores obtenidos",   ← texto para mostrar
          "detail":       "312 seguidores encontrados",
          "count":        312,                      ← número relevante (opcional)
          "ts":           "2026-03-09T12:00:00"
        }
        """
        step_index = STEP_INDEX.get(step, 0)
        pct = round(step_index / (TOTAL_STEPS - 1) * 100) if TOTAL_STEPS > 1 else 100
        await self._broadcast({
            "event":        "progress",
            "id_identidad": id_identidad,
            "id_caso":      id_caso,
            "step":         step,
            "step_index":   step_index,
            "total_steps":  TOTAL_STEPS,
            "pct":          pct,
            "label":        STEP_LABELS.get(step, step),
            "detail":       detail or STEP_LABELS.get(step, step),
            "count":        count,
        })


# Instancia Global (Singleton)
event_manager = EventManager()

