import time
from typing import Any, Literal, Optional, TypedDict
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from app.core.llm_router import (
    get_langfuse_callbacks,
    invoke_multimodal_extraction_with_fallback,
    invoke_structured_with_fallback,
)
from app.rag.hybrid_store import get_policy_store
from app.schemas.audit import (
    ExtractedDocumentData,
    FinalAuditVerdict,
    PolicyCitation,
)


class CriticEvaluation(BaseModel):
    passed: bool = Field(
        ...,
        description="True jika audit sudah akurat, berdasar SOP valid, dan siap dirilis",
    )
    critique_notes: str = Field(
        ..., description="Catatan hasil pemeriksaan silang oleh Critic Node"
    )
    refined_search_query: Optional[str] = Field(
        default=None,
        description="Query pencarian SOP tambahan jika ada aturan penting yang terlewat",
    )


class AuditAgentState(TypedDict):
    session_id: str
    filename: str
    extracted_text: str
    page_images_b64: list[str]
    is_scanned: bool
    policy_domain: str
    extracted_data: Optional[dict[str, Any]]
    retrieved_policies: list[dict[str, Any]]
    draft_verdict: Optional[dict[str, Any]]
    critic_passed: bool
    retry_count: int
    refined_query: Optional[str]
    final_verdict: Optional[dict[str, Any]]
    node_trace: list[dict[str, Any]]


def _record_trace(
    state: AuditAgentState,
    node_name: str,
    start_time: float,
    status: str,
    detail: str,
) -> list[dict[str, Any]]:
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
    traces = list(state.get("node_trace", []))
    traces.append(
        {
            "node": node_name,
            "status": status,
            "latency_ms": elapsed_ms,
            "detail": detail,
        }
    )
    return traces


