# API y Base de Datos para Scr4per (X, Instagram, Facebook)

Esta guía crea una base de datos PostgreSQL y una API mínima para insertar perfiles, relaciones (seguidores/seguidos), posts y comentaristas. No modifica tu código del scraper.

Estructura creada:

- `db/schema.sql`: Esquema de la base de datos.
- `db/.env.example`: Variables de entorno (copia a `.env`).
- `db/seed.sql`: Opcional para crear rol/DB y ejecutar el esquema.
- `db/connect_test.py`: Script simple para probar conexión.
- `api/app.py`: API con FastAPI para insertar datos.
- `api/requirements.txt`: Dependencias de la API.

## 1) Preparar PostgreSQL

1. Instala PostgreSQL 14+.
2. Crea usuario y base (opcional, puedes usar tu propia):

   En psql como superusuario:

   ```sql
   CREATE ROLE scr4per_user WITH LOGIN PASSWORD 'your_password_here';
   CREATE DATABASE scr4per OWNER scr4per_user;
   GRANT ALL PRIVILEGES ON DATABASE scr4per TO scr4per_user;
   ```

3. Conéctate a la DB `scr4per` y aplica el esquema:

   En psql:

   ```sql
   \i c:/Users/DarkG/Documents/Github/Scr4per/db/schema.sql
   ```

## 2) Configurar variables de entorno

- Copia `db/.env.example` a `db/.env` y edita los valores:

```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=scr4per
POSTGRES_USER=scr4per_user
POSTGRES_PASSWORD=your_password_here
```

## 3) Crear y activar entorno virtual

Usando PowerShell en la carpeta del repo:

```powershell
python -m venv venv_api ; .\venv_api\Scripts\Activate.ps1 ; python -m pip install --upgrade pip
```

## 4) Instalar dependencias de la API

```powershell
pip install -r .\api\requirements.txt
```

## 5) Probar conexión a la DB

Asegúrate de tener `db/.env` configurado y ejecuta:

```powershell
python .\db\connect_test.py
```

Deberías ver "Connected!" con la versión de PostgreSQL.

## 6) Ejecutar la API

```powershell
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

- Healthcheck: http://127.0.0.1:8000/health
- Docs interactivos (Swagger): http://127.0.0.1:8000/docs

Asegúrate de que `db/.env` existe y la DB está accesible.

## 7) Esquema de la base (resumen)

- `profiles`: perfiles únicos por `platform` + `username` con `full_name`, `profile_url`, `photo_url`.
- `relationships`: relaciones follower/following para un `owner_profile`.
- `posts`: posts por plataforma y URL (para X comentaristas, reutilizable IG/FB).
- `comments`: quién comentó qué `post`.

Incluye índices y restricciones de unicidad para evitar duplicados.

## 8) Insertar datos con la API (ejemplos en PowerShell)

Usa `Invoke-RestMethod` en PowerShell 5.1:

1) Crear/actualizar un perfil

```powershell
$body = '{
  "platform": "x",
  "username": "ibaillanos",
  "full_name": "Ibai Llanos",
  "profile_url": "https://x.com/ibaillanos",
  "photo_url": "https://pbs.twimg.com/profile_images/..."
}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/profiles" -Method Post -ContentType 'application/json' -Body $body
```

2) Insertar relación (seguidor o seguido)

```powershell
$body = '{
  "platform": "x",
  "owner_username": "ibaillanos",
  "related_username": "some_follower",
  "rel_type": "follower"
}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/relationships" -Method Post -ContentType 'application/json' -Body $body
```

3) Insertar post

```powershell
$body = '{
  "platform": "x",
  "owner_username": "ibaillanos",
  "post_url": "https://x.com/ibaillanos/status/1234567890"
}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/posts" -Method Post -ContentType 'application/json' -Body $body
```

4) Insertar comentarista (requiere que el post exista)

```powershell
$body = '{
  "platform": "x",
  "post_url": "https://x.com/ibaillanos/status/1234567890",
  "commenter_username": "comment_user"
}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/comments" -Method Post -ContentType 'application/json' -Body $body
```

Notas:
- Los endpoints hacen upsert de perfiles automáticamente (salvo `/comments` que exige que el post exista).
- `platform` acepta: `x`, `instagram`, `facebook`.
- `rel_type` acepta: `follower` o `following`.

## 9) Cómo mapear los datos de tus scrapers

Basado en tu scraper de X descrito en el MD:

- Perfil principal: envía a `/profiles` el `username`, `full_name`, `profile_url` y `photo_url`.
- Seguidores/Seguidos: por cada usuario de la lista, llama a `/relationships` con `owner_username` del perfil principal y `related_username` del usuario, con `rel_type` según corresponda.
- Comentadores: primero crea el `post` con `/posts` usando `post_url`, luego por cada comentarista llama a `/comments`.

Para Instagram/Facebook puedes reutilizar el mismo patrón, usando `platform` igual a `instagram` o `facebook`.

## 10) Troubleshooting

- Error de conexión: revisa `db/.env` y que PostgreSQL esté levantado y acepte conexiones (`pg_hba.conf`).
- "platform mismatch for post_url": el post existe con otra plataforma; verifica los datos.
- Duplicados: los `ON CONFLICT` evitan duplicados y devuelven `inserted=false`.

## 11) Limpieza

Para borrar todo el esquema (¡destructivo!):

```sql
DROP TABLE IF EXISTS comments, posts, relationships, profiles CASCADE;
DROP TYPE IF EXISTS platform_enum, rel_type_enum;
```
