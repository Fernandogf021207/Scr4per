# Plan de acción: Endpoint POST /multi-scrape (schema_version=2)

Este documento define el plan para implementar el nuevo endpoint POST `/multi-scrape`, que orquesta scraping concurrente de múltiples perfiles por plataforma (facebook, instagram, x), normaliza el resultado, persiste perfiles/relaciones en PostgreSQL de forma idempotente y devuelve un payload unificado estable para frontend y multi-related.

## Objetivos y alcance

- Endpoint único: POST `/multi-scrape`.
- Entrada: lista de roots (1..5) con `platform`, `username`, `max_photos?` y opciones globales `headless?`, `max_concurrency?`, `persist?`.
- Salida: `schema_version=2`, `root_profiles`, `profiles` únicos con `sources`, `relations` aplanadas, `warnings`, `meta` con métricas.
- Persistencia obligatoria e idempotente: esquemas `red_facebook`, `red_instagram`, `red_x`; tablas `profiles`, `relationships`; enums y constraints según reglas.
- Concurrencia controlada con Semaphore (1..3). Un navegador Playwright, múltiples contextos.

## Diseño técnico (alto nivel)

- Router FastAPI: `api/routers/multi_scrape.py`
  - POST `/multi-scrape` recibe `MultiScrapeRequest` y llama a `api.services.multi_scrape.multi_scrape_execute`.
  - Valida tamaños, regex, rangos; construye defaults de concurrencia.
  - Manejo de errores y mapeo de códigos: 422, 400 opcional (falta de storage_state), 500 para no controlados.

- Servicio orquestador: `api/services/multi_scrape.py`
  - Función principal: `async def multi_scrape_execute(req: MultiScrapeRequest|dict) -> dict`.
  - Abre un único Chromium. Crea un contexto por root y, para cada lista (followers/following/friends), usa un contexto fresco.
  - Limita concurrencia con `asyncio.Semaphore(max_concurrency)`.
  - Usa adaptadores por plataforma (interfaces):
    - `get_root_profile(username)` → dict: username, full_name?, profile_url, photo_url?
    - `get_followers(username, max_photos?)` → list[dict]
    - `get_following(username, max_photos?)` → list[dict]
    - `get_friends(username)` (solo facebook) → list[dict]
  - Normaliza usernames/URLs y deduplica perfiles por `(platform, username)` acumulando `sources`.
  - Persistencia por root dentro de una transacción; idempotente.
  - Warnings por root ante fallos parciales; tiempos por root en `meta.roots_timings`.

- Persistencia (repositorio DB)
  - Reutilizar `api.repositories.upsert_profile(cur, platform, username, ...)` y `api.repositories.add_relationship(cur, platform, owner_username, related_username, rel_type)`.
  - Transacción por root: `conn = get_conn(); cur = conn.cursor(); ... conn.commit()`; `ON CONFLICT DO NOTHING` en relaciones.
  - No insertar `source==target`. Ignorar usernames inválidos tras normalización.

- Sesiones y storage-state
  - Validar storage-state por plataforma con `api.deps.storage_state_for(platform)`.
  - Política: estricto (400 STORAGE_STATE_MISSING) o laxa (warning y omitir root). Inicialmente: laxa con `warnings` y `roots_processed` menor si falta.

- Logging y observabilidad
  - `logger.info` al inicio/fin por root; métricas por lista (tamaño, duración), scrolls.
  - `logger.warning` para errores recuperables (timeouts, listas vacías inesperadas).
  - `logger.exception` para fallos no recuperables por root (sin tumbar el proceso completo).
  - `meta.build_ms`, `meta.roots_timings`, `meta.max_concurrency`.

## Contratos de datos

- Request `MultiScrapeRequest`
  - `roots: List[Root]` (1..5)
    - `platform: 'facebook'|'instagram'|'x'`
    - `username: str` (2..60; regex `[A-Za-z0-9._-]+`)
    - `max_photos?: int` (0..50; default 5)
  - `headless?: bool` (default true)
  - `max_concurrency?: int` (1..3; default 1 si `len(roots)==1`, 3 si >1)
  - `persist?: bool` (default true)

