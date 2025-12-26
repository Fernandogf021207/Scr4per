import asyncio
import json
from typing import List
from fastapi import Request

class EventManager:
    """
    Administra las colas de mensajes para Server-Sent Events (SSE).
    Patrón Pub/Sub simple en memoria.
    """
    def __init__(self):
        # Lista de colas activas (usuarios escuchando)
        self.listeners: List[asyncio.Queue] = []

    async def subscribe(self, request: Request):
        """
        Generador que entrega mensajes al cliente mientras la conexión siga viva.
        """
        queue = asyncio.Queue()
        self.listeners.append(queue)
        try:
            while True:
                # Verificar si el cliente cerró la conexión
                if await request.is_disconnected():
                    break
                
                # Esperar mensaje
                data = await queue.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in self.listeners:
                self.listeners.remove(queue)

    async def broadcast_status(self, id_identidad: int, estado: str, id_caso: int):
        """
        Envía una actualización a todos los clientes conectados.
        Formato JSON simple.
        """
        message = json.dumps({
            "event": "status_update",
            "id_identidad": id_identidad,
            "id_caso": id_caso,
            "nuevo_estado": estado
        })
        
        # Enviar a todas las colas activas
        # Usamos una copia de la lista para evitar problemas si se desconectan durante la iteración
        for queue in list(self.listeners):
            await queue.put(message)

# Instancia Global (Singleton)
event_manager = EventManager()
