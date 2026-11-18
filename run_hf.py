import os

# Matikan Node SSR Proxy Gradio 6 agar trafik '/' dan SSE streaming langsung ditangani FastAPI
os.environ["GRADIO_SSR_MODE"] = "false"
os.environ["NO_PROXY"] = "localhost,127.0.0.1,0.0.0.0"
os.environ["no_proxy"] = "localhost,127.0.0.1,0.0.0.0"

import gradio as gr
import gradio.routes
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.api.routes import limiter, router
from app.main import FRONTEND_DIR
from app.rag.hybrid_store import get_policy_store
from data.presets.seed_policies import seed_default_policies

try:
    import spaces

    @spaces.GPU
    def gpu_health_ping(text: str) -> str:
        return f"VeriAudit AI Ready: {text}"

except ImportError:

    def gpu_health_ping(text: str) -> str:
        return f"VeriAudit AI Ready: {text}"


# Pastikan Qdrant Cloud terisi SOP dasar sebelum server mulai menerima request
store = get_policy_store()
store.ensure_collection()
info = store.client.get_collection(store.collection_name)
if (info.points_count or 0) == 0:
    seed_default_policies()

# Sisipkan FastAPI routes & Split-Pane UI ke dalam FastAPI internal milik Gradio
_orig_create_app = gradio.routes.App.create_app


def _custom_create_app(blocks, *args, **kwargs):
    gradio_app = _orig_create_app(blocks, *args, **kwargs)

    # Ganti rute root '/' bawaan Gradio dengan antarmuka Split-Pane VeriAudit AI
    gradio_app.router.routes = [
        r for r in gradio_app.router.routes if getattr(r, "path", None) != "/"
    ]

    gradio_app.state.limiter = limiter
    gradio_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    gradio_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    gradio_app.include_router(router)

    if FRONTEND_DIR.exists():
        gradio_app.mount(
            "/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static"
        )

    # Dukung GET dan HEAD agar healthcheck Gradio (url_ok) selalu menerima HTTP 200
    @gradio_app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def serve_frontend():
        return FileResponse(FRONTEND_DIR / "index.html")

    return gradio_app


gradio.routes.App.create_app = _custom_create_app

with gr.Blocks(title="VeriAudit AI") as demo:
    gr.Markdown("# VeriAudit AI")
    with gr.Row(visible=False):
        ping_input = gr.Textbox(value="OK")
        ping_output = gr.Textbox()
        ping_btn = gr.Button("Ping")
        ping_btn.click(fn=gpu_health_ping, inputs=ping_input, outputs=ping_output)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", ssr_mode=False)
