"""Первичная распаковка PDF: текст постранично + картинки.

Складывает:
  scripts/_tmp/raw/<doc>/text.md           — текст с маркерами страниц
  scripts/_tmp/raw/<doc>/img_p{N}_{i}.png  — все изображения по страницам
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import fitz  # PyMuPDF

SRC = Path("/tmp/ai_ceiling_docs/2. Для ИИ")
DST = Path(__file__).resolve().parent / "raw"


def slugify(name: str) -> str:
    base = name.replace("Копия ", "").replace(".pdf", "")
    # Копия 1.1. Виды профилей... → 1_1_vidy_profilej
    parts = base.split(". ", 1)
    num = parts[0].replace(".", "_") if len(parts) == 2 else parts[0]
    return num


def extract_pdf(pdf_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    md_lines: list[str] = [f"# {pdf_path.stem}\n"]
    for page_idx, page in enumerate(doc, start=1):
        md_lines.append(f"\n\n---\n## Page {page_idx}\n")
        text = page.get_text("text").strip()
        md_lines.append(text)

        # Изображения
        images = page.get_images(full=True)
        for img_i, img in enumerate(images, start=1):
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n >= 5:  # CMYK → RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                img_name = f"img_p{page_idx:02d}_{img_i}.png"
                pix.save(out_dir / img_name)
                md_lines.append(f"\n\n[IMG: {img_name}]")
                pix = None
            except Exception as e:
                md_lines.append(f"\n\n[IMG FAILED xref={xref}: {e}]")

    (out_dir / "text.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"  {pdf_path.name} → {out_dir} ({len(doc)} pages, {sum(len(p.get_images(full=True)) for p in doc)} images)")
    doc.close()


def main() -> None:
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True)
    pdfs = sorted(SRC.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs")
    for pdf in pdfs:
        slug = slugify(pdf.name)
        extract_pdf(pdf, DST / slug)


if __name__ == "__main__":
    main()
