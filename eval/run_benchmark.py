import json
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import fitz
from app.agents.audit_graph import audit_agent
from app.rag.hybrid_store import get_policy_store
from app.rag.parser import parse_document

EVAL_OUTPUT_PATH = Path(__file__).resolve().parent / "results.json"

BENCHMARK_CASES = [
    {
        "case_id": "EVAL-01",
        "name": "Procurement Invoice Tanpa PO & Salah PPN",
        "domain": "procurement",
        "expected_status": "REJECTED",
        "expected_rule_codes": ["PROC-001", "PROC-002"],
        "text": (
            "PT SINAR ABADI (PKP) - INVOICE INV-901\n"
            "Tanggal: 10 November 2026 | Nomor PO: Tidak Ada\n"
            "Item: Pengadaan 2 Unit Workstation (Rp 15.000.000)\n"
            "Subtotal: Rp 15.000.000 | PPN 10%: Rp 1.500.000 | Total: Rp 16.500.000\n"
            "Catatan: Belum ditandatangani manajer departemen."
        ),
    },
    {
        "case_id": "EVAL-02",
        "name": "Klaim Makan Dinas Sesuai Plafon",
        "domain": "expense",
        "expected_status": "APPROVED",
        "expected_rule_codes": ["EXP-001", "EXP-002"],
        "text": (
            "FORM REIMBURSEMENT KARYAWAN - EXP-302\n"
            "Tanggal Transaksi: 15 November 2026 | Tanggal Ajuan: 17 November 2026\n"
            "Item: Makan Siang Perjalanan Dinas Jakarta (1x Nasi Padang + Es Teh) Rp 85.000\n"
            "Total Klaim: Rp 85.000 | Status: Struk lunas asli & disetujui supervisor."
        ),
    },
    {
        "case_id": "EVAL-03",
        "name": "Klaim Makan Dinas Mengandung Item Terlarang",
        "domain": "expense",
        "expected_status": "REJECTED",
        "expected_rule_codes": ["EXP-001"],
        "text": (
            "FORM REIMBURSEMENT KARYAWAN - EXP-309\n"
            "Tanggal Transaksi: 16 November 2026 | Tanggal Ajuan: 17 November 2026\n"
            "Item 1: Makan Malam Klien Rp 110.000\n"
            "Item 2: Rokok & Minuman Beralkohol Rp 95.000\n"
            "Total Klaim: Rp 205.000"
        ),
    },
    {
        "case_id": "EVAL-04",
        "name": "Kontrak Vendor Akses Database Tanpa NDA",
        "domain": "contract",
        "expected_status": "REJECTED",
        "expected_rule_codes": ["CTR-002", "CTR-003"],
        "text": (
            "KONTRAK KERJA SAMA INTEGRASI DATA PELANGGAN - CTR-88\n"
            "Nilai Kontrak: Rp 45.000.000 | Termin: Net 30\n"
            "Ruang Lingkup: Vendor mengakses database produksi dan memproses data ke server luar negeri.\n"
            "Catatan: Tidak memuat klausul NDA maupun denda keterlambatan SLA."
        ),
    },
    {
        "case_id": "EVAL-05",
        "name": "Out-of-Scope Document (Abstention Check)",
        "domain": "all",
        "expected_status": "NEEDS_HUMAN_REVIEW",
        "expected_rule_codes": [],
        "text": (
            "MEMO INTERNAL ACARA GATHERING KANTOR\n"
            "Jadwal senam pagi hari Jumat pukul 07.00 WIB di halaman parkir gedung utama.\n"
            "Harap membawa botol minum masing-masing."
        ),
    },
]


def _make_pdf_bytes(content: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 70), content, fontsize=11)
    raw = doc.tobytes()
    doc.close()
    return raw


def run_evaluation():
    store = get_policy_store()
    store.ensure_collection()

    case_results = []
    retrieval_recalls = []
    verdict_matches = 0
    grounded_citations = 0
    total_citations = 0
    latencies_ms = []

    print(f"Menjalankan evaluasi pada {len(BENCHMARK_CASES)} kasus uji...")

    for case in BENCHMARK_CASES:
        t0 = time.perf_counter()
        pdf_bytes = _make_pdf_bytes(case["text"])
        parsed = parse_document(pdf_bytes, f"{case['case_id']}.pdf")

        state = {
            "session_id": f"eval-{uuid.uuid4().hex[:6]}",
            "filename": parsed.filename,
            "extracted_text": parsed.extracted_text,
            "page_images_b64": parsed.page_images_b64,
            "is_scanned": parsed.is_scanned,
            "policy_domain": case["domain"],
            "extracted_data": None,
            "retrieved_policies": [],
            "draft_verdict": None,
            "critic_passed": False,
            "retry_count": 0,
            "refined_query": None,
            "final_verdict": None,
            "node_trace": [],
        }

        out = audit_agent.invoke(state)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        latencies_ms.append(elapsed_ms)

        retrieved_codes = {p["rule_code"] for p in out["retrieved_policies"]}
        expected_codes = set(case["expected_rule_codes"])

        if expected_codes:
            recall = len(expected_codes & retrieved_codes) / len(expected_codes)
            retrieval_recalls.append(recall)
        else:
            recall = 1.0

        verdict = out["final_verdict"]
        actual_status = verdict["overall_status"]
        is_verdict_correct = actual_status == case["expected_status"]
        if is_verdict_correct:
            verdict_matches += 1

        cited_codes = [f["rule_code"] for f in verdict.get("findings", [])]
        valid_cited = [c for c in cited_codes if c in retrieved_codes]
        total_citations += len(cited_codes)
        grounded_citations += len(valid_cited)

        case_results.append(
            {
                "case_id": case["case_id"],
                "name": case["name"],
                "expected_status": case["expected_status"],
                "actual_status": actual_status,
                "verdict_match": is_verdict_correct,
                "retrieval_recall": round(recall, 2),
                "latency_ms": elapsed_ms,
            }
        )
        print(
            f"- {case['case_id']}: Expected={case['expected_status']} | "
            f"Actual={actual_status} | Recall={recall:.2f} | {elapsed_ms} ms"
        )

    summary = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(BENCHMARK_CASES),
        "verdict_accuracy_pct": round(
            (verdict_matches / len(BENCHMARK_CASES)) * 100, 1
        ),
        "avg_retrieval_recall_pct": round(statistics.mean(retrieval_recalls) * 100, 1),
        "citation_grounding_pct": round(
            (grounded_citations / total_citations) * 100 if total_citations else 100.0,
            1,
        ),
        "median_latency_ms": round(statistics.median(latencies_ms), 1),
        "cases": case_results,
    }

    EVAL_OUTPUT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\nHasil evaluasi disimpan ke:", EVAL_OUTPUT_PATH)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run_evaluation()
