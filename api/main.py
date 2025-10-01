import os
import sys
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from paths import STORAGE_DIR, PUBLIC_IMAGES_PREFIX_PRIMARY, PUBLIC_IMAGES_PREFIX_COMPAT, ensure_dirs

# Make repo root importable
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

def create_app() -> FastAPI:
    app = FastAPI(title="Scr4per DB API", version="0.1.0")

    # Ensure logging configured (scripts call setup_logging, API didn't)
    try:
        # Avoid reconfiguring if already handled by uvicorn or previous setup
        if not logging.getLogger().handlers:
            from src.utils.logging_config import setup_logging  # type: ignore
            setup_logging()
        else:
            # Raise root level if default WARNING so our scraper INFO logs show
            if logging.getLogger().level > logging.INFO:
                logging.getLogger().setLevel(logging.INFO)
    except Exception as e:  # pragma: no cover
        logging.getLogger(__name__).warning(f"logging setup skip error={e}")

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
    ensure_dirs()
    if os.path.isdir(STORAGE_DIR):
        app.mount("/data/storage", StaticFiles(directory=STORAGE_DIR), name="data_storage")
        app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage_compat")

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
    from .routers.multi_scrape import router as multi_scrape_router

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
    app.include_router(multi_scrape_router)

    return app

app = create_app()