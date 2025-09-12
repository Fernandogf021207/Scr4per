import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Make repo root importable
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

def create_app() -> FastAPI:
    app = FastAPI(title="Scr4per DB API", version="0.1.0")

    # CORS
    _default_frontend_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://localhost:5173",
    ]
    _extra_origins = [o.strip() for o in (os.getenv("FRONTEND_ORIGINS") or "").split(",") if o.strip()]
    _allowed_origins = list({*(_default_frontend_origins + _extra_origins)})
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static mounts
    # Directorio real: <repo>/data/storage
    # Exponemos dos prefijos:
    #  - /data/storage  (contrato actual devuelto por upload-image)
    #  - /storage       (alias de compatibilidad)
    # Esto permite eliminar cualquier carpeta duplicada bajo api/.
    storage_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'storage'))
    if os.path.isdir(storage_root):
        # Principal según contrato vigente devuelto por /files/upload-image
        app.mount("/data/storage", StaticFiles(directory=storage_root), name="data_storage")
        # Alias de compatibilidad
        app.mount("/storage", StaticFiles(directory=storage_root), name="storage_compat")

    # Routers
    from .routers.health import router as health_router
    from .routers.proxy import router as proxy_router
    from .routers.graph_session import router as graph_session_router
    from .routers.profiles import router as profiles_router
    from .routers.relationships import router as relationships_router
    from .routers.posts import router as posts_router
    from .routers.comments import router as comments_router
    from .routers.reactions import router as reactions_router
    from .routers.related import router as related_router
    from .routers.scrape import router as scrape_router
    from .routers.export import router as export_router
    from .routers.files import router as files_router

    app.include_router(health_router)
    app.include_router(proxy_router)
    app.include_router(graph_session_router)
    app.include_router(profiles_router)
    app.include_router(relationships_router)
    app.include_router(posts_router)
    app.include_router(comments_router)
    app.include_router(reactions_router)
    app.include_router(related_router)
    app.include_router(scrape_router)
    app.include_router(export_router)
    app.include_router(files_router, prefix="/files")

    return app

app = create_app()