import fitz  # PyMuPDF

PRESET_CATALOG = [
    {
        "id": "invoice_violation",
        "title": "Invoice Pengadaan Server (Pelanggaran SOP)",
        "badge": "High Risk • Procurement",
        "domain": "procurement",
        "filename": "INV-2026-0891_PT_Nusantara_Tech.pdf",
        "description": "Tagihan Rp 13,2 juta tanpa nomor PO, tanpa tanda tangan manajer, PPN 10% (seharusnya 11%), dan DP 50%.",
    },
    {
        "id": "expense_compliant",
        "title": "Klaim Makan & Transportasi Dinas (Valid)",
        "badge": "Compliant • Expense",
        "domain": "expense",
        "filename": "EXP-2026-1104_Klaim_Dinas_Bandung.pdf",
        "description": "Klaim konsumsi Rp 125.000 (di bawah plafon Rp 150.000) dan tiket kereta Rp 110.000 yang diajukan H+3.",
    },
    {
        "id": "contract_sla_risk",
        "title": "Draft Kontrak Jasa IT Rp 60 Juta (Tanpa NDA)",
        "badge": "Violation • Contract",
        "domain": "contract",
        "filename": "CTR-2026-042_Kontrak_Cloud_ERP.pdf",
        "description": "Kontrak akses database internal senilai Rp 60 juta tanpa klausul NDA dan tanpa denda keterlambatan SLA.",
    },
]


def _render_pdf_from_lines(header: str, subheader: str, lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Header banner
    page.draw_rect(
        fitz.Rect(40, 40, 555, 105), color=(0.15, 0.23, 0.38), fill=(0.95, 0.97, 1.0)
    )
    page.insert_text(
        (55, 68), header, fontsize=14, fontname="helv", color=(0.1, 0.15, 0.25)
    )
    page.insert_text(
        (55, 88), subheader, fontsize=10, fontname="helv", color=(0.35, 0.42, 0.55)
    )

    y = 135
    for line in lines:
        if line == "---":
            page.draw_line(
                fitz.Point(45, y), fitz.Point(550, y), color=(0.8, 0.84, 0.9)
            )
            y += 18
        else:
            page.insert_text(
                (50, y), line, fontsize=10.5, fontname="helv", color=(0.12, 0.14, 0.18)
            )
            y += 20

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def generate_preset_pdf(preset_id: str) -> tuple[bytes, str, str]:
    """Mengembalikan (pdf_bytes, filename, domain)."""
    if preset_id == "invoice_violation":
        pdf = _render_pdf_from_lines(
            "PT NUSANTARA TECH SOLUTIONS (STATUS: PKP)",
            "INVOICE TAGIHAN PENGADAAN INFRASTRUKTUR IT",
            [
                "Nomor Invoice    : INV-2026-0891",
                "Tanggal Terbit   : 15 November 2026",
                "Nomor PO         : [TIDAK TERLAMPIR / TANPA PO]",
                "Termin Pembayaran: Uang Muka (DP) 50% dibayar di muka",
                "---",
                "RINCIAN BARANG / JASA:",
                "1. Server Rack & Managed Switch (1 Paket)         Rp 12.000.000",
                "---",
                "Subtotal                                          Rp 12.000.000",
                "PPN (10%)                                         Rp  1.200.000",
                "TOTAL TAGIHAN                                     Rp 13.200.000",
                "---",
                "Otorisasi Vendor : Ditandatangani Sales Admin",
                "Otorisasi Internal: [BELUM ADA TANDA TANGAN / STEMPEL MANAJER]",
            ],
        )
        return pdf, "INV-2026-0891_PT_Nusantara_Tech.pdf", "procurement"

    if preset_id == "expense_compliant":
        pdf = _render_pdf_from_lines(
            "FORMULIR KLAIM REIMBURSEMENT PERJALANAN DINAS",
            "DIVISI PRODUCT & ENGINEERING • KARYAWAN: AGNI M.",
            [
                "Nomor Klaim      : EXP-2026-1104",
                "Tanggal Transaksi: 14 November 2026",
                "Tanggal Pengajuan: 17 November 2026 (H+3 setelah transaksi)",
                "Tujuan Dinas     : Audit Sistem di Kantor Cabang Bandung",
                "---",
                "RINCIAN BUKTI PEMBAYARAN TERLAMPIR:",
                "1. Tiket Kereta Api Argo Parahyangan (Lunas)      Rp 110.000",
                "2. Makan Siang Dinas - RM Sederhana (Non-Alkohol) Rp 125.000",
                "---",
                "Subtotal                                          Rp 235.000",
                "Pajak (Termasuk dalam struk)                      Rp       0",
                "TOTAL KLAIM REIMBURSEMENT                         Rp 235.000",
                "---",
                "Status Bukti     : Struk asli terbaca jelas tanpa coretan",
                "Otorisasi        : Disetujui & Distempel Supervisor Lapangan",
            ],
        )
        return pdf, "EXP-2026-1104_Klaim_Dinas_Bandung.pdf", "expense"

    if preset_id == "contract_sla_risk":
        pdf = _render_pdf_from_lines(
            "PERJANJIAN KERJA SAMA PENGEMBANGAN & INTEGRASI CLOUD ERP",
            "DRAFT KONTRAK VENDOR PIHAK KETIGA",
            [
                "Nomor Kontrak    : CTR-2026-042",
                "Tanggal Dokumen  : 16 November 2026",
                "Pihak Pertama    : PT Maju Bersama Indonesia",
                "Pihak Kedua      : CV Solusi Digital Nusantara",
                "---",
                "POKOK KLAUSUL PERJANJIAN:",
                "1. Nilai Kontrak : Rp 60.000.000 (Net 30 hari setelah BAST)",
                "2. Ruang Lingkup : Pihak Kedua diberikan akses penuh ke database",
                "                   pelanggan internal untuk migrasi sistem.",
                "3. Kerahasiaan   : [KLAUSUL NDA & BATAS TRANSFER DATA TIDAK TERCANTUM]",
                "4. Sanksi / SLA  : [KLAUSUL DENDA KETERLAMBATAN TIDAK DIATUR]",
                "---",
                "Total Nilai Kontrak                               Rp 60.000.000",
                "Status Tanda Tangan: Baru ditandatangani Pihak Kedua (Pihak Pertama kosong)",
            ],
        )
        return pdf, "CTR-2026-042_Kontrak_Cloud_ERP.pdf", "contract"

    raise ValueError(f"Preset '{preset_id}' tidak ditemukan.")
