import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    APP_HEALTH,
    HTTP_ERRORS,
    HTTP_LATENCY,
    HTTP_REQUESTS,
    MODEL_LOADED,
    router,
)
from app.core.config import get_settings
from app.services.inference import InferenceService

logger = logging.getLogger("agricnxedge")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app):
        model_loaded = bool(app.state.inference.loaded)
        MODEL_LOADED.set(1 if model_loaded else 0)
        APP_HEALTH.set(1)
        logger.info("Application startup completed", extra={"model_loaded": model_loaded, "model_path": str(settings.model_path)})
        if model_loaded:
            logger.info("ML model loaded successfully")
        else:
            logger.warning("Model artifact missing or not loaded; prediction endpoints will return 503 until a valid model is mounted.")
        yield

    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.inference = InferenceService(settings.model_path)

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        started = time.perf_counter()
        method = request.method
        endpoint = request.url.path
        route = request.scope.get("route")
        if route is not None and getattr(route, "path", None):
            endpoint = route.path

        try:
            response = await call_next(request)
        except Exception:
            elapsed = time.perf_counter() - started
            status_code = "500"
            HTTP_REQUESTS.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            HTTP_ERRORS.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            HTTP_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)
            logger.exception("Unhandled request error", extra={"method": method, "path": endpoint})
            raise

        elapsed = time.perf_counter() - started
        status_code = str(response.status_code)
        HTTP_REQUESTS.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
        HTTP_LATENCY.labels(method=method, endpoint=endpoint).observe(elapsed)
        if response.status_code >= 400:
            HTTP_ERRORS.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
        MODEL_LOADED.set(1 if app.state.inference.loaded else 0)
        APP_HEALTH.set(1)
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.include_router(router, prefix="/api")

    static_dir = Path(os.environ.get("STATIC_DIR", "static"))
    candidates = [static_dir, Path(__file__).resolve().parents[2] / "static", Path("/app/static")]
    dist = next((p for p in candidates if (p / "index.html").exists()), None)
    if dist is not None:
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def serve_root():
            return FileResponse(dist / "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str):
            candidate = dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()
