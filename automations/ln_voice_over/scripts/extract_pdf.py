"""Extract page images from a PDF and classify them.

Uses opendataloader-pdf to extract all pages as images, then classifies
each page by file size heuristic (color illustration, text, etc.).

Requires: Java 21+, opendataloader-pdf

Usage:
    python extract_pdf.py <slug> [--pdf-path PATH]
"""

import argparse
import json
import sys
from pathlib import Path

PROJECTS_DIR = Path.home() / ".assistant" / "ln_voice_over" / "projects"

# File size thresholds for classification (in KB)
COLOR_ILLUSTRATION_THRESHOLD_KB = 2000
SMALL_PAGE_THRESHOLD_KB = 200


def classify_page(size_kb: float) -> str:
    """Classify a page based on its image file size."""
    if size_kb > COLOR_ILLUSTRATION_THRESHOLD_KB:
        return "color_illustration"
    if size_kb < SMALL_PAGE_THRESHOLD_KB:
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

    # Rename images from imageFileN.png to NNN.png and classify
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
                    "classification": classify_page(size_kb),
                }
            )

    # Clean up temp extraction dir
    for f in tmp_dir.iterdir():
        f.unlink()
    tmp_dir.rmdir()

    # Write pages.json
    result = {
        "source_pdf": pdf_path.name,
        "total_pages": total_pages,
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
        "classifications": classifications,
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
