---
title: VeriAudit AI
emoji: 🛡️
colorFrom: indigo
colorTo: slate
sdk: gradio
app_file: run_hf.py
pinned: false
---

# VeriAudit AI — Autonomous Multimodal Document Intelligence & Policy Verification Agent

**VeriAudit AI** is an end-to-end AI Engineering application designed to audit unstructured financial and legal documents (PDFs, scanned invoices, expense receipts, and vendor contracts) against company Standard Operating Procedures (SOPs).

Built with **LangGraph**, **Hybrid RAG (Dense + BM25 RRF on Qdrant Cloud)**, **Multimodal Document Parsing**, **Multi-Provider LLM Fallback**, and **Langfuse Observability**.

---

## Key Engineering Highlights

- **Multimodal Document Ingestion (`PyMuPDF` + `Pillow`):** Extracts embedded digital text and renders document pages into optimized visual inputs (`150 DPI`, resized & JPEG-compressed) for layout, table, stamp, and signature inspection.
- **Adaptive Multi-Provider LLM Routing:** Routes visual/scanned documents through a **Gemini Multimodal** cascade (`gemini-3.6-flash` / `3.5-flash-lite` / `3.1-flash-lite`) and digital-text documents through **Groq (`openai/gpt-oss-120b`)**, featuring instant zero-sleep failover across providers.
- **Hybrid Policy Retrieval (`Qdrant Cloud`):** Combines multilingual dense embeddings (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384d) and sparse lexical vectors (`Qdrant/bm25`) fused via **Reciprocal Rank Fusion (RRF)** with domain payload filtering.
- **Self-Reflective LangGraph Workflow (`Extract -> Retrieve -> Audit -> Critic`):**
  - Enforces strict **Pydantic** schemas for extracted entities (`ExtractedDocumentData`) and compliance verdicts (`FinalAuditVerdict`).
  - **Deterministic + LLM Critic Node:** Programmatically verifies that every cited `rule_code` exists in retrieved Qdrant context to eliminate hallucinated citations and triggers automatic re-retrieval when policy checks are incomplete.
  - **Abstention Guardrail:** Flags out-of-scope or low-evidence documents as `NEEDS_HUMAN_REVIEW`.
- **Real-Time SSE Streaming & Production Guardrails:** Streams node-by-node execution latency and status via Server-Sent Events (SSE), protected by IP rate limiting (`SlowAPI`) and strict file size/extension validation.

---

## System Architecture

```text
[PDF / Image Upload or 1-Click Preset]
                 │
                 ▼
      ┌─────────────────────┐
      │  Multimodal Parser  │  (PyMuPDF text + page rendering)
      └──────────┬──────────┘
                 │
                 ▼
      ┌─────────────────────┐
      │    extract_node     │  (Adaptive Gemini Vision / Groq 120B -> Pydantic JSON)
      └──────────┬──────────┘
                 │
                 ▼
      ┌─────────────────────┐
      │retrieve_policy_node │  (Qdrant Cloud Hybrid Search: Dense + BM25 RRF)
      └──────────┬──────────┘
                 │
                 ▼
      ┌─────────────────────┐
      │     audit_node      │  (SOP Compliance & Math Verification)
      └──────────┬──────────┘
                 │
                 ▼
      ┌─────────────────────┐     Retry (if hallucinated code / missing check)
      │     critic_node     │ ────────────────────────────────────────────────┐
      └──────────┬──────────┘                                                 │
                 │ Verified                                                   ▼
                 ▼                                                 [retrieve_policy_node]
      ┌─────────────────────┐
      │ Final Audit Verdict │  (APPROVED / REJECTED / NEEDS_HUMAN_REVIEW + Citations)
      └─────────────────────┘
```

---

## Automated Evaluation Benchmark (`eval/results.json`)

Evaluated across 5 golden-dataset scenarios covering procurement SOP violations, compliant expense claims, prohibited expense items, missing contract NDA/SLA clauses, and out-of-scope abstention:

| Metric                        |   Result   | Evaluation Scope                                                 |
| :---------------------------- | :--------: | :--------------------------------------------------------------- |
| **Verdict Accuracy**          | **100.0%** | 5/5 exact matches (`APPROVED`, `REJECTED`, `NEEDS_HUMAN_REVIEW`) |
| **Hybrid Retrieval Recall@5** | **100.0%** | Dense + BM25 RRF retrieval across domain-filtered SOPs           |
| **Citation Grounding Rate**   | **100.0%** | Zero hallucinated `rule_code` citations                          |
| **Median End-to-End Latency** | **14.4 s** | Full 4-node LangGraph execution + critic verification            |

---

## Tech Stack

| Layer                            | Technologies                                                                          |
| :------------------------------- | :------------------------------------------------------------------------------------ |
| **Agent Orchestration**          | LangGraph, LangChain Core, Pydantic v2                                                |
| **LLM Inference**                | Google Gemini API (Multimodal), Groq API (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`)  |
| **Vector Database & Embeddings** | Qdrant Cloud, FastEmbed ONNX (`paraphrase-multilingual-MiniLM-L12-v2`, `Qdrant/bm25`) |
| **Backend & Security**           | FastAPI, Uvicorn, PyMuPDF, Pillow, SSE-Starlette, SlowAPI                             |
| **Frontend UI**                  | HTML5, Tailwind CSS, Vanilla JS (Split-Pane Inspector + SSE Client)                   |
| **Observability & CI/CD**        | Langfuse Cloud, Pytest, GitHub Actions, Docker (Hugging Face Spaces)                  |

---

## Local Development & Docker Setup

### 1. Run Locally

```bash
git clone https://github.com/4gnim/veriaudit-ai.git
cd veriaudit-ai

# Configure environment variables
cp .env.example .env

# Install dependencies and seed initial SOP rules to Qdrant Cloud
pip install -r requirements.txt
python -m data.presets.seed_policies

# Run test suite
pytest -v

# Start FastAPI server
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000` in your browser.

### 2. Run with Docker

```bash
docker build -t veriaudit-ai .
docker run -p 7860:7860 --env-file .env veriaudit-ai
```

---

## Limitations & Scope

- **Benchmark Dataset Size:** Current automated evaluation covers 5 curated synthetic scenarios; enterprise production deployment requires expanding the golden dataset across multi-page scanned documents and noisy OCR inputs.
- **Knowledge Base Scope:** Default Qdrant collection contains 12 baseline SOP rules across `procurement`, `expense`, and `contract` domains (extensible live via the UI or `POST /api/policies`).
- **Public Demo Quotas:** Hosted demo enforces per-IP rate limiting and a 5 MB file upload cap to preserve free-tier inference API quotas.
