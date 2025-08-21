# Scr4per: Estructura de Carpetas y Funcionamiento

## Estructura Recomendada de Carpetas

```
Scr4per/
│
├── api/
│   ├── app.py                # API principal (FastAPI, endpoints para DB y scraping)
│   └── scraper_endpoints.py  # Endpoints HTTP para disparar scraping (nuevo)
│
├── src/
│   ├── scrapers/             # Lógica de scraping por red social (x.py, instagram.py, facebook.py, etc.)
│   └── services/
│       └── scraping_service.py  # Funciones para orquestar scraping, importar desde scrapers/ (nuevo)
│
├── scripts/
│   └── ...                   # Scripts CLI legacy para uso manual
│
├── db/
│   ├── schema.sql            # Esquema de la base de datos
│   ├── .env.example          # Variables de entorno de ejemplo
│   ├── .env                  # Variables de entorno reales (no subir a git)
│   └── connect_test.py       # Script para probar conexión a la DB
│
├── README.md
├── API_SETUP.md
└── requirements.txt
```

---

## ¿Cómo funciona Scr4per?

### 1. **Propósito**
Scr4per es un microservicio que permite scrapear información de perfiles de redes sociales (X, Instagram, Facebook) y almacenar los datos estructurados en una base de datos PostgreSQL. Expone endpoints HTTP para que otros programas puedan interactuar con el scraper y la base de datos.

---

### 2. **Componentes principales**

- **API (FastAPI/Uvicorn):**
  - Expone endpoints HTTP para insertar perfiles, relaciones, posts y comentarios en la base de datos.
  - Expone endpoints para disparar el scraping de perfiles de redes sociales mediante peticiones POST con JSON.
  - Permite consultar el estado o resultado del scraping (opcional, si se implementa asincronía).

- **Scrapers:**
  - Lógica específica para cada red social, ubicada en `src/scrapers/`.
  - Cada scraper puede ser llamado desde la API o desde scripts manuales.

- **Servicios:**
  - Orquestan la ejecución de los scrapers y el manejo de resultados.
  - Se ubican en `src/services/scraping_service.py`.

- **Base de datos:**
  - PostgreSQL almacena perfiles, relaciones, posts y comentarios.
  - El esquema está en `db/schema.sql` y se configura mediante variables de entorno.

---

### 3. **Flujo de trabajo típico**

1. **Otro programa envía una petición POST** a `/scrape` con un JSON que contiene la URL del perfil y la red social.
2. **La API recibe la petición** y llama a la función de scraping correspondiente según la red social.
3. **El scraper obtiene los datos** del perfil, amigos, posts, etc.
4. **Los datos se insertan** en la base de datos usando los endpoints internos de la API.
5. **La API responde** con el resultado del scraping o un identificador de tarea si es asíncrono.
6. **El programa cliente puede consultar** el resultado posteriormente mediante un endpoint GET (opcional).

---

### 4. **Ejemplo de uso de endpoints**

- **POST `/scrape`**  
  Inicia el scraping de un perfil:
  ```json
  {
    "platform": "x",
    "profile_url": "https://x.com/ibaillanos"
  }
  ```
  Respuesta:
  ```json
  {
    "status": "ok",
    "data": { ...datos del perfil y relaciones... }
  }
  ```

- **POST `/profiles`**, **/relationships**, **/posts**, **/comments**  
  Permiten insertar datos directamente en la base de datos (ver ejemplos en `API_SETUP.md`).

---

### 5. **Ventajas de esta arquitectura**

- Permite integración sencilla con otros sistemas mediante HTTP.
- Facilita la escalabilidad y el mantenimiento del código.
- Separa claramente la API, la lógica de scraping y los scripts manuales.
- Permite reutilizar la lógica de scraping tanto desde la API como desde scripts CLI.

---

### 6. **Notas adicionales**

- Puedes ejecutar la API con:
  ```
  uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
  ```
- La documentación interactiva está disponible en `/docs`.
- Los scripts en `scripts/` pueden seguir usándose para pruebas manuales o migrarse a la API.

---

**Este documento resume la estructura y funcionamiento de Scr4per para facilitar su comprensión y evolución por parte de otros desarrolladores