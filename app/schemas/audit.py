from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class LineItem(BaseModel):
    description: str = Field(..., description="Nama barang atau jasa pada dokumen")
    quantity: float = Field(default=1.0, description="Jumlah unit")
    unit_price: float = Field(default=0.0, description="Harga satuan")
    total_price: float = Field(default=0.0, description="Total harga item")

    @field_validator("quantity", mode="before")
    @classmethod
    def default_quantity(cls, v):
        return 1.0 if v is None else v

    @field_validator("unit_price", "total_price", mode="before")
    @classmethod
    def default_price(cls, v):
        return 0.0 if v is None else v


class ExtractedDocumentData(BaseModel):
    document_type: Literal[
        "invoice", "receipt", "contract", "expense_claim", "other"
    ] = Field(..., description="Kategori dokumen yang terdeteksi")
    document_number: Optional[str] = Field(
        default=None, description="Nomor invoice, kontrak, atau referensi dokumen"
    )
    vendor_or_party: Optional[str] = Field(
        default=None, description="Nama vendor, merchant, atau pihak terkait"
    )
    document_date: Optional[str] = Field(
        default=None, description="Tanggal dokumen (format YYYY-MM-DD jika tersedia)"
    )
    currency: str = Field(default="IDR", description="Kode mata uang (IDR, USD, dll.)")
    subtotal: float = Field(default=0.0, description="Subtotal sebelum pajak")
    tax_amount: float = Field(default=0.0, description="Nominal pajak (PPN/PPh)")
    total_amount: float = Field(default=0.0, description="Total nilai akhir dokumen")
    has_signature_or_stamp: bool = Field(
        default=False,
        description="Apakah terlihat tanda tangan, stempel, atau otorisasi visual",
    )
    line_items: list[LineItem] = Field(default_factory=list)
    key_terms_or_notes: list[str] = Field(
        default_factory=list,
        description="Klausul penting, syarat pembayaran, atau catatan khusus",
    )
    extraction_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Tingkat keyakinan ekstraksi antara 0.0 sampai 1.0",
    )

    @field_validator("subtotal", "tax_amount", "total_amount", mode="before")
    @classmethod
    def default_amounts(cls, v):
        return 0.0 if v is None else v


class PolicyCitation(BaseModel):
    rule_code: str = Field(..., description="Kode aturan SOP, misal FIN-001")
    category: str = Field(..., description="Domain kebijakan")
    section: str = Field(..., description="Judul pasal atau bagian")
    content: str = Field(..., description="Isi aturan SOP yang relevan")
    relevance_score: float = Field(..., description="Skor relevansi RRF dari Qdrant")


class AuditFinding(BaseModel):
    rule_code: str = Field(..., description="Kode aturan yang diperiksa")
    status: Literal["COMPLIANT", "VIOLATION", "WARNING", "INSUFFICIENT_DATA"] = Field(
        ..., description="Status kepatuhan terhadap aturan tersebut"
    )
    reason: str = Field(
        ..., description="Penjelasan berbasis bukti dari dokumen dan aturan SOP"
    )


class FinalAuditVerdict(BaseModel):
    overall_status: Literal["APPROVED", "REJECTED", "NEEDS_HUMAN_REVIEW"] = Field(
        ..., description="Keputusan akhir hasil audit"
    )
    risk_score: int = Field(
        ..., ge=0, le=100, description="Skor risiko 0 (aman) hingga 100 (kritis)"
    )
    summary: str = Field(..., description="Ringkasan eksekutif hasil audit")
    findings: list[AuditFinding] = Field(default_factory=list)
    critic_notes: str = Field(
        default="", description="Catatan verifikasi silang dari Critic Node"
    )
