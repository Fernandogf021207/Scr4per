# Plan Incremental Backend Multi-Root (Informe para Frontend)

Versión documento: 0.1 (borrador para validación FE)
Fecha: 2025-09-29
Responsable Backend: Graph Backend Agent
Responsable Frontend: FE Graph Agent
Estado: PENDIENTE DE ACEPTACIÓN FRONTEND

---
## 1. Objetivo
Agregar soporte multi-root (múltiples perfiles origen) para extracción, fusión y análisis relacional sin romper el endpoint legacy `/scrape` actualmente usado en producción.

## 2. Resumen de Alcance (Scope)
| Fase | Entrega | Cambios visibles FE | Riesgo |
|------|---------|---------------------|--------|
| F1 | Nuevo endpoint `/multi-scrape` (schema v2 básico) | FE puede pedir varios roots y recibir `root_profiles[]`, `profiles[]`, `relations[]`, `schema_version:2` | Bajo (aislado) |
| F2 | Warnings + límites + merge strategy | FE muestra panel warnings | Bajo |
| F3 | Concurrencia controlada (pool scrapers) | Menor latencia en roots múltiples | Medio (Playwright) |
| F4 | Endpoint `/multi-related` (enriquecimiento incremental) | FE actualiza grafo sin recargar | Medio |
| F5 | Persistencia sesiones v2 (`/graphs`, `/graphs/{id}`) | FE guarda/carga grafos multi-root | Medio |
| F6 | Métricas & logs estructurados | FE puede mostrar performance/estado (opcional) | Bajo |
| F7 | Export (PDF / snapshot) | FE botón export | Medio |

## 3. Principios
- No romper `/scrape` ni payload legacy v1.
- `schema_version` obligatorio en nuevas respuestas v2.
- Limpia separación: backend produce datos semánticos, FE construye layout/estilos.
- Determinismo en IDs (FE seguirá generando `platform::username`).
- Evolución controlada: cada fase mergeable independientemente.

## 4. Endpoints (Estado / Plan)
| Endpoint | Estado | Notas |
|----------|--------|-------|
| `POST /scrape` | Legacy activo | Sin cambios (retorno v1). |
| `POST /multi-scrape` | Nuevo (F1) | Retorno v2 con múltiples roots. |
| `POST /multi-related` | Planeado (F4) | Enriquecer grafo existente (deltas). |
| `POST /graphs` | Planeado (F5) | Persistir sesión multi-root v2. |
| `GET /graphs/{graph_id}` | Planeado (F5) | Recuperar sesión almacenada. |
| `POST /graphs/{graph_id}/export` | Planeado (F7) | Export PDF/otros. |

## 5. Contrato Inicial `/multi-scrape` (F1)
Request:
```jsonc
{
  "requests": [
    { "platform": "instagram", "username": "userA", "max_fotos": 30 },
    { "platform": "instagram", "username": "userB", "max_fotos": 20 }
  ],
  "options": {
    "merge_strategy": "first_wins",        // future: overwrite | prefer_longer_name
    "include_relations_between_roots": true  // F1: ignorado o reservado
  }
}
```
Response v2 (F1 mínimo):
```jsonc
{
  "schema_version": 2,
  "root_profiles": [ {"platform":"instagram","username":"userA","full_name":"...","photo_url":"..."} ],
  "profiles": [ {"platform":"instagram","username":"userA","full_name":"..."} ],
  "relations": [ {"source":{"platform":"instagram","username":"userX"},"target":{"platform":"instagram","username":"userA"},"type":"seguidor"} ],
  "warnings": [],
  "meta": { "generated_at":"2025-09-29T12:05:00Z", "processing_ms": 742 }
}
```
Tipos de relación v2 (idioma español): `seguidor`, `seguido`, `amigo` (FB), `comentó`, `reaccionó`.

## 6. Transformaciones / Agregación
Se introducirá un módulo interno (nombre tentativo `aggregation.py`) que:
- Normaliza usernames (regex ^[A-Za-z0-9._-]{1,50}$).
- Deduplica perfiles combinando `full_name`, `photo_url` según `merge_strategy`.
- Construye `relations[]` dirigidas con semántica consistente.
- Genera warnings (F2+).

No genera layout, ni IDs del front (lo hace FE), ni estilos.

## 7. Persistencia (Plan)
| Fase | Acción | Nota |
|------|--------|------|
| F1 | Upsert perfiles/relaciones como ahora (por root) | Reusa repos existentes. |
| F2 | Batch insert opcional | Optimización. |
| F5 | Guarda sesión v2 (graph JSON + roots + meta) | Sustituye uso parcial de `graph_session` legacy. |

## 8. Warnings (Introducción F2)
| Código | Situación | Reacción FE |
|--------|-----------|-------------|
| ROOT_SKIPPED | Scrape root fallido | Indicar listado fallidos |
| INVALID_USERNAME | Regex no válida | Mostrar validación inmediata |
| PARTIAL_FAILURE | Root con error intermedio | Resaltar parcial |
| REL_LIMIT_TRUNCATED | Recorte por límite | Mostrar badge |
| LIMIT_REDUCED | max_fotos reducido | Info secundaria |
| TIMEOUT_ROOT | Timeout scraping root | Sugerir reintento |

## 9. Concurrencia (F3)
- Semáforo: `MAX_CONCURRENT_ROOTS` (env, default 2).
- Cada root → contexto Playwright aislado (no se comparte state).
- Política en caso de saturación: cola FIFO interna (no 429 al FE inicialmente).

