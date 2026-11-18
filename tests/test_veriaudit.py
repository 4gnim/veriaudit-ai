import io
import fitz
from fastapi.testclient import TestClient
from PIL import Image
from app.agents.audit_graph import critic_node
from app.core.presets import generate_preset_pdf
from app.main import app
from app.rag.parser import parse_document

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert "collection" in body
    assert len(body["vision_models"]) > 0


def test_presets_endpoint_and_pdf_generation():
    res = client.get("/api/presets")
    assert res.status_code == 200
    presets = res.json()["presets"]
    assert len(presets) == 3

    for item in presets:
        pdf_bytes, filename, domain = generate_preset_pdf(item["id"])
        assert len(pdf_bytes) > 500
        assert filename.endswith(".pdf")
        assert domain in {"procurement", "expense", "contract"}


def test_multimodal_parser_pdf_and_image():
    pdf_bytes, filename, _ = generate_preset_pdf("invoice_violation")
    parsed_pdf = parse_document(pdf_bytes, filename)
    assert parsed_pdf.page_count == 1
    assert parsed_pdf.is_scanned is False
    assert "INV-2026-0891" in parsed_pdf.extracted_text
    assert len(parsed_pdf.page_images_b64) == 1

    # Uji parsing input berupa gambar PNG langsung (simulasi foto struk)
    img = Image.new("RGB", (400, 200), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    parsed_img = parse_document(buf.getvalue(), "struk_makan.png")
    assert parsed_img.page_count == 1
    assert parsed_img.is_scanned is True
    assert len(parsed_img.page_images_b64) == 1


def test_upload_guardrails_reject_invalid_and_oversized_files():
    # 1. File kosong harus ditolak (400)
    res_empty = client.post(
        "/api/audit/upload/stream",
        files={"file": ("kosong.pdf", b"", "application/pdf")},
    )
    assert res_empty.status_code == 400

    # 2. Ekstensi tidak didukung harus ditolak (400)
    res_ext = client.post(
        "/api/audit/upload/stream",
        files={"file": ("malware.exe", b"MZ9000", "application/octet-stream")},
    )
    assert res_ext.status_code == 400

    # 3. File melebihi batas 5 MB harus ditolak (413)
    oversized_payload = b"0" * (6 * 1024 * 1024)
    res_large = client.post(
        "/api/audit/upload/stream",
        files={"file": ("besar.pdf", oversized_payload, "application/pdf")},
    )
    assert res_large.status_code == 413


def test_policy_schema_validation_guardrail():
    # Mengirim rule_code terlalu pendek (< 3 karakter) harus ditolak Pydantic (422)
    res = client.post(
        "/api/policies",
        json={
            "rule_code": "A",
            "category": "procurement",
            "section": "Judul Pendek",
            "content": "Isi aturan minimal sepuluh karakter.",
        },
    )
    assert res.status_code == 422


def test_critic_node_catches_hallucinated_rule_code():
    """
    Memastikan Critic Node secara deterministik menolak draft putusan
    jika mengutip rule_code yang tidak ada di hasil retrieval Qdrant.
    """
    fake_state = {
        "session_id": "test-critic-guard",
        "filename": "dummy.pdf",
        "extracted_text": "",
        "page_images_b64": [],
        "is_scanned": False,
        "policy_domain": "all",
        "extracted_data": {"document_type": "invoice", "total_amount": 1000000},
        "retrieved_policies": [
            {
                "rule_code": "PROC-001",
                "category": "procurement",
                "section": "Batas PO",
                "content": "Aturan PO",
                "relevance_score": 0.85,
            }
        ],
        "draft_verdict": {
            "overall_status": "REJECTED",
            "risk_score": 90,
            "summary": "Melanggar aturan fiktif",
            "findings": [
                {
                    "rule_code": "FAKE-999",
                    "status": "VIOLATION",
                    "reason": "Kode aturan karangan LLM",
                }
            ],
            "critic_notes": "",
        },
        "critic_passed": False,
        "retry_count": 0,
        "refined_query": None,
        "final_verdict": None,
        "node_trace": [],
    }

    output = critic_node(fake_state)
    assert output["critic_passed"] is False
    assert output["retry_count"] == 1
    assert "FAKE-999" in output["refined_query"]
