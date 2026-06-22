"""FastAPI application: REST API + web UI for PriceSwitch."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import __version__, auth
from .controller import SwitchController
from .database import EventLog
from .env_config import env_config
from .gpio import gpio_controller
from .logging_config import configure_logging
from .providers import list_providers
from .schemas import SettingsUpdate
from .settings import SettingsStore

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("Starting PriceSwitch v%s", __version__)

    store = SettingsStore(env_config.resolve(env_config.config_file))
    event_log = EventLog(env_config.resolve(env_config.db_file))
    controller = SwitchController(store, gpio_controller, event_log)

    app.state.store = store
    app.state.event_log = event_log
    app.state.controller = controller

    await controller.start()
    try:
        yield
    finally:
        await controller.stop()
        event_log.close()
        logger.info("PriceSwitch stopped")


app = FastAPI(title="PriceSwitch", version=__version__, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=env_config.secret_key)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# --- dependencies ----------------------------------------------------------
def get_store(request: Request) -> SettingsStore:
    return request.app.state.store


def get_controller(request: Request) -> SwitchController:
    return request.app.state.controller


def get_event_log(request: Request) -> EventLog:
    return request.app.state.event_log


def api_guard(request: Request) -> None:
    """Reject unauthenticated API calls when auth is enabled."""
    if not auth.is_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required")


# --- auth routes -----------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if auth.is_authenticated(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"error": None, "version": __version__}
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form(...)):
    if auth.verify_password(password):
        auth.login_session(request)
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Incorrect password", "version": __version__},
        status_code=401,
    )


@app.get("/logout")
async def logout(request: Request):
    auth.logout_session(request)
    return RedirectResponse(url="/login", status_code=303)


# --- pages -----------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    redirect = auth.require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"version": __version__, "auth_enabled": auth.auth_enabled()},
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    redirect = auth.require_auth(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"version": __version__, "auth_enabled": auth.auth_enabled()},
    )


# --- JSON API --------------------------------------------------------------
@app.get("/api/status")
async def api_status(
    request: Request,
    controller: SwitchController = Depends(get_controller),
    _=Depends(api_guard),
):
    return controller.snapshot().to_dict()


@app.get("/api/providers")
async def api_providers(_=Depends(api_guard)):
    return [
        {
            "id": p.id,
            "name": p.name,
            "tier": p.tier,
            "requires_key": p.requires_key,
            "zones": p.zones,
            "zone_hint": p.zone_hint,
            "homepage": p.homepage,
            "needs_token_env": p.needs_token_env,
        }
        for p in list_providers()
    ]


@app.get("/api/settings")
async def api_get_settings(
    store: SettingsStore = Depends(get_store),
    _=Depends(api_guard),
):
    return store.current.model_dump()


@app.put("/api/settings")
async def api_update_settings(
    update: SettingsUpdate,
    store: SettingsStore = Depends(get_store),
    controller: SwitchController = Depends(get_controller),
    _=Depends(api_guard),
):
    try:
        new_settings = store.update(update.to_update_dict())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    controller.request_refresh()
    return new_settings.model_dump()


@app.get("/api/events")
async def api_events(
    limit: int = 100,
    event_log: EventLog = Depends(get_event_log),
    _=Depends(api_guard),
):
    limit = max(1, min(limit, 500))
    return event_log.recent(limit)


@app.get("/api/health")
async def api_health():
    return JSONResponse({"status": "ok", "version": __version__})