- Respuesta 200 OK `MultiScrapeResponse` (schema_version=2)
  - `schema_version: 2`
  - `root_profiles: List[str]` con formato `"platform:username"` en orden de procesamiento
  - `profiles: List[ProfileItem]`
    - `platform, username, full_name?, profile_url, photo_url?, sources: List[str]`
  - `relations: List[RelationItem]`
    - `{ platform, source, target, type }` con `type ∈ {'follower','following','friend'}`
  - `warnings: List[{code,message}]`
  - `meta: { schema_version, roots_requested, roots_processed, generated_at, build_ms, roots_timings: { [rootId]: {seconds} }, max_concurrency }`

- Errores
  - 422 `VALIDATION_ERROR`: payload inválido (roots vacío, >5, username inválido, etc.)
  - 400 `STORAGE_STATE_MISSING`: si se adopta política estricta por plataforma sin sesión disponible
  - 500 `ORCHESTRATOR_ERROR`: excepciones no controladas en nivel superior

## Validaciones y normalización

- Validar `roots`: 1..5
- `platform` ∈ {facebook, instagram, x}
- `username` regex `[A-Za-z0-9._-]{2,60}`
- `max_photos` 0..50
- Defaults de `headless`, `max_concurrency`, `persist`
- Normalización de URL/username por plataforma (reutilizar utilidades en `src/utils/url.py` y reglas en cada adapter).

## Flujo por root (paso a paso)

1. Validar storage-state; si falta, registrar warning y saltar root (o 400 si política estricta).
2. `get_root_profile(username)`
3. Listas:
   - `followers = get_followers(username, max_photos)`
   - `following = get_following(username, max_photos)`
   - `friends = get_friends(username)` solo facebook
4. Normalizar y agregar a `profiles`:
   - Insertar root con `sources=[rootId]`
   - Para cada item de listas, agregar perfil o fusionar `sources` si ya existe
5. Construir `relations` aplanadas:
   - follower: `root → follower`
   - following: `root → followed`
   - friend (facebook): `root → friend` (dirección única)
6. Persistir (si `persist=true`):
   - Transacción por root
   - `upsert_profile(root)`; luego por cada relación: `upsert_profile(related)`, `add_relationship(owner=root, related=target, rel_type)`
   - `ON CONFLICT DO NOTHING` en relaciones
   - Nunca insertar `source==target`
7. Tiempos, warnings, logging

## Arquitectura y módulos a crear/modificar

- Nuevo: `api/routers/multi_scrape.py`
  - Define `@router.post('/multi-scrape')`
  - Usa `MultiScrapeRequest`/`Response`
  - Calcula `max_concurrency` default
  - `await multi_scrape_execute(request.model_dump())`
  - Manejo de errores → respuestas con códigos/formatos acordados

- Nuevo: `api/services/multi_scrape.py`
  - `async def multi_scrape_execute(request_dict) -> dict`
  - Orquesta concurrencia con `asyncio.Semaphore`
  - Controla Playwright: un navegador, contextos por root/lista
  - Integra adaptadores `src/scrapers/{facebook,instagram,x}`
  - Persistencia mediante `api.db.get_conn` y `api.repositories.*`

- Cambios menores:
  - `api/schemas.py`: añadir modelos `MultiScrapeRoot`, `MultiScrapeRequest`, `MultiScrapeResponse`
  - `api/main.py`: `app.include_router(multi_scrape_router)`

- Reutilizados:
  - `api/deps.storage_state_for`
  - `api/repositories.upsert_profile` y `add_relationship`
  - Utils de normalización `src/utils/*`

## Contrato de adapters (interfaces)

Cada plataforma implementa:

```python
async def get_root_profile(ctx, username) -> dict
async def get_followers(ctx, username, max_photos: int = 5) -> list[dict]
async def get_following(ctx, username, max_photos: int = 5) -> list[dict]
# Facebook solamente
async def get_friends(ctx, username) -> list[dict]
```

- Campos esperados por item: `username`, `full_name?`, `profile_url`, `photo_url?`
- El orquestador hará la normalización final y validación del `username`.

## Manejo de errores y warnings

- Por root:
  - Si falla adapter o listas: `warnings += [{code:'PARTIAL_FAILURE', message: f'{rootId} ...'}]`
  - Continuar con otros roots
