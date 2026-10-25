"""SAM SPACE FastAPI application.

One process serves the API (/api/...), the logo (/brand/...), and the built
React app (frontend/dist). Teaching staff need only Python. Node is needed only
to change the frontend.
"""

from __future__ import annotations

import logging
import threading

from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai.availability import ModelAvailability, check_availability, describe_tiers
from .ai.providers import AIProvider
from .api.deps import CSRF_HEADER
from .agents.manager import WorkflowManager
from .api.routes import activity, auth, donations as donation_routes, safety as safety_routes, experiments, finance as finance_routes, legacy, legacy_imports, mission, outputs, records, runs, settings as settings_routes, studio, system, workspace
from .core.config import Settings, get_settings
from .core.env import REPO_ROOT
from .core.ratelimit import LoginLimiter
from .db.database import Database

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
BRAND_DIR = REPO_ROOT / "assets"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
    "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def create_app(settings: Settings | None = None, *, verify_models: bool | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="SAM SPACE", version=system.VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

    app.state.settings = settings
    app.state.db = Database(settings.database_path)
    app.state.db.initialize(seed_demo=True)
    app.state.login_limiter = LoginLimiter()
    app.state.workflows = WorkflowManager(app.state)
    app.state.workflows.mark_interrupted()
    app.state.provider = AIProvider.from_settings(settings)
    app.state.availability = ModelAvailability(
        provider=settings.provider,
        status="unverified" if settings.provider else "no_provider",
        tier_models=describe_tiers(settings.provider, None),
    )

    should_verify = settings.verify_models_on_startup if verify_models is None else verify_models
    if should_verify and app.state.provider is not None:
        def _verify() -> None:
            app.state.availability = check_availability(app.state.provider)

        threading.Thread(target=_verify, name="verify-models", daemon=True).start()

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        # Safe error messages: say which field and why, never echo the submitted values back.
        errors = [{"loc": list(e.get("loc", [])), "msg": str(e.get("msg", "Invalid value"))[:200], "type": e.get("type")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception):
        from .safety.redact import configured_secrets, redact
        logging.getLogger("sam_space").error("Unhandled error on %s: %s", request.url.path,
                                             redact(f"{type(exc).__name__}: {exc}", configured_secrets()))
        return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Same-origin check for state-changing API calls: browsers will not send
        # this custom header cross-site without a CORS preflight, which we never allow.
        if request.url.path.startswith("/api/") and request.method in UNSAFE_METHODS:
            if request.headers.get(CSRF_HEADER) != "1":
                return JSONResponse({"detail": "Missing request header."}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    for module in (system, auth, workspace, records, activity, settings_routes, runs, outputs, legacy, legacy_imports, experiments,
                   studio, mission,
                   finance_routes, donation_routes, safety_routes):
        app.include_router(module.router)

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_not_found(rest: str):
        raise HTTPException(404, "Not found.")

    if BRAND_DIR.is_dir():
        app.mount("/brand", StaticFiles(directory=BRAND_DIR), name="brand")
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        @app.get("/", include_in_schema=False)
        def no_build() -> HTMLResponse:
            return HTMLResponse(
                "<h1>SAM SPACE API is running</h1><p>The frontend build (frontend/dist) is missing. "
                "Run <code>cd frontend && npm install && npm run build</code>, then restart.</p>",
                status_code=503,
            )
        return

    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")
    dist_root = FRONTEND_DIST.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and dist_root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)
