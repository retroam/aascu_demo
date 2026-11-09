"""Run shared Workbench routes privately behind the main app's authenticated proxy."""
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
STARTER = ROOT.parent / "pdp-datathon-starter"
STORAGE = ROOT / ".data/workbench"
STORAGE.mkdir(parents=True, exist_ok=True)

# Override before importing Playground settings; never inherit its database choice.
os.environ["DATABASE_URL"] = f"sqlite:///{STORAGE / 'pdp.sqlite'}"
os.environ["APP_ENV"] = "production"
os.environ["SANDBOX_ENABLED"] = "true"
sys.path.insert(0, str(STARTER / "playground/server_application"))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.core.errors import register_exception_handlers
from app.sandbox.dictionary.routes import router as dictionary_router
from app.sandbox.pipeline.routes import router as pipeline_router
from app.sandbox.pipeline import service, uploads
import pdp_model
import yaml

service.TABLES_DIR = STORAGE / "tables"
uploads.UPLOADS_DIR = STORAGE / "uploads"
# Keep staging rows and validation reports local as well as the final database.
pipeline = yaml.safe_load(pdp_model.PIPELINE_CONFIG.read_text())
pipeline.update(logs_dir=str(STORAGE / "logs"), staging_dir=str(STORAGE / "staging"))
pdp_model.PIPELINE_CONFIG = STORAGE / "pipeline.yaml"
pdp_model.PIPELINE_CONFIG.write_text(yaml.safe_dump(pipeline, sort_keys=False))

app = FastAPI(title="Demo Workbench", docs_url=None, redoc_url=None, openapi_url=None)
register_exception_handlers(app)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


@app.middleware("http")
async def local_requests(request: Request, call_next):
    """Accept the main proxy, which checks browser origins before stripping them."""
    origin = request.headers.get("origin")
    if origin:
        return JSONResponse({"error": {"message": "Use Workbench through the main app."}}, status_code=403)
    try:
        host = urlsplit("//" + request.headers.get("host", ""))
        valid_host = host.hostname in ("127.0.0.1", "localhost") and host.port == 8100
    except ValueError:
        valid_host = False
    if not valid_host:
        return JSONResponse({"error": {"message": "Use the local Workbench port."}}, status_code=403)
    return await call_next(request)


@app.get("/health")
def health():
    """Identify this isolated API without exposing local paths or records."""
    return {"service": "demo-workbench", "separate_data": True, "active_run": service._active_run}


app.include_router(dictionary_router, prefix="/api/v1")
app.include_router(pipeline_router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100)