## 10. Métricas (F6)
Prometheus (nombres tentativos):
- `graph_multi_scrape_duration_ms` (histogram)
- `graph_multi_scrape_roots_total`
- `graph_multi_scrape_relations_total`
- `graph_multi_scrape_warnings_total{code}`
- `graph_multi_scrape_errors_total{code}`

## 11. Errores (Formato Estándar)
```json
{
  "error": { "code": "VALIDATION_ERROR", "message": "Username inválido", "detail": null, "meta": {"field":"username"} }
}
```
HTTP / Códigos sugeridos:
- 422: VALIDATION_ERROR / LIMIT_EXCEEDED
- 500: INTERNAL_ERROR
- 200 + warnings si al menos un root OK.

## 12. Compatibilidad FE
| Situación | Acción FE |
|-----------|-----------|
| `schema_version` ausente | Tratar como v1 (ya implementado) |
| `schema_version:2` | Invocar parser v2 (merge) |
| Nuevos warnings | Mostrar panel / badge sin bloquear |
| Futuros campos | Ignorar si no usados |

## 13. Decisiones Requeridas del Frontend (INPUT NECESARIO)
Por favor responder antes de avanzar a implementación F1:
1. ¿Mantenemos idioma de tipos de relación 100% en español (seguidor/seguido) o FE prefiere mapear a inglés internamente? (Backend puede fijar español.)
2. ¿Necesita FE que `relations[]` incluya redundancia de `full_name` o solo `platform/username`? (Propuesta: minimal solo IDs.)
3. ¿Se requiere field adicional `sources[]` (lista roots que originaron el perfil) en `profiles[]` ya en F1 o lo dejamos para F2? 
4. Límite inicial sugerido de roots simultáneos (5 propuesto). ¿Confirmar? 
5. ¿FE necesita ya `include_relations_between_roots` o se pospone? (Si roots no se siguen entre sí puede devolver vacío.)
6. ¿Priorizar persistencia v2 (F5) antes que warnings (F2) para flujos de investigación, o mantener el orden actual?
7. Para colisiones de `full_name`: preferimos `first_wins` por simplicidad. ¿Confirmar o desean `prefer_longer_name`? 

## 14. Roadmap Tentativo (Semanas)
| Semana | Hito |
|--------|------|
| S1 | F1 (`/multi-scrape` básico) + tests mínimos |
| S2 | F2 (warnings + merge strategy) |
| S3 | F3 (concurrencia) + micro-bench |
| S4 | F5 (persistencia sesiones v2) |
| S5 | F4/F6 según prioridad FE |

(Orden F4/F5 puede intercambiarse si FE pide primero persistencia.)

## 15. Testing Plan (F1 mínimo)
- Unit: agregador (dedupe perfiles, relaciones).
- Integration: `/multi-scrape` con 1 root vs `/scrape` equivalencia básica.
- Integration: 2 roots, sin intersección, sin warnings.
- Integration: root inválido → warning + sigue.

## 16. Rollback Strategy
- F1 aislado: eliminar router `/multi-scrape` y archivos `aggregation.py` / `multi_scrape.py`.
- DB sin migraciones nuevas en F1 → rollback trivial.
- Feature flag (env) opcional: `ENABLE_MULTI_SCRAPE=0` para desactivar endpoint sin redeploy de código (si se implementa wrapper rápido).

## 17. Riesgos y Mitigaciones
| Riesgo | Mitigación |
|--------|-----------|
| Tiempos altos multi-root | Paralelismo controlado + timeouts por root |
| Bloqueo Playwright | Reinicio de contexto por root, no reuso contaminado |
| Crecimiento no controlado de memoria | Cierre explícito de context y browser por root |
| Payload grande | Límite relaciones + warnings truncados |

## 18. Ejemplo Completo (F1 Esperado)
```jsonc
{
  "schema_version": 2,
  "root_profiles": [
    {"platform":"instagram","username":"userA","full_name":"User A","photo_url":"/data/storage/images/userA.jpg"},
    {"platform":"instagram","username":"userB","full_name":"User B","photo_url":"/data/storage/images/userB.jpg"}
  ],
  "profiles": [
    {"platform":"instagram","username":"userA","full_name":"User A","photo_url":"/data/storage/images/userA.jpg"},
    {"platform":"instagram","username":"userB","full_name":"User B","photo_url":"/data/storage/images/userB.jpg"},
    {"platform":"instagram","username":"userC","full_name":"User C","photo_url":"/data/storage/images/userC.jpg"}
  ],
  "relations": [
    {"source":{"platform":"instagram","username":"userC"},"target":{"platform":"instagram","username":"userA"},"type":"seguidor"},
    {"source":{"platform":"instagram","username":"userB"},"target":{"platform":"instagram","username":"userC"},"type":"seguido"}
  ],
  "warnings": [],
  "meta": {"generated_at":"2025-09-29T12:05:00Z","processing_ms":742}
}
```

## 19. Próximos Pasos (Tras Aprobación FE)
1. Confirmar decisiones sección 13.
2. Crear rama `multi-root` (si no existe) o continuar trabajo ahí.
3. Implementar modelos Pydantic F1 + agregador mínimo.
4. Endpoint `/multi-scrape` (sin concurrencia todavía).
5. Tests básicos + documentación OpenAPI.
6. Entregar a FE para integración inicial.

---
## 20. Solicitud al Frontend
Por favor responder con las decisiones (1..7) y cualquier ajuste antes de comenzar implementación para asegurar alineación.

> QUEDA A LA ESPERA DE RESPUESTA DEL FRONTEND.