def extract_node(state: AuditAgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    callbacks = get_langfuse_callbacks(state.get("session_id"))

    system_prompt = (
        "Anda adalah spesialis ekstraksi dokumen keuangan dan legal perusahaan. "
        "Ekstrak seluruh informasi penting dari dokumen secara akurat ke dalam skema JSON. "
        "Periksa dengan teliti angka subtotal, pajak (PPN), total akhir, tanggal, nomor dokumen, "
        "nama vendor, daftar item, serta keberadaan tanda tangan atau stempel visual pada dokumen. "
        "Jangan mengarang angka yang tidak tertera pada dokumen."
    )

    text_prompt = (
        f"Nama file: {state['filename']}\n"
        f"Teks hasil parser PDF (kosong jika dokumen berupa scan/gambar):\n"
        f"{state['extracted_text'] or '[Tidak ada teks digital, baca langsung dari gambar halaman]'}"
    )

    extracted, provider_used = invoke_multimodal_extraction_with_fallback(
        schema=ExtractedDocumentData,
        system_prompt=system_prompt,
        text_prompt=text_prompt,
        page_images_b64=state.get("page_images_b64", []),
        callbacks=callbacks,
    )

    detail = (
        f"Provider={provider_used} | Tipe={extracted.document_type} | "
        f"Total={extracted.currency} {extracted.total_amount:,.0f} | "
        f"Confidence={extracted.extraction_confidence:.2f}"
    )
    return {
        "extracted_data": extracted.model_dump(),
        "node_trace": _record_trace(state, "extract_node", t0, "completed", detail),
    }


def retrieve_policy_node(state: AuditAgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    store = get_policy_store()
    extracted = ExtractedDocumentData(**state["extracted_data"])

    if state.get("refined_query"):
        query = state["refined_query"]
    else:
        terms_text = ", ".join(extracted.key_terms_or_notes[:4])
        items_text = ", ".join(item.description for item in extracted.line_items[:4])
        query = (
            f"Dokumen {extracted.document_type} dari {extracted.vendor_or_party or 'vendor'} "
            f"senilai {extracted.currency} {extracted.total_amount:,.0f}, pajak {extracted.tax_amount:,.0f}, "
            f"tanda tangan/stempel={extracted.has_signature_or_stamp}. "
            f"Item: {items_text}. Catatan: {terms_text}"
        )

    domain_filter = state.get("policy_domain", "all")
    hits = store.hybrid_search(query=query, top_k=5, category_filter=domain_filter)

    # Gabungkan dengan policy yang sudah pernah diambil jika ini adalah siklus retry
    existing = {p["rule_code"]: p for p in state.get("retrieved_policies", [])}
    for hit in hits:
        existing[hit.rule_code] = hit.model_dump()

    merged_policies = list(existing.values())
    codes = ", ".join(p["rule_code"] for p in merged_policies)
    detail = f"Ditemukan {len(merged_policies)} SOP relevan ({codes})"

    return {
        "retrieved_policies": merged_policies,
        "node_trace": _record_trace(
            state, "retrieve_policy_node", t0, "completed", detail
        ),
    }


def audit_node(state: AuditAgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    callbacks = get_langfuse_callbacks(state.get("session_id"))

    extracted_json = state["extracted_data"]
    policies = [PolicyCitation(**p) for p in state.get("retrieved_policies", [])]
    policies_context = "\n\n".join(
        f"[{p.rule_code}] ({p.category.upper()} - {p.section}): {p.content}"
        for p in policies
    )

    system_prompt = (
        "Anda adalah Senior Internal Auditor AI. Tugas Anda memeriksa kepatuhan data dokumen "
        "terhadap aturan SOP perusahaan yang tersedia di konteks.\n"
        "ATURAN KETAT:\n"
        "1. Hanya gunakan rule_code yang benar-benar ada di daftar ATURAN SOP.\n"
        "2. Lakukan perhitungan matematis secara teliti (misal: cek apakah PPN 11% dari subtotal sesuai, "
        "cek apakah total melebihi plafon batas otorisasi Rp 5.000.000 atau Rp 150.000).\n"
        "3. Jika dokumen tidak relevan dengan aturan SOP atau data terlalu minim, set overall_status "
        "menjadi 'NEEDS_HUMAN_REVIEW' dan jelaskan kekurangannya (abstention).\n"
        "4. Jika ditemukan pelanggaran aturan jelas, set overall_status menjadi 'REJECTED'."
    )

    human_prompt = (
        f"DATA DOKUMEN TERSTRUKTUR:\n{extracted_json}\n\n"
        f"ATURAN SOP YANG RELEVAN:\n{policies_context}\n\n"
        "Hasilkan putusan audit terstruktur beserta rincian temuan per rule_code."
    )

    verdict, provider_used = invoke_structured_with_fallback(
        schema=FinalAuditVerdict,
        messages=[
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ],
        prefer_provider="groq",
        callbacks=callbacks,
    )

    detail = (
        f"Provider={provider_used} | Status={verdict.overall_status} | "
        f"Risk={verdict.risk_score}/100"
    )
    return {
        "draft_verdict": verdict.model_dump(),
        "node_trace": _record_trace(state, "audit_node", t0, "completed", detail),
    }


def critic_node(state: AuditAgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    callbacks = get_langfuse_callbacks(state.get("session_id"))

    draft = FinalAuditVerdict(**state["draft_verdict"])
    valid_codes = {p["rule_code"] for p in state.get("retrieved_policies", [])}
    cited_codes = {f.rule_code for f in draft.findings}

    # 1. Validasi deterministik: cek apakah ada rule_code halusinasi
    hallucinated_codes = cited_codes - valid_codes
    if hallucinated_codes:
        detail = f"Deteksi sitasi tidak valid: {hallucinated_codes}. Memicu perbaikan."
        return {
            "critic_passed": False,
            "retry_count": state.get("retry_count", 0) + 1,
            "refined_query": f"Aturan SOP terkait {', '.join(hallucinated_codes)}",
            "node_trace": _record_trace(
                state, "critic_node", t0, "retry_triggered", detail
            ),
        }

    # 2. Pemeriksaan silang oleh LLM Critic
    system_prompt = (
        "Anda adalah Quality Assurance Critic untuk sistem audit AI. "
        "Periksa apakah Draft Putusan Audit sudah konsisten dengan Data Dokumen dan Aturan SOP yang tersedia. "
        "Pastikan tidak ada aturan penting yang terlewat (misalnya batas nominal otorisasi PO, tarif pajak PPN 11%, "
        "atau kelengkapan tanda tangan). Jika sudah konsisten dan menyeluruh, set passed=True."
    )

    human_prompt = (
        f"DATA DOKUMEN:\n{state['extracted_data']}\n\n"
        f"ATURAN SOP TERSEDIA:\n{state['retrieved_policies']}\n\n"
        f"DRAFT PUTUSAN AUDIT:\n{draft.model_dump()}\n\n"
        "Evaluasi kualitas draft putusan di atas."
    )

    critique, provider_used = invoke_structured_with_fallback(
        schema=CriticEvaluation,
        messages=[
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ],
        prefer_provider="groq",
        callbacks=callbacks,
    )

    current_retries = state.get("retry_count", 0)
    if not critique.passed and current_retries < 1 and critique.refined_search_query:
        detail = f"Critic meminta retrieval tambahan ({provider_used}): {critique.critique_notes[:80]}"
        return {
            "critic_passed": False,
            "retry_count": current_retries + 1,
            "refined_query": critique.refined_search_query,
            "node_trace": _record_trace(
                state, "critic_node", t0, "retry_triggered", detail
            ),
        }

    # Lolos verifikasi -> finalisasi putusan
    draft.critic_notes = f"[Verified by {provider_used}] {critique.critique_notes}"
    detail = f"Lolos verifikasi ({provider_used}) | Retry={current_retries}"
    return {
        "critic_passed": True,
        "final_verdict": draft.model_dump(),
        "node_trace": _record_trace(state, "critic_node", t0, "completed", detail),
    }


def route_after_critic(
    state: AuditAgentState,
) -> Literal["retrieve_policy_node", "__end__"]:
    if not state.get("critic_passed", True) and state.get("retry_count", 0) <= 1:
        return "retrieve_policy_node"
    return END


def build_audit_graph():
    builder = StateGraph(AuditAgentState)

    builder.add_node("extract_node", extract_node)
    builder.add_node("retrieve_policy_node", retrieve_policy_node)
    builder.add_node("audit_node", audit_node)
    builder.add_node("critic_node", critic_node)

    builder.add_edge(START, "extract_node")
    builder.add_edge("extract_node", "retrieve_policy_node")
    builder.add_edge("retrieve_policy_node", "audit_node")
    builder.add_edge("audit_node", "critic_node")
    builder.add_conditional_edges(
        "critic_node",
        route_after_critic,
        {
            "retrieve_policy_node": "retrieve_policy_node",
            END: END,
        },
    )

    return builder.compile()


audit_agent = build_audit_graph()
