# Instagram -> Scrapling Migration Plan

## Objetivo
Migrar el scraper de Instagram para dejar de depender de selectores hardcodeados y pausas manuales, usando Scrapling para parsing dinamico y Playwright solo para navegacion/interaccion minima.

## Estado Actual Detectado
- `src/scrapers/instagram/scraper.py` concentra toda la logica de scraping con Playwright + selectores CSS y multiples `wait_for_timeout`.
- `src/scrapers/instagram/scrapling_spider.py` existe pero esta vacio.
- `requirements.txt` no declara `scrapling`.

## Principios de la Migracion
- Mantener compatibilidad de API: no romper firmas publicas actuales de `scraper.py`.
- Extraer parsing de HTML/DOM a Scrapling `Selector` con heuristicas por semantica (texto, roles, href, estructura), no por rutas CSS fragiles.
- Reemplazar esperas fijas por esperas de condicion observables:
  - cambios de URL
  - apertura/cierre de modal
  - incremento real de nodos en listas
  - llegada de respuestas de red esperadas
- Usar intercept de red como suplemento (GraphQL/REST) cuando exista informacion mas estable que el DOM.

## Alcance Funcional (Paridad con flujo actual)
- Perfil principal
- Seguidores
- Seguidos
- Reacciones a posts
- Comentaristas de posts
- Export CSV

## Plan de Implementacion por Fases

### Fase 0 - Baseline y Seguridad
- [ ] Agregar `scrapling` a `requirements.txt`.
- [ ] Crear test de humo para Instagram Scrapling (`tests/test_instagram_scrapling_smoke.py`) con cuenta controlada.
- [ ] Medir baseline actual (tiempo total, cantidad de nodos, errores) sobre 1 cuenta de referencia.

### Fase 1 - Nuevo modulo `scrapling_spider.py`
- [ ] Implementar `login_instagram(page, max_retries=3)` con verificacion de sesion y early-exit.
- [ ] Implementar `get_profile_data_scrapling(page, profile_url)`:
  - navegación Playwright
  - HTML renderizado
  - parsing con Scrapling + fallback minimo Playwright
- [ ] Implementar utilidades comunes:
  - detector de overlay/modal visible
  - detector de contenedor scrolleable dinamico
  - scroll adaptativo con criterio de estancamiento

### Fase 2 - Listas de red (seguidores/seguidos)
- [ ] Implementar `scrap_list_network_scrapling(page, profile_url, list_type)`.
- [ ] Estrategia hibrida:
  - extracción por lotes via JS evaluado (anchors + imagen + texto)
  - normalizacion y deduplicacion con `build_user_item`
  - suplemento opcional por red (si aparece endpoint util)
- [ ] Eliminar dependencia de selectores de texto exacto para botones en ES/EN.

### Fase 3 - Engagement de posts
- [ ] Implementar `scrap_post_engagements_scrapling(page, profile_url, username, max_posts=5)` para:
  - liked_by (reacciones)
  - comentarios
- [ ] Priorizar parseo semantico:
  - links de usuario por patrones de URL validos
  - exclusion de rutas no usuario (`/p/`, `/reel/`, `/stories/`, etc.)
- [ ] Fallback controlado a utilidades legacy solo en casos limite.

### Fase 4 - Integracion en `scraper.py` sin ruptura
- [ ] `obtener_datos_usuario_principal` -> delegar a `get_profile_data_scrapling`.
- [ ] `scrap_seguidores` -> delegar a `scrap_list_network_scrapling(..., "followers")`.
- [ ] `scrap_seguidos` -> delegar a `scrap_list_network_scrapling(..., "following")`.
- [ ] `scrap_reacciones_instagram` -> delegar a `scrap_post_engagements_scrapling`.
- [ ] `scrap_comentadores_instagram` -> delegar a `scrap_post_engagements_scrapling`.
- [ ] Mantener wrappers legacy para compatibilidad y rollback rapido.

### Fase 5 - Verificacion y Rollout
- [ ] Comparativa A/B Legacy vs Scrapling en 3 cuentas:
  - volumen de datos
  - precision de usernames
  - tiempo total
  - tasa de fallo
- [ ] Activar feature flag `INSTAGRAM_SCRAPER_ENGINE=scrapling|legacy`.
- [ ] Rollout gradual:
  - 10% -> 50% -> 100%
- [ ] Desactivar caminos legacy tras estabilidad.

## Mapa de Migracion (funcion actual -> destino)
- `obtener_datos_usuario_principal` -> `get_profile_data_scrapling`
- `extraer_usuarios_instagram` + `navegar_a_lista_instagram` -> `scrap_list_network_scrapling`
- `scrap_seguidores` -> wrapper a `scrap_list_network_scrapling(..., "followers")`
- `scrap_seguidos` -> wrapper a `scrap_list_network_scrapling(..., "following")`
- `extraer_posts_del_perfil` + `_abrir_liked_by_y_extraer_usuarios` + `scrap_reacciones_instagram` -> `scrap_post_engagements_scrapling` (modo likes)
- `extraer_comentarios_post` + `extraer_comentarios_en_modal` + `scrap_comentadores_instagram` -> `scrap_post_engagements_scrapling` (modo comments)
- `scrap_lista_usuarios` -> wrapper compatibilidad

## Criterios de Aceptacion
- Sin uso de `wait_for_timeout` en el flujo principal de Instagram (solo tolerado en fallback acotado).
- Al menos 90% de paridad de volumen vs flujo legacy en datasets de prueba.
- Reduccion minima esperada del 20% en tiempo promedio por corrida.
- Errores por cambio de DOM reducidos (menos incidencias de `query_selector` nulo en logs).

## Riesgos y Mitigaciones
- Riesgo: cambios frecuentes de UI en modales de Instagram.
  - Mitigacion: parser semantico + deteccion de contenedor dinamico + fallback por red.
- Riesgo: bloqueo/rate limiting.
  - Mitigacion: scroll escalonado, pausas adaptativas por actividad, reintentos con backoff.
- Riesgo: regresion funcional.
  - Mitigacion: feature flag + A/B + wrappers legacy.

## Accion Inmediata Recomendada (siguiente commit)
- [ ] Crear implementacion inicial de `src/scrapers/instagram/scrapling_spider.py` con:
  - login y validacion de sesion
  - parser de perfil
  - extractor de listas con scroll dinamico
- [ ] Conectar solo `obtener_datos_usuario_principal` por feature flag para primer despliegue seguro.
