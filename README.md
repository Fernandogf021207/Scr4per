# Social Media Scraper

Un scraper modular y asíncrono para extraer datos de X, Instagram y Facebook, incluyendo seguidores, seguidos y comentadores de posts.

## 🚀 Características

- **Scraping asíncrono** con Playwright para mejor rendimiento
- **Extracción completa** de seguidores, seguidos y comentadores
- **Interfaz de menú** interactiva para seleccionar tareas específicas
- **Exportación flexible** a Excel o CSV
- **Logging detallado** para debugging
- **Manejo robusto de errores** y rate limiting
- **Arquitectura modular** extensible a otras plataformas

## 📋 Requisitos

- Python 3.8+
- Cuenta de Instagram (para sesión autenticada)
- Navegador Chromium (instalado automáticamente por Playwright)

## 🛠️ Instalación

### 1. Clonar o descargar el proyecto

```bash
git clone <tu-repositorio>
cd social_media_scraper
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
playwright install
```

### 3. Configurar el proyecto

```bash
python setup.py
```

Este script:
- Crea la estructura de directorios necesaria
- Te ayuda a configurar tu sesión de Instagram
- Prepara el entorno de trabajo

## 📁 Estructura del Proyecto

```
social_media_scraper/
├── src/
│   ├── utils/
│   │   ├── common.py              # Utilidades compartidas
│   │   ├── logging_config.py      # Configuración de logging
│   │   └── output.py             # Manejo de archivos de salida
│   └── scrapers/
│       └── instagram/
│           ├── config.py         # Configuración (selectores, parámetros)
│           ├── utils.py          # Funciones auxiliares específicas
│           └── scraper.py        # Lógica principal de scraping
├── scripts/
│   └── run_instagram.py         # Punto de entrada con menú
├── data/
│   ├── output/                  # Archivos Excel/CSV generados
│   └── storage/                 # Archivos de sesión del navegador
├── logs/
│   └── scraper.log             # Archivo de log
├── requirements.txt
├── setup.py
└── README.md
```

## 🎯 Uso

Interfaz de Menú (Recomendado)

```bash
python scripts/run_instagram.py
```

El menú te permite elegir:
1. **Extraer solo seguidores** - Lista completa de seguidores
2. **Extraer solo seguidos** - Lista completa de seguidos  
3. **Extraer solo comentadores** - Usuarios que comentan en posts
4. **Extraer todo** - Seguidores, seguidos y comentadores
5. **Salir**


## ⚙️ Configuración

### Archivo de Sesión

El scraper requiere un archivo de sesión de Instagram:
- Ubicación: `data/storage/instagram_storage_state.json`
- Se genera automáticamente durante `setup.py`
- Contiene las cookies de tu sesión autenticada

### Parámetros Configurables

En `src/scrapers/instagram/config.py`:

```python
max_scroll_attempts = 30          # Máximo número de scrolls en modales
scroll_pause_ms = 1500           # Pausa entre scrolls (ms)
rate_limit_pause_ms = 5000       # Pausa cada 10 scrolls para evitar bans
max_no_new_content = 3           # Scrolls sin contenido nuevo antes de parar
default_max_posts = 5            # Posts por defecto para comentarios
```

## 📊 Formato de Salida

### Excel (Preferido)
Archivo: `data/output/instagram_scraping_<username>.xlsx`

**Hojas:**
- **Usuario**: Datos del perfil principal
- **Seguidores**: Lista completa de seguidores
- **Seguidos**: Lista completa de seguidos
- **Comentarios**: Usuarios que comentan en posts

### CSV (Fallback)
Si `openpyxl` no está disponible, se crean 4 archivos CSV separados.

### Estructura de Datos

```python
# Usuario principal
{
    'id_usuario': [1],
    'nombre_usuario': ['Nombre Completo'],
    'username': ['username'],
    'url_usuario': ['https://instagram.com/username/'],
    'url_foto_perfil': ['https://...']
}

# Seguidores/Seguidos
{
    'id_seguidor': [1, 2, 3...],
    'id_usuario_principal': [1, 1, 1...],
    'nombre_seguidor': ['Nombre 1', 'Nombre 2'...],
    'username_seguidor': ['user1', 'user2'...],
    'url_seguidor': ['https://instagram.com/user1/'...],
    'url_foto_perfil_seguidor': ['https://...'...]
}

# Comentarios
{
    'id_comentario': [1, 2, 3...],
    'id_usuario_principal': [1, 1, 1...],
    'post_id': [1, 1, 2...],
    'url_post': ['https://instagram.com/p/ABC123/'...],
    'username_comentario': ['commenter1'...],
    'nombre_comentario': ['Commenter Name'...],
    'url_perfil_comentario': ['https://instagram.com/commenter1/'...],
    'url_foto_comentario': ['https://...'...]
}
```

## 🔧 Solución de Problemas

### Perfil Privado
```
❌ No se pudo encontrar el enlace de seguidores. ¿El perfil es público?
```
**Solución:** Sigue al usuario o usa un perfil público

### Sesión Expirada
```
❌ Error navegando a seguidores
```
**Solución:** Regenera tu sesión ejecutando `python setup.py`

### Sin Datos Extraídos
```
⚠️ No se encontraron datos
```
**Posibles causas:**
- Perfil privado sin seguir
- Sesión no iniciada/expirada
- Cambios en la estructura de Instagram
- Rate limiting de Instagram

### Rate Limiting
Si Instagram limita tu cuenta:
1. Aumenta `rate_limit_pause_ms` en `config.py`
2. Reduce `max_scroll_attempts`
3. Espera unas horas antes de hacer scraping

## 📝 Logs

Los logs se guardan en `logs/scraper.log` e incluyen:
- Errores de navegación
- Problemas con selectores
- Estadísticas de extracción
- Warnings de rate limiting

Ejemplo:
```
2024-01-15 10:30:15 - INFO - Usuario detectado: @instagram (Instagram)
2024-01-15 10:30:45 - INFO - Seguidores encontrados: 1250
2024-01-15 10:31:20 - WARNING - No se pudo cargar más comentarios: timeout
```

## 🛡️ Consideraciones Éticas y Legales

- **Respeta los términos de servicio** de Instagram
- **Usa datos solo para propósitos legítimos** (investigación, análisis personal)
- **No hagas scraping masivo** que pueda sobrecargar los servidores
- **Respeta la privacidad** de los usuarios
- **Implementa delays apropiados** para evitar ser bloqueado

## 🚀 Extensibilidad

El proyecto está diseñado para ser extensible:

### Agregar Nuevas Plataformas
```
src/scrapers/nueva_plataforma/
├── config.py
├── utils.py
├── scraper.py
└── __init__.py
```

### Agregar Nuevas Funcionalidades
- Extracción de stories
- Análisis de hashtags
- Métricas de engagement
- Exportación a bases de datos

## 🤝 Contribuciones

Las contribuciones son bienvenidas:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Ver `LICENSE` para más detalles.

## ⚠️ Disclaimer

Este scraper es para propósitos educativos y de investigación. Los usuarios son responsables de cumplir con los términos de servicio de Instagram y las leyes aplicables en su jurisdicción.
