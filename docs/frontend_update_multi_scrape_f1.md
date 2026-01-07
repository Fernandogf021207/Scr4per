# Actualización Backend F1: Endpoint `/multi-scrape` (schema v2)

Esta entrega completa la primera fase (F1) del modo multi-root.

## Resumen de Cambios Implementados
- Nuevo endpoint: `POST /multi-scrape`.
- Nuevo esquema de respuesta `schema_version: 2`.
- Campo `sources[]` incluido en cada perfil desde F1 (IDs de raíces que originaron ese hallazgo) con formato string `platform:username`.
- Límite de raíces: mínimo 1, máximo 5 (422 `LIMIT_EXCEEDED` si se supera).
- Validación de usernames (regex `[A-Za-z0-9_.-]{2,60}`), se normaliza removiendo `@` inicial.
- Soporta plataformas: `facebook`, `instagram`, `x`.
- Normalización añadida de listas heterogéneas devueltas por los scrapers (keys variantes como `username_usuario`, `nombre_usuario`, `link_usuario`, etc.) antes de generar relaciones.
- Relaciones ahora se agregan automáticamente a partir de seguidores, seguidos y amigos:
  - `seguidor`: follower -> root
  - `seguido`: root -> followed
  - `amigo`: amistad mutua -> se emiten DOS aristas (root -> amigo y amigo -> root) para mantener la semántica en un grafo dirigido. El FE puede colapsarlas si desea vista undirected.
- Respuesta incluye `warnings[]` (códigos iniciales: `ROOT_SKIPPED`, `PARTIAL_FAILURE`).
- Metadatos mínimos: `meta.build_ms`, `meta.roots_requested`, `meta.roots_processed`, `meta.schema_version`.
- No rompe endpoint legacy `/scrape` (sigue igual).

### NUEVO (F1 Ajuste Final)
Se añadió la función interna de normalización que garantiza que cada item de listas de seguidores/seguidos/amigos genera un objeto con:
```
{
  username,      # derivado de campo directo o de la URL
  full_name,     # preferido; fallback username
  profile_url,   # URL canónica normalizada
  photo_url
}
```
Si un username queda vacío o inválido se descarta el nodo.

## Request Body (ejemplo)
```json
{
  "roots": [
    {"platform": "facebook", "username": "user_a"},
    {"platform": "instagram", "username": "user_b", "max_photos": 3}
  ]
}
```
`max_photos` es opcional (default 5). No se usa todavía para optimización fuerte, pero se preserva para forward compatibility.

## Respuesta (ejemplo simplificado)
```json
{
  "schema_version": 2,
  "root_profiles": ["facebook:user_a", "instagram:user_b"],
  "profiles": [
    {
      "platform": "facebook",
      "username": "user_a",
      "full_name": "User A",
      "profile_url": "https://facebook.com/user_a",
      "photo_url": "/data/storage/images/uuid1.jpg",
      "sources": ["facebook:user_a"]
    },
    {
      "platform": "instagram",
      "username": "user_b",
      "full_name": "User B",
      "profile_url": "https://instagram.com/user_b",
      "photo_url": "/data/storage/images/uuid2.jpg",
      "sources": ["instagram:user_b"]
    },
    {
      "platform": "facebook",
      "username": "friend_x",
      "full_name": "Friend X",
      "profile_url": null,
      "photo_url": null,
      "sources": ["facebook:user_a"]
    }
  ],
  "relations": [
    {"platform": "facebook", "source": "friend_x", "target": "user_a", "type": "seguidor"},
    {"platform": "facebook", "source": "user_a", "target": "friend_x", "type": "seguido"},
    {"platform": "facebook", "source": "user_a", "target": "amigo_y", "type": "amigo"},
    {"platform": "facebook", "source": "amigo_y", "target": "user_a", "type": "amigo"}
  ],
  "warnings": [],
  "meta": {
    "schema_version": 2,
    "roots_requested": 2,
    "roots_processed": 2,
    "build_ms": 842
  }
}
```

## Notas de Agregación
- Clave de identidad de perfil: `platform + username`.
- `sources[]` son strings `platform:root_username` (orden lexicográfico tras agregación interna).
- Si un mismo perfil aparece por múltiples raíces de la misma plataforma, su `sources` acumula todas las raíces: `["facebook:root1", "facebook:root2"]`.
- No se fusionan identidades cross-platform (mismo username en dos plataformas => dos perfiles distintos).
- Relaciones `amigo` se modelan como par de aristas dirigidas para facilitar algoritmos que requieren dirección; el FE puede deduplicar (`min(source,target)` como clave) para vista undirected.
- Root-root (A↔B) aparece si las listas lo revelan (no hay post-procesamiento adicional todavía).

## Guía para Integración en Cytoscape (Frontend)

### 1. Construcción de Nodos
Usar cada item en `profiles` para generar:
```
node.data = {
  id: `${platform}:${username}`,
  platform,
  username,
  label: full_name || username,
  profile_url,
  photo_url,
  sources,            // array de strings
  sources_count: sources.length,
  is_root: root_profiles.includes(`${platform}:${username}`)
}
```
- Imagen: usar `photo_url` si no vacío; fallback a avatar por plataforma.
- Diferenciar raíces con un estilo (borde grueso, color distinto).

