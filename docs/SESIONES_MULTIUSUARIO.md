# Sistema de Sesiones Multi-Usuario

## Resumen

Este sistema permite que múltiples analistas usen el scraper simultáneamente con sus propias credenciales de Facebook, eliminando el problema de conflictos y baneos por sesiones compartidas.

## Arquitectura

### Componentes Principales

1. **`db/models.py`** - Modelo SQLAlchemy para `sesiones_scraping`
2. **`src/services/scraping_service.py`** - Servicio para obtener sesiones desde la DB
3. **`src/scrapers/facebook/scraper.py`** - `FacebookScraperManager` con validación early exit
4. **`src/scrapers/facebook/navigation.py`** - Utilidades de navegación y URL
5. **`src/scrapers/facebook/config.py`** - Configuración con Pydantic
6. **`src/utils/exceptions.py`** - Excepciones personalizadas
7. **`api/routers/health.py`** - Health check profundo (DB + FTP)

## Flujo de Uso

### 1. Obtener Sesión desde la DB

```python
from src.services.scraping_service import scraping_service

# Obtener sesión para un usuario específico
session_data = scraping_service.get_session_for_user(
    id_usuario=1,
    plataforma='facebook'
)
```

**Validaciones Automáticas:**
- Verifica que la sesión exista
- Verifica que el estado sea `'activa'`
- Verifica que no haya expirado (>30 días sin actividad)
- Lanza excepciones específicas si falla

### 2. Iniciar Scraper con Sesión

```python
from src.scrapers.facebook.scraper import FacebookScraperManager

manager = FacebookScraperManager()
await manager.start(
    storage_state=session_data['cookies'],  # Cookies desde DB
    proxy_url=session_data.get('proxy_url'),  # Proxy opcional
    user_agent=session_data.get('user_agent'),  # User agent
    session_id=session_data['id_sesion'],  # Para logging
    headless=True
)
```

### 3. Validar Sesión (Early Exit)

```python
try:
    # Valida navegando a facebook.com y verificando que no redirija a login
    await manager._validate_session_integrity()
except SessionExpiredException:
    # Sesión expirada - marcar en DB
    scraping_service._mark_session_expired(session_data['id_sesion'])
except AccountBannedException:
    # Cuenta baneada - marcar en DB
    scraping_service.mark_session_banned(session_data['id_sesion'])
```

**¿Qué valida?**
- No redirige a `/login` o `/checkpoint`
- No muestra formulario de login
- No muestra checkpoint de seguridad

**Beneficio:** Falla en 2-3 segundos en lugar de perder minutos navegando con sesión inválida.

### 4. Realizar Scraping

```python
# Obtener la página de Playwright
page = manager.get_page()

# Usar funciones existentes
from src.scrapers.facebook.scraper import (
    obtener_datos_usuario_facebook,
    scrap_friends_all,
)

datos = await obtener_datos_usuario_facebook(page, perfil_url)
amigos = await scrap_friends_all(page, perfil_url, datos['username'])
```

### 5. Actualizar Actividad

```python
# Actualizar timestamp de última actividad
scraping_service.update_session_activity(session_data['id_sesion'])
```

### 6. Cerrar Navegador

```python
await manager.close()
```

## Esquema de Base de Datos

```sql
CREATE TABLE entidades.sesiones_scraping (
    id_sesion SERIAL PRIMARY KEY,
    id_usuario INTEGER NOT NULL REFERENCES entidades.usuarios(id_usuario),
    plataforma VARCHAR(50) NOT NULL,
    cookies JSONB NOT NULL,  -- storage_state de Playwright
    proxy_url VARCHAR(255),
    user_agent VARCHAR(500),
    estado VARCHAR(20) DEFAULT 'activa',  -- activa, expirada, baneada
    ultima_actividad TIMESTAMP DEFAULT NOW(),
    fecha_creacion TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sesiones_usuario_plataforma 
ON entidades.sesiones_scraping(id_usuario, plataforma);
```

## Excepciones

### `SessionNotFoundException`
- **Cuándo:** No existe sesión para el usuario/plataforma
- **Acción:** Crear nueva sesión o notificar al usuario

### `SessionExpiredException`
- **Cuándo:** 
  - Estado != 'activa'
  - Más de 30 días sin actividad
  - Se detecta formulario de login
- **Acción:** Marcar como expirada, solicitar re-login

