"""Same-origin single-user web application; run with exactly one worker."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ai4s_declarations import DeclarationRegistry
from .declarations import DeclarationService, DeclarationCreate, DeclarationPreview, DeclarationConfirm, DeclarationChat
from .declaration_agent import DeclarationAgent
from .agent import AgentGateway
from .catalog import CATALOG, knowledge
from .task_catalog import task_catalog
from .files import upload
from .lock import acquire_lock, release_lock
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
    registry = DeclarationRegistry(Path(__file__).resolve().parents[2] / "configs/task_declarations")
    declarations = DeclarationService(store, registry)
    declaration_agent = DeclarationAgent(gateway, declarations)

    @asynccontextmanager
    async def lifespan(app):
        # A process lock makes the documented JSON/single-worker boundary real.
        # Read+write so the Windows byte-range lock is allowed on this handle.
        with (store.root / "server.lock").open("a+") as lock:
            try:
                acquire_lock(lock)
            except BlockingIOError:
                raise RuntimeError("同一数据目录只允许一个服务进程；请使用 --workers 1") from None
            yield
            release_lock(lock)

    app = FastAPI(title="AI4S Workflow Demo", version="0.1.0", lifespan=lifespan)
    app.state.service, app.state.gateway = service, gateway
    app.state.declarations, app.state.registry = declarations, registry

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

    @app.get("/api/graph-contract")
    def graph_contract():
        return {"schema_version": "ai4s-graph-1", "changes": ChangeRequest.model_json_schema(),
                "execution_connected": False,
                "relation_kinds": {"feedback": "设计反馈，不绑定输入", "reference": "产物参考，不绑定输入"},
                "layouts": ["layered", "circle"], "models": CATALOG}

    @app.get("/api/task-declarations")
    def declaration_list():
        return {"declarations": registry.list()}

    @app.get("/api/task-catalog")
    def registration_catalog():
        return task_catalog(registry)

    @app.get("/api/task-declarations/{task_id}/{version}")
    def declaration_definition(task_id: str, version: str):
        try: return registry.get(task_id, version)
        except KeyError: raise Problem(404, "invalid_declaration") from None

    @app.get("/api/declaration-drafts")
    def declaration_drafts(deleted: bool = False):
        return {"drafts": declarations.list(deleted=deleted)}

    @app.post("/api/declaration-drafts", status_code=201)
    def declaration_create(request: DeclarationCreate):
        return declarations.create(request)

    @app.post("/api/declaration-drafts/{draft_id}/delete")
    def delete_declaration(draft_id: str, request: RevisionRequest):
        return store.set_deleted("declaration_drafts", draft_id, request.expected_revision, True)

    @app.post("/api/declaration-drafts/{draft_id}/restore")
    def restore_declaration(draft_id: str, request: RevisionRequest):
        return store.set_deleted("declaration_drafts", draft_id, request.expected_revision, False)

    @app.get("/api/declaration-drafts/{draft_id}")
    def declaration_draft(draft_id: str):
        return declarations.get(draft_id)

    @app.post("/api/declaration-drafts/{draft_id}/preview")
    def declaration_preview(draft_id: str, request: DeclarationPreview):
        return declarations.preview(draft_id, request)

    @app.post("/api/declaration-drafts/{draft_id}/confirm")
    def declaration_confirm(draft_id: str, request: DeclarationConfirm):
        return declarations.confirm(draft_id, request)

    @app.post("/api/declaration-drafts/{draft_id}/cancel")
    def declaration_cancel(draft_id: str, request: DeclarationConfirm):
        return declarations.confirm(draft_id, request, cancel=True)

    @app.post("/api/declaration-drafts/{draft_id}/export")
    def declaration_export(draft_id: str, request: RevisionRequest):
        return declarations.export(draft_id, request.expected_revision)

    @app.post("/api/declaration-drafts/{draft_id}/messages")
    async def declaration_message(draft_id: str, request: DeclarationChat):
        return await declaration_agent.chat(draft_id, request)

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
    def list_workflows(deleted: bool = False):
        return {"workflows": store.list_workflows(deleted=deleted)}

    @app.post("/api/workflows", status_code=201)
    def create_workflow(request: CreateWorkflow):
        return service.create(request)

    @app.post("/api/workflows/{workflow_id}/delete")
    def delete_workflow(workflow_id: str, request: RevisionRequest):
        return store.set_deleted("workflows", workflow_id, request.expected_revision, True)

    @app.post("/api/workflows/{workflow_id}/restore")
    def restore_workflow(workflow_id: str, request: RevisionRequest):
        return store.set_deleted("workflows", workflow_id, request.expected_revision, False)

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

    @app.post("/api/workflows/{workflow_id}/changes/preview")
    def preview_changes(workflow_id: str, request: ChangeRequest):
        with store.lock:
            service._revision(service._read(workflow_id), request.expected_revision)
            return {"summary": service.preview_changes(workflow_id, request.operations)}

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

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def index():
        return RedirectResponse("../workbench.html#/workflows/editor", status_code=307)

    return app
