import json
import uuid
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse
from app.agents.audit_graph import audit_agent
from app.core.config import get_settings
from app.core.presets import PRESET_CATALOG, generate_preset_pdf
from app.rag.hybrid_store import get_policy_store
from app.rag.parser import ParsedDocument, parse_document
from data.presets.seed_policies import DEFAULT_POLICIES

router = APIRouter(prefix="/api", tags=["VeriAudit API"])
limiter = Limiter(key_func=get_remote_address)


class NewPolicyRequest(BaseModel):
    rule_code: str = Field(..., min_length=3, max_length=20, examples=["FIN-099"])
    category: Literal["procurement", "expense", "contract"] = "procurement"
    section: str = Field(..., min_length=3, max_length=120)
    content: str = Field(..., min_length=10, max_length=1000)


def _stream_audit_pipeline(parsed: ParsedDocument, policy_domain: str):
    session_id = f"audit-{uuid.uuid4().hex[:8]}"

    # Event 1: Kirim info hasil parsing & pratinjau halaman 1 ke frontend
    yield {
        "event": "parsed",
        "data": json.dumps(
            {
                "session_id": session_id,
                "filename": parsed.filename,
                "page_count": parsed.page_count,
                "is_scanned": parsed.is_scanned,
                "preview_image_b64": (
                    parsed.page_images_b64[0] if parsed.page_images_b64 else None
                ),
            }
        ),
    }

    initial_state = {
        "session_id": session_id,
        "filename": parsed.filename,
        "extracted_text": parsed.extracted_text,
        "page_images_b64": parsed.page_images_b64,
        "is_scanned": parsed.is_scanned,
        "policy_domain": policy_domain,
        "extracted_data": None,
        "retrieved_policies": [],
        "draft_verdict": None,
        "critic_passed": False,
        "retry_count": 0,
        "refined_query": None,
        "final_verdict": None,
        "node_trace": [],
    }

    accumulated = dict(initial_state)

    try:
        for update in audit_agent.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in update.items():
                accumulated.update(node_output)
                latest_trace = (
                    node_output.get("node_trace", [])[-1]
                    if node_output.get("node_trace")
                    else {
                        "node": node_name,
                        "status": "completed",
                        "latency_ms": 0,
                        "detail": "",
                    }
                )
                yield {
                    "event": "node_update",
                    "data": json.dumps(
                        {
                            "node": node_name,
                            "trace": latest_trace,
                            "extracted_data": accumulated.get("extracted_data"),
                            "retrieved_policies": accumulated.get(
                                "retrieved_policies", []
                            ),
                        }
                    ),
                }

        yield {
            "event": "final_result",
            "data": json.dumps(
                {
                    "session_id": session_id,
                    "extracted_data": accumulated.get("extracted_data"),
                    "retrieved_policies": accumulated.get("retrieved_policies", []),
                    "final_verdict": accumulated.get("final_verdict"),
                    "node_trace": accumulated.get("node_trace", []),
                }
            ),
        }
    except Exception as exc:
        yield {
            "event": "error",
            "data": json.dumps({"message": str(exc)}),
        }


@router.get("/health")
def health_check():
    settings = get_settings()
    return {
        "status": "healthy",
        "app": settings.app_name,
        "collection": settings.qdrant_collection_name,
        "vision_models": settings.gemini_vision_models,
        "reasoning_model": settings.groq_primary_model,
    }


@router.get("/presets")
def list_presets():
    return {"presets": PRESET_CATALOG}


@router.get("/policies")
def list_policies():
    store = get_policy_store()
    store.ensure_collection()
    records, _ = store.client.scroll(
        collection_name=store.collection_name,
        limit=100,
        with_payload=True,
    )
    items = [r.payload for r in records if r.payload]
    items.sort(key=lambda x: x.get("rule_code", ""))
    return {"total": len(items), "policies": items}


@router.get("/evals")
def get_benchmark_results():
    eval_file = Path(__file__).resolve().parent.parent.parent / "eval" / "results.json"
    if not eval_file.exists():
        return {"available": False}
    data = json.loads(eval_file.read_text(encoding="utf-8"))
    return {"available": True, **data}


@router.post("/policies")
@limiter.limit("10/minute")
def add_custom_policy(request: Request, body: NewPolicyRequest):
    store = get_policy_store()
    count = store.upsert_policies([body.model_dump()])
    return {"status": "indexed", "upserted": count, "policy": body.model_dump()}


@router.post("/policies/reset")
@limiter.limit("5/minute")
def reset_default_policies(request: Request):
    store = get_policy_store()
    count = store.upsert_policies(DEFAULT_POLICIES)
    return {"status": "reset_complete", "total_indexed": count}


@router.post("/audit/preset/{preset_id}/stream")
@limiter.limit("15/minute")
def stream_preset_audit(
    request: Request,
    preset_id: str,
    policy_domain: str = "all",
):
    try:
        pdf_bytes, filename, default_domain = generate_preset_pdf(preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    domain_to_use = default_domain if policy_domain == "all" else policy_domain
    parsed = parse_document(pdf_bytes, filename)
    return EventSourceResponse(_stream_audit_pipeline(parsed, domain_to_use))


@router.post("/audit/upload/stream")
@limiter.limit("10/minute")
async def stream_upload_audit(
    request: Request,
    file: UploadFile = File(...),
    policy_domain: str = Form("all"),
):
    settings = get_settings()
    file_bytes = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="File kosong tidak dapat diproses.")
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Ukuran file melebihi batas maksimal {settings.max_upload_size_mb} MB.",
        )

    try:
        parsed = parse_document(file_bytes, file.filename or "uploaded_document.pdf")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return EventSourceResponse(_stream_audit_pipeline(parsed, policy_domain))
