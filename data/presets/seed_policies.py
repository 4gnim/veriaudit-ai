from app.rag.hybrid_store import get_policy_store

DEFAULT_POLICIES = [
    # Domain 1: Procurement & Vendor Invoice
    {
        "rule_code": "PROC-001",
        "category": "procurement",
        "section": "Batas Otorisasi Pembelian Tanpa PO",
        "content": "Pembelian barang atau jasa dengan total nilai di atas Rp 5.000.000 wajib melampirkan nomor Purchase Order (PO) resmi dan tanda tangan atau stempel otorisasi manajer departemen.",
    },
    {
        "rule_code": "PROC-002",
        "category": "procurement",
        "section": "Validasi Perhitungan Pajak PPN",
        "content": "Untuk vendor berstatus Pengusaha Kena Pajak (PKP), tarif PPN harus sesuai ketentuan berlaku sebesar 11% dari subtotal sebelum pajak. Selisih pembulatan maksimal yang ditoleransi adalah Rp 500.",
    },
    {
        "rule_code": "PROC-003",
        "category": "procurement",
        "section": "Kelengkapan Identitas Invoice Vendor",
        "content": "Setiap invoice vendor wajib mencantumkan nomor invoice unik, tanggal penerbitan dokumen, nama badan usaha vendor, serta rincian item barang atau jasa yang ditagihkan.",
    },
    {
        "rule_code": "PROC-004",
        "category": "procurement",
        "section": "Larangan Pemecahan Transaksi (Split Billing)",
        "content": "Dilarang memecah satu paket pengadaan menjadi beberapa invoice pada tanggal yang sama dari vendor yang sama untuk menghindari batas persetujuan Rp 5.000.000.",
    },
    # Domain 2: Employee Expense Reimbursement
    {
        "rule_code": "EXP-001",
        "category": "expense",
        "section": "Batas Plafon Klaim Makan Dinas",
        "content": "Klaim konsumsi perjalanan dinas luar kota maksimal Rp 150.000 per hari per karyawan. Item minuman beralkohol atau rokok tidak dapat diklaim dan wajib ditolak.",
    },
    {
        "rule_code": "EXP-002",
        "category": "expense",
        "section": "Batas Waktu Pengajuan Reimbursement",
        "content": "Struk atau kuitansi reimbursement wajib diajukan maksimal 14 hari kalender sejak tanggal transaksi yang tertera pada bukti pembayaran.",
    },
    {
        "rule_code": "EXP-003",
        "category": "expense",
        "section": "Bukti Pembayaran Transportasi & Akomodasi",
        "content": "Klaim transportasi online, tiket kereta, atau hotel wajib menampilkan nama penyedia layanan, tanggal perjalanan, dan nominal lunas yang terbaca jelas tanpa coretan manual.",
    },
    {
        "rule_code": "EXP-004",
        "category": "expense",
        "section": "Klaim Perangkat Lunak & Langganan SaaS",
        "content": "Pembelian lisensi perangkat lunak atau langganan cloud menggunakan kartu pribadi di atas USD 50 atau Rp 750.000 wajib memiliki persetujuan tertulis dari divisi IT Security.",
    },
    # Domain 3: Vendor Contract & SLA Compliance
    {
        "rule_code": "CTR-001",
        "category": "contract",
        "section": "Termin Pembayaran Standar Vendor",
        "content": "Termin pembayaran standar perusahaan adalah Net 30 hari kalender setelah invoice diterima lengkap. Termin pembayaran di muka (DP) di atas 30% memerlukan jaminan bank atau persetujuan Direktur Keuangan.",
    },
    {
        "rule_code": "CTR-002",
        "category": "contract",
        "section": "Klausul Denda Keterlambatan (SLA Penalty)",
        "content": "Kontrak pengadaan jasa IT atau konstruksi bernilai di atas Rp 25.000.000 wajib mencantumkan klausul denda keterlambatan minimal 0,1% per hari keterlambatan.",
    },
    {
        "rule_code": "CTR-003",
        "category": "contract",
        "section": "Kerahasiaan Data & NDA",
        "content": "Setiap kontrak dengan pihak ketiga yang mengakses data pelanggan atau sistem internal wajib menyertakan klausul Non-Disclosure Agreement (NDA) dan larangan transfer data ke luar wilayah hukum Indonesia.",
    },
    {
        "rule_code": "CTR-004",
        "category": "contract",
        "section": "Keabsahan Tanda Tangan Para Pihak",
        "content": "Dokumen kontrak dianggap sah untuk dieksekusi hanya jika memuat tanda tangan pejabat berwenang dari kedua belah pihak beserta tanggal penandatanganan.",
    },
]


def seed_default_policies() -> int:
    store = get_policy_store()
    return store.upsert_policies(DEFAULT_POLICIES)


if __name__ == "__main__":
    total = seed_default_policies()
    print(f"Berhasil mengindeks {total} aturan SOP ke Qdrant Cloud!")

    store = get_policy_store()
    sample_query = "Invoice pembelian server senilai Rp 12.500.000 tanpa tanda tangan manajer dan PPN 11%"
    hits = store.hybrid_search(sample_query, top_k=3)
    print("\nHasil Hybrid Search (Dense + BM25 RRF):")
    for h in hits:
        print(
            f"- [{h.rule_code}] (score={h.relevance_score}) {h.section}: {h.content[:80]}..."
        )
