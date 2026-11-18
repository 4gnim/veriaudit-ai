import json
import uuid
import fitz  # PyMuPDF
from app.agents.audit_graph import audit_agent
from app.rag.parser import parse_document


def _create_sample_invoice_pdf() -> bytes:
    """Membuat PDF invoice simulasi yang memiliki pelanggaran SOP untuk pengujian."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    text = (
        "PT NUSANTARA TECH SOLUTIONS (PKP)\n"
        "INVOICE TAGIHAN VENDOR\n"
        "--------------------------------------------------\n"
        "Nomor Invoice : INV-2026-0891\n"
        "Tanggal       : 15 November 2026\n"
        "Nomor PO      : [TIDAK ADA / TANPA PO]\n"
        "Termin        : Pembayaran DP 50% di muka\n\n"
        "Rincian Item:\n"
        "1. Pengadaan Server Rack & Switch (1 Unit)  : Rp 12.000.000\n"
        "--------------------------------------------------\n"
        "Subtotal      : Rp 12.000.000\n"
        "PPN (10%)     : Rp  1.200.000\n"
        "Total Tagihan : Rp 13.200.000\n\n"
        "Catatan: Dokumen belum ditandatangani oleh Manajer Departemen."
    )
    page.insert_text((50, 70), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


if __name__ == "__main__":
    pdf_bytes = _create_sample_invoice_pdf()
    parsed = parse_document(pdf_bytes, "sample_invoice_violation.pdf")

    initial_state = {
        "session_id": f"test-{uuid.uuid4().hex[:8]}",
        "filename": parsed.filename,
        "extracted_text": parsed.extracted_text,
        "page_images_b64": parsed.page_images_b64,
        "is_scanned": parsed.is_scanned,
        "policy_domain": "all",
        "extracted_data": None,
        "retrieved_policies": [],
        "draft_verdict": None,
        "critic_passed": False,
        "retry_count": 0,
        "refined_query": None,
        "final_verdict": None,
        "node_trace": [],
    }

    print("Menjalankan Self-Reflective Audit Agent...")
    result = audit_agent.invoke(initial_state)

    print("\n=== NODE EXECUTION TRACE ===")
    for step in result["node_trace"]:
        print(
            f"- {step['node']} [{step['status']}] ({step['latency_ms']} ms): {step['detail']}"
        )

    print("\n=== FINAL AUDIT VERDICT ===")
    print(json.dumps(result["final_verdict"], indent=2, ensure_ascii=False))