### 2. Construcción de Aristas
Para cada relación en `relations`:
```
edge.data = {
  id: `${platform}:${source}->${target}:${type}`,
  source: `${platform}:${source}`,
  target: `${platform}:${target}`,
  type,
  platform
}
```
- Si `type === 'amigo'` y deseas vista no dirigida: filtra duplicados quedándote con un único edge (por ejemplo conservar solo aquel donde `source < target` lexicográficamente).

### 3. Clases / Styling Sugeridos
Mapeo tipo → clase:
```
seguidor -> edge-follower   (inbound hacia root)
seguido  -> edge-following  (outbound desde root)
amigo    -> edge-friend
```
Podrías colorear así (ejemplo):
```
edge-follower: azul
edge-following: verde
edge-friend: naranja (o estilo dashed si se colapsa a undirected)
```

### 4. Métricas / Atributos para Layout
- `sources_count` puede usarse como peso visual (tamaño del nodo) para resaltar intersección entre raíces.
- Grado (in/out) se puede calcular client-side para heurísticas de layout (e.g., concentric / cose-bilkent).
- Puedes aplicar un layout inicial `cose` y luego cambiar a `concentric` usando `sources_count` como nivel.

### 5. Hover / Tooltip
Mostrar:
```
Full name / username
Plataforma
Roots que lo referencian (sources)
Conteo de relaciones (in/out)
```

### 6. Gestión de Grandes Listas
- Si el número de nodos supera un umbral (ej. > 1500) podrías agrupar temporalmente por plataforma hasta que el usuario haga zoom.
- (Futuro) agregaremos warnings de truncamiento para listas muy largas.

### 7. Estrategia para Detección de Intersecciones
Un perfil con `sources_count > 1` es un candidato para resaltado (stroke doble, glow, etc.).

### 8. Posible Integración con Sesiones (Próxima Fase)
Cuando añadamos persistencia `/graphs`, el mismo payload tendrá un `graph_id` para recargar sesiones; por ahora el frontend puede simplemente conservar el JSON en memoria o en localStorage.

## Ejemplo de Elementos Cytoscape (derivado del ejemplo simplificado)
```js
const nodes = profiles.map(p => ({
  data: {
    id: `${p.platform}:${p.username}`,
    platform: p.platform,
    username: p.username,
    label: p.full_name || p.username,
    profile_url: p.profile_url,
    photo_url: p.photo_url,
    sources: p.sources,
    sources_count: p.sources.length,
    is_root: root_profiles.includes(`${p.platform}:${p.username}`)
  }
}));

const edges = relations.map(r => ({
  data: {
    id: `${r.platform}:${r.source}->${r.target}:${r.type}`,
    source: `${r.platform}:${r.source}`,
    target: `${r.platform}:${r.target}`,
    type: r.type,
    platform: r.platform
  },
  classes: `rel-${r.type}`
}));
```

## Buenas Prácticas Recomendadas Frontend
- Aplicar debounce a búsquedas/filtrado de nodos cuando `nodes.length` > 800.
- Pre-cargar imágenes con `IntersectionObserver` dentro de un panel lateral (no cargar todas a la vez).
- Usar `sources_count` para agrupar nodos antes del primer layout final si > 500 nodos.

---
Si necesitáis ordenamiento determinista de `profiles` o filtrado temprano desde backend, se puede añadir un parámetro (`sort=alpha|degree`) en una sub-fase sin romper contrato actual.

## Warnings Actuales
| Código | Significado |
|--------|-------------|
| ROOT_SKIPPED | No había `storage_state` para la plataforma solicitada. |
| PARTIAL_FAILURE | Excepción no crítica al procesar una raíz. |

## Próximos Pasos Planeados (para que FE anticipe)
1. Persistencia sesión v2 (`/graphs` + export) — siguiente prioridad.
2. Warnings enriquecidos (ratelimit, listas truncadas, etc.).
3. Concurrencia controlada para acelerar múltiples raíces.
4. Endpoint `multi-related`.

## Diferencias vs `/scrape` (legacy)
| Aspecto | `/scrape` | `/multi-scrape` |
|---------|-----------|-----------------|
| Raíces | 1 | 1–5 |
| Versión schema | 1 | 2 |
| `sources[]` | No | Sí |
| Unificación multi-root | N/A | Sí (por plataforma+username) |
| Warnings estructurados | Limitado | Sí (lista formal) |

## Contrato Esencial para FE
- Mostrar siempre perfiles en orden libre (no garantizamos sorting todavía); FE puede ordenar client-side.
- Usar `root_profiles` para marcar nodos principales.
- Usar `sources.length` para derivar un grado de intersección (cuántas raíces lo referencian).
- Prepararse para nuevos campos en `meta` y `warnings[*]` sin romper (ignorar desconocidos).

## Errores (HTTP)
| Status | detail.code | Caso |
|--------|-------------|------|
| 422 | VALIDATION_ERROR | Username inválido / cuerpo vacío |
| 422 | LIMIT_EXCEEDED | >5 raíces |
| 400 | PLATFORM_UNSUPPORTED | (raro: si llegase a pasar) |
| 500 | INTERNAL_ERROR | Error inesperado |

---
Cualquier duda o si necesitan ordenamiento determinista adicional, avisar.