### `AccountBannedException`
- **Cuándo:** Se detecta checkpoint o restricción
- **Acción:** Marcar como baneada, revisar manualmente

## Health Check

```bash
GET /health
```

**Respuesta Exitosa (200):**
```json
{
    "status": "ok",
    "services": {
        "database": {"status": "ok", "message": "Database connection successful"},
        "ftp": {"status": "ok", "message": "FTP connection successful"}
    }
}
```

**Respuesta con Fallo (503):**
```json
{
    "status": "error",
    "services": {
        "database": {"status": "ok", "message": "..."},
        "ftp": {"status": "error", "message": "FTP connection failed"}
    }
}
```

## Navegación

### URLs Soportadas

El sistema maneja automáticamente ambos formatos de perfil:

1. **Username:** `facebook.com/juan.perez`
2. **ID Numérico:** `facebook.com/profile.php?id=100012345`

```python
from src.scrapers.facebook.navigation import FacebookNavigation

# Construir URLs
friends_url = FacebookNavigation.build_friends_url('juan.perez')
# → https://www.facebook.com/juan.perez/friends

friends_url = FacebookNavigation.build_friends_url('100012345')
# → https://www.facebook.com/profile.php?id=100012345&sk=friends

# Extraer identificador
identifier = FacebookNavigation.extract_identifier_from_url(url)

# Validar URLs
is_login = FacebookNavigation.is_login_url(current_url)
is_checkpoint = FacebookNavigation.is_checkpoint_url(current_url)
```

## Configuración

Archivo: `src/scrapers/facebook/config.py`

```python
from src.scrapers.facebook.config import facebook_config

# Valores por defecto (modificables con Pydantic)
facebook_config.modal_scroll_pause  # 3.0 segundos
facebook_config.max_friends_to_scrape  # 5000
facebook_config.headless  # True
facebook_config.timeout_navigation  # 30000 ms
facebook_config.timeout_selectors  # 10000 ms
facebook_config.max_scrolls  # 20
facebook_config.scroll_pause_ms  # 3500 ms
```

## Migración desde Sistema Antiguo

### Antes (archivo local):
```python
await context.storage_state(path='data/storage/facebook_storage_state.json')
```

### Ahora (base de datos):
```python
# 1. Guardar sesión en DB (una vez)
storage_state = await context.storage_state()
# INSERT INTO entidades.sesiones_scraping (id_usuario, plataforma, cookies)
# VALUES (1, 'facebook', storage_state::jsonb)

# 2. Usar sesión desde DB
session_data = scraping_service.get_session_for_user(1, 'facebook')
await manager.start(storage_state=session_data['cookies'])
```

## Ejemplo Completo

Ver: `examples/ejemplo_sesiones_multiusuario.py`

```python
import asyncio
from src.scrapers.facebook.scraper import FacebookScraperManager
from src.services.scraping_service import scraping_service

async def scrape_with_db_session():
    # 1. Obtener sesión
    session = scraping_service.get_session_for_user(1, 'facebook')
    
    # 2. Iniciar scraper
    manager = FacebookScraperManager()
    await manager.start(storage_state=session['cookies'], session_id=session['id_sesion'])
    
    try:
        # 3. Validar sesión (early exit)
        await manager._validate_session_integrity()
        
        # 4. Scraping
        page = manager.get_page()
        # ... tu código de scraping aquí ...
        
        # 5. Actualizar actividad
        scraping_service.update_session_activity(session['id_sesion'])
        
    finally:
        await manager.close()

asyncio.run(scrape_with_db_session())
```

## Beneficios

✅ **Multi-Usuario:** Cada analista usa sus propias credenciales  
✅ **Early Exit:** Detecta sesiones inválidas en 2-3 segundos  
✅ **Fail Fast:** No pierde tiempo navegando con sesiones expiradas  
✅ **Gestión Centralizada:** Todas las sesiones en la DB  
✅ **Health Check:** Monitoreo de DB y FTP  
✅ **Proxy Support:** Cada usuario puede usar su propio proxy  
✅ **Auto-Expiración:** Marca sesiones >30 días como expiradas  

## Próximos Pasos

1. Migrar sesiones existentes de archivos JSON a la DB
2. Implementar adaptadores similares para Instagram y X
3. Agregar endpoint API para crear/actualizar sesiones
4. Implementar monitoreo de salud de sesiones (cron job)
5. Agregar soporte para rotación automática de proxies
