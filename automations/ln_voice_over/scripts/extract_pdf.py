"""Extract page images from a PDF and classify them.

Uses opendataloader-pdf to extract all pages as images, then classifies
each page by a size heuristic derived from this PDF's own distribution
(full-bleed illustrations vs. typical text pages vs. blank/sparse pages).

These are hints only — size alone cannot always separate partial-bleed
color illustrations from dense text pages, so the /setup-book skill's
OCR pass remains the ground truth.

Requires: Java 21+, opendataloader-pdf

Usage:
    python extract_pdf.py <slug> [--pdf-path PATH]
"""

import argparse
import json
import sys
from pathlib import Path

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"

# Multipliers applied to the per-PDF median page size. Full-bleed illustrations
# typically weigh ~1.5-3x a typical text page; blank/sparse pages <30%.
COLOR_MULTIPLE = 1.6
SMALL_MULTIPLE = 0.30


def compute_thresholds(sizes: list[float]) -> tuple[float, float]:
    """Return (color_cutoff_kb, small_cutoff_kb) scaled to this PDF's median."""
    s = sorted(sizes)
    median = s[len(s) // 2]
    return median * COLOR_MULTIPLE, median * SMALL_MULTIPLE


def classify_page(size_kb: float, color_cutoff: float, small_cutoff: float) -> str:
    """Classify a page given this PDF's computed cutoffs."""
    if size_kb > color_cutoff:
        return "color_illustration"
    if size_kb < small_cutoff:
        return "small"  # blank, ToC, title, or sparse text — needs review
    return "text"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract page images from a PDF.")
    parser.add_argument("slug", help="Project slug")
    parser.add_argument("--pdf-path", help="Path to PDF (default: auto-detect in source/)")
    args = parser.parse_args()

    project_dir = PROJECTS_DIR / args.slug
    source_dir = project_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    # Find PDF
    if args.pdf_path:
        pdf_path = Path(args.pdf_path)
    else:
        pdfs = sorted(source_dir.glob("*.pdf"))
        if not pdfs:
            print(f"ERROR: No PDF found in {source_dir}", file=sys.stderr)
            sys.exit(1)
        pdf_path = pdfs[0]

    pages_dir = source_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting pages from: {pdf_path.name}", file=sys.stderr)

    from opendataloader_pdf import convert

    convert(
        input_path=str(pdf_path),
        output_dir=str(source_dir / "_tmp_extract"),
        format="json",
        image_output="external",
        image_format="png",
        image_dir=str(pages_dir),
        quiet=True,
    )

    # Read the extraction JSON to get page count
    tmp_dir = source_dir / "_tmp_extract"
    extract_jsons = list(tmp_dir.glob("*.json"))
    if not extract_jsons:
        print("ERROR: opendataloader-pdf produced no output", file=sys.stderr)
        sys.exit(1)

    extract_data = json.loads(extract_jsons[0].read_text(encoding="utf-8"))
    total_pages = extract_data.get("number of pages", 0)

    # First pass: rename images from imageFileN.png to NNN.png and collect sizes.
    pages = []
    for kid in extract_data.get("kids", []):
        page_num = kid["page number"]
        old_name = kid.get("source", "")
        if not old_name:
            continue

        old_path = pages_dir / Path(old_name).name
        new_path = pages_dir / f"{page_num:03d}.png"

        if old_path.exists() and not new_path.exists():
            old_path.rename(new_path)
        elif old_path.exists() and new_path.exists():
            old_path.unlink()

        if new_path.exists():
            size_kb = new_path.stat().st_size / 1024
            pages.append(
                {
                    "page": page_num,
                    "image_path": f"pages/{page_num:03d}.png",
                    "size_kb": round(size_kb, 1),
                }
            )

    # Second pass: compute per-PDF thresholds, then classify.
    color_cutoff_kb, small_cutoff_kb = compute_thresholds([p["size_kb"] for p in pages])
    for p in pages:
        p["classification"] = classify_page(p["size_kb"], color_cutoff_kb, small_cutoff_kb)

    # Clean up temp extraction dir
    for f in tmp_dir.iterdir():
        f.unlink()
    tmp_dir.rmdir()

    # Write pages.json
    result = {
        "source_pdf": pdf_path.name,
        "total_pages": total_pages,
        "color_cutoff_kb": round(color_cutoff_kb, 1),
        "small_cutoff_kb": round(small_cutoff_kb, 1),
        "pages": sorted(pages, key=lambda p: p["page"]),
    }

    output_path = source_dir / "pages.json"
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # Summary
    classifications = {}
    for p in pages:
        c = p["classification"]
        classifications[c] = classifications.get(c, 0) + 1

    summary = {
        "pages_json": str(output_path),
        "total_pages": total_pages,
        "extracted": len(pages),
        "color_cutoff_kb": round(color_cutoff_kb, 1),
        "small_cutoff_kb": round(small_cutoff_kb, 1),
        "classifications": classifications,
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
