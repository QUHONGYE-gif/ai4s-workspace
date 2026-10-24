"""Same-origin single-user web application; run with exactly one worker."""

import fcntl
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .agent import AgentGateway
from .catalog import CATALOG, knowledge
from .files import upload
from .models import (ChangeRequest, ChatRequest, CreateWorkflow, GenerateRequest,
                     ImportRequest, RegisterRequest, RevisionRequest)
from .service import WorkflowService
from .settings import APISettings, ProviderSettings
from .storage import Problem, Store


def create_app(data_dir=None, *, gateway_factory=AgentGateway):
    load_dotenv(".local/agent-demo.env", override=False)
    store = Store(data_dir or os.environ.get("AI4S_DEMO_DATA", ".local/agent-demo"))
    service = WorkflowService(store)
    settings = ProviderSettings(store)
    gateway = gateway_factory(settings, service)

    @asynccontextmanager
    async def lifespan(app):
        # A process lock makes the documented JSON/single-worker boundary real.
        with (store.root / "server.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("同一数据目录只允许一个服务进程；请使用 --workers 1") from None
            yield
            fcntl.flock(lock, fcntl.LOCK_UN)

    app = FastAPI(title="AI4S Workflow Demo", version="0.1.0", lifespan=lifespan)
    app.state.service, app.state.gateway = service, gateway

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
            parts = urlsplit(origin)
            if not parts.scheme or parts.netloc != request.headers.get("host"):
                return JSONResponse({"error": "不允许跨站修改配置"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return JSONResponse({"error": exc.message, "details": exc.details}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        # Pydantic's default error embeds input (including a malformed API key).
        errors = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse({"error": "请求字段不符合接口要求", "details": errors}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "agent": settings.public(), "adapter": "not_connected", "storage": "single_process_json"}

    @app.get("/api/models")
    def models():
        return {"models": [{"id": key, **value, "documentation": knowledge(key)} for key, value in CATALOG.items()]}

    @app.get("/api/settings/model")
    def get_settings():
        return settings.public()

    @app.post("/api/settings/model")
    def save_settings(request: APISettings):
        return settings.update(request)

    @app.post("/api/settings/model/test")
    async def test_settings():
        return await gateway.test_connection()

    @app.get("/api/workflows")
    def list_workflows():
        return {"workflows": store.list_workflows()}

    @app.post("/api/workflows", status_code=201)
    def create_workflow(request: CreateWorkflow):
        return service.create(request)

    @app.get("/api/workflows/{workflow_id}")
    def get_workflow(workflow_id: str):
        return service.get(workflow_id)

    @app.get("/api/files")
    def list_files():
        with store.lock:
            return {"files": [store.read("files", p.stem) for p in (store.root / "files").glob("*.json")]}

    @app.post("/api/files", status_code=201)
    async def upload_file(file: UploadFile = File(...)):
        data = await file.read(5 * 1024 * 1024 + 1)
        return upload(store, file.filename or "input", data)

    @app.post("/api/workflows/{workflow_id}/changes")
    def changes(workflow_id: str, request: ChangeRequest):
        return service.change(workflow_id, request)

    @app.post("/api/workflows/{workflow_id}/undo")
    def undo(workflow_id: str, request: RevisionRequest):
        return service.undo(workflow_id, request)

    @app.post("/api/workflows/{workflow_id}/registrations")
    def register(workflow_id: str, request: RegisterRequest):
        return service.register(workflow_id, request)

    @app.post("/api/workflows/{workflow_id}/requests")
    def generate(workflow_id: str, request: GenerateRequest):
        return service.generate(workflow_id, request.registration_id)

    @app.post("/api/workflows/{workflow_id}/messages")
    async def messages(workflow_id: str, request: ChatRequest):
        return await gateway.chat(workflow_id, request)

    @app.post("/api/workflows/{workflow_id}/import-preview")
    async def import_preview(workflow_id: str, request: ImportRequest):
        service.get(workflow_id)
        return await gateway.extract(workflow_id, request)

    web = Path(__file__).parent / "web"
    app.mount("/assets", StaticFiles(directory=web), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(web / "index.html")

    return app
