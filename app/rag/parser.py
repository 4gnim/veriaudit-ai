import base64
import io
from dataclasses import dataclass
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class ParsedDocument:
    filename: str
    extension: str
    page_count: int
    extracted_text: str
    page_images_b64: list[str]
    is_scanned: bool


def _resize_and_encode_image(pil_img: Image.Image, max_dim: int = 1400) -> str:
    if pil_img.mode not in ("RGB", "L"):
        pil_img = pil_img.convert("RGB")
    elif pil_img.mode == "L":
        pil_img = pil_img.convert("RGB")

    width, height = pil_img.size
    if max(width, height) > max_dim:
        scale = max_dim / float(max(width, height))
        new_size = (int(width * scale), int(height * scale))
        pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    pil_img.save(buffer, format="JPEG", quality=85, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def parse_document(
    file_bytes: bytes, filename: str, max_pages: int = 5
) -> ParsedDocument:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Format file '{ext}' tidak didukung. Gunakan PDF, PNG, JPG, atau WEBP."
        )

    if ext == ".pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_pages = len(doc)
        pages_to_process = min(total_pages, max_pages)

        text_chunks: list[str] = []
        images_b64: list[str] = []

        for page_idx in range(pages_to_process):
            page = doc[page_idx]
            page_text = page.get_text("text").strip()
            if page_text:
                text_chunks.append(f"--- Halaman {page_idx + 1} ---\n{page_text}")

            # Render halaman ke gambar (150 DPI cukup tajam untuk OCR visual)
            pix = page.get_pixmap(dpi=150)
            pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
            images_b64.append(_resize_and_encode_image(pil_img))

        doc.close()
        combined_text = "\n\n".join(text_chunks).strip()
        is_scanned = len(combined_text) < 40

        return ParsedDocument(
            filename=filename,
            extension=ext,
            page_count=total_pages,
            extracted_text=combined_text,
            page_images_b64=images_b64,
            is_scanned=is_scanned,
        )

    # Jika input berupa file gambar langsung
    pil_img = Image.open(io.BytesIO(file_bytes))
    encoded = _resize_and_encode_image(pil_img)

    return ParsedDocument(
        filename=filename,
        extension=ext,
        page_count=1,
        extracted_text="",
        page_images_b64=[encoded],
        is_scanned=True,
    )