- Errores HTTP del endpoint:
  - 422: validación Pydantic
  - 400: falta de storage-state (si activamos política estricta por query flag p.ej. `strict_sessions=true`)
  - 500: excepción no controlada

## Estrategia de concurrencia

- `max_concurrency` ∈ [1,3]
- Default dinámico: 1 si `len(roots)==1`, 3 si `>1`
- `asyncio.Semaphore(max_concurrency)` para envolver tareas de roots
- Crear/cerrar contextos por lista para estabilidad en sesiones largas

## Pruebas (aceptación mínima)

- Unit/integration (FastAPI TestClient):
  - POST `/multi-scrape` con 1 root de instagram → 200; `schema_version=2`; `root_profiles` incluye `instagram:<user>`; `profiles` incluye el root
  - `persist=true` y DB accesible: después del run, `relationships` contiene filas para owner=root hoy (se puede verificar con un helper de test)
  - 2 roots y `max_concurrency=2` → respuesta con ambos `root_profiles` y `meta.roots_timings`
  - Un root inválido → `warnings` con `PARTIAL_FAILURE`; el otro root válido no se ve afectado
  - Validaciones: roots vacío y >5 → 422 (tests ya existentes: `tests/test_api_multi_scrape.py`)

## Plan de implementación (fases y tareas)

1) Esquemas y router (Día 1)
- [ ] `api/schemas.py`: añadir modelos y validaciones
- [ ] `api/routers/multi_scrape.py`: endpoint POST `/multi-scrape` + wiring con servicio
- [ ] `api/main.py`: incluir router

2) Servicio y orquestación (Día 1-2)
- [ ] `api/services/multi_scrape.py`: `multi_scrape_execute` con concurrencia, almacenamiento de métricas y warnings
- [ ] Normalización de perfiles/relaciones y merge de `sources`
- [ ] Manejo de sesiones via `storage_state_for`

3) Persistencia (Día 2)
- [ ] Transacción por root utilizando `get_conn`
- [ ] Reutilizar `upsert_profile` y `add_relationship` (idempotencia)
- [ ] Guardas: no `source==target`, ignorar usernames inválidos

4) Adaptadores (Día 2-3)
- [ ] Integración con scrapers existentes (fb/ig/x). Si no disponibles, stubs controlados para no bloquear la entrega
- [ ] Contextos frescos por lista para estabilidad
- [ ] Logs informativos por lista y root

5) Pruebas y estabilización (Día 3)
- [ ] Asegurar `tests/test_api_multi_scrape.py` pasa
- [ ] Pruebas de persistencia con DB
- [ ] Ajustes de timeouts, scrolls, y límites si aplica

6) Documentación y rollout (Día 3)
- [ ] README/API docs: ejemplos de request/response, notas de sesión, límites
- [ ] Notas de compatibilidad: enums `rel_type` en inglés; rutas estáticas `/data/storage` y `/storage`

## Criterios de “Listo” (Definition of Done)

- Endpoint `/multi-scrape` disponible y documentado
- Cumplimiento íntegro del contrato del request/response (schema_version=2)
- Persistencia idempotente y por transacción de root, sin duplicados
- Warnings bien formados en fallos parciales; logs útiles
- Pruebas mínimas pasando (incluido `tests/test_api_multi_scrape.py`)

## Riesgos y mitigaciones

- Inestabilidad del navegador/contexts → contexto fresco por lista + límites de concurrencia
- Bloqueos por sesiones caducadas → validación previa y warnings claros
- Duplicados en perfiles/relaciones → claves únicas + ON CONFLICT
- Cambios de DOM en listas grandes → heurísticas de scroll y re-evaluación periódica del contenedor

## Apéndice: Estructuras

- ProfileItem
```json
{
  "platform": "instagram",
  "username": "usuario1",
  "full_name": "Usuario 1",
  "profile_url": "https://www.instagram.com/usuario1/",
  "photo_url": null,
  "sources": ["instagram:usuario1"]
}
```

- RelationItem
```json
{ "platform": "facebook", "source": "usuario2", "target": "amigo_a", "type": "friend" }
```

- Warning
```json
{ "code": "PARTIAL_FAILURE", "message": "instagram:usuario1 timeout en seguidores" }
```
