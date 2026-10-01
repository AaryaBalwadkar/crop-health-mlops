import logging
import time

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.schemas.responses import HealthResponse, PredictionResponse

logger = logging.getLogger("agricnxedge.api")

router = APIRouter()

PREDICT_REQUESTS = Counter("agricnxedge_predict_requests_total", "Total prediction requests", ["outcome"])
PREDICT_LATENCY = Histogram("agricnxedge_predict_latency_seconds", "Prediction latency in seconds")
HTTP_REQUESTS = Counter(
    "agricnxedge_http_requests_total",
    "Total HTTP requests by method, endpoint and status code",
    ["method", "endpoint", "status_code"],
)
HTTP_ERRORS = Counter(
    "agricnxedge_http_errors_total",
    "Total HTTP errors by method, endpoint and status code",
    ["method", "endpoint", "status_code"],
)
HTTP_LATENCY = Histogram(
    "agricnxedge_http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)
APP_HEALTH = Gauge("agricnxedge_app_health", "Application health status (1 = healthy)")
MODEL_LOADED = Gauge("agricnxedge_model_loaded", "Whether the model is currently loaded")


def _endpoint_name(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    service = request.app.state.inference
    settings = request.app.state.settings
    model_loaded = bool(getattr(service, "loaded", False))
    APP_HEALTH.set(1)
    MODEL_LOADED.set(1 if model_loaded else 0)
    logger.info("Health check completed", extra={"service": settings.app_name, "model_loaded": model_loaded})
    return {
        "status": "ok",
        "service": settings.app_name,
        "model_loaded": model_loaded,
    }


@router.get("/model/status")
def model_status(request: Request):
    status_payload = request.app.state.inference.status()
    MODEL_LOADED.set(1 if status_payload.get("loaded") else 0)
    logger.info("Model status checked", extra={"loaded": status_payload.get("loaded")})
    return status_payload


@router.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.post("/predict", response_model=PredictionResponse)
async def predict(request: Request, file: UploadFile = File(...)):
    settings = request.app.state.settings
    content_type = (file.content_type or "").lower()
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if content_type not in allowed_types:
        filename = file.filename or "upload"
        PREDICT_REQUESTS.labels(outcome="rejected").inc()
        logger.warning("Rejected prediction request", extra={"file_name": filename, "content_type": content_type})
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a JPEG, PNG, or WEBP image.",
        )

    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        PREDICT_REQUESTS.labels(outcome="rejected").inc()
        logger.warning(
            "Prediction request too large",
            extra={"file_name": file.filename or "upload", "size_bytes": len(content), "max_bytes": max_bytes},
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image must be {settings.max_upload_mb} MB or smaller.",
        )

    started = time.perf_counter()
    try:
        result = request.app.state.inference.predict(content, file.filename or "upload")
        PREDICT_REQUESTS.labels(outcome="ok").inc()
        logger.info(
            "Prediction succeeded",
            extra={"file_name": file.filename or "upload", "latency_ms": result.get("latency_ms")},
        )
        return result
    except RuntimeError as exc:
        PREDICT_REQUESTS.labels(outcome="error").inc()
        logger.exception("Prediction failed", extra={"file_name": file.filename or "upload"})
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    finally:
        PREDICT_LATENCY.observe(time.perf_counter() - started)
