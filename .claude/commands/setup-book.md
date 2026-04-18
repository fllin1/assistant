# Setup Book — Download, Extract, and Prepare a Light Novel Volume

Take a light novel PDF (downloaded from AnyFlip or pre-supplied), extract page images, OCR text, classify illustrations, and produce a structured `book.json` ready for `lnvo split`.

**Usage:**
- `/setup-book <anyflip-url> <series>/<volume>` — download from AnyFlip, then process.
- `/setup-book <series>/<volume>` — process a PDF already sitting in `<series>/<volume>/source/`.

Examples:
- `/setup-book https://anyflip.com/cnyjl/fhfw/ classroom-of-the-elite-year-2/v6`
- `/setup-book classroom-of-the-elite-year-2/v10` — when the PDF is already in `source/`

## Instructions

You are setting up a new light novel volume for the voice-over pipeline. This covers the full flow: optionally download the PDF, create the project, extract pages, OCR text, and produce the structured input for the rest of the pipeline.

Parse `$ARGUMENTS`. Detect which form you got:
- If the first token starts with `http://` or `https://`, it's the AnyFlip URL and the second token is the slug.
- Otherwise the only argument is the slug, and the PDF is expected to already be in `<series>/<volume>/source/`.

If you can't tell or the slug is missing, ask the user.

### Step 1: Ensure the PDF is in place and the project exists

Create (or refresh) the project folder structure via `create_project()`. The slug is `<series>/<volume>`:

```
python -c "from automations.ln_voice_over.init_project import create_project; print(create_project('<series>', '<volume>'))"
```

**If you have an AnyFlip URL**, download the PDF from a scratch directory and move it into `source/`:

```
mkdir -p /tmp/lnvo-<volume> && cd /tmp/lnvo-<volume> && ~/go/bin/anyflip-downloader "<anyflip-url>"
mv /tmp/lnvo-<volume>/*.pdf ~/.assistant/ln_voice_over/projects/<series>/<volume>/source/
```

**If you have no URL**, just verify a PDF is already present:

```
ls ~/.assistant/ln_voice_over/projects/<series>/<volume>/source/*.pdf
```

If no PDF is found, stop and tell the user where to drop it (`source/` of the volume) before re-running the skill.

`extract_pdf.py` auto-detects the first `*.pdf` in `source/`, so the filename doesn't matter.

### Step 2: Extract page images from PDF

Run the extraction script:

```
PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH" python automations/ln_voice_over/scripts/extract_pdf.py <series>/<volume>
```

This extracts all page images to `source/pages/` and writes `source/pages.json` with initial classifications (color_illustration, text, small). Capture the JSON output for the summary.

Report to the user: total pages, classification breakdown (color illustrations, text pages, small pages).

### Step 3: Review classifications

Read `source/pages.json` to understand the book structure. This step can run **in parallel with Step 4** — small-page review and OCR don't depend on each other.

Typical light novel structure:
- **Pages 1-6**: Cover + color illustrations (classified as `color_illustration`)
- **Pages 7-12**: Title page, copyright, ToC (classified as `small` or `text`)
- **Pages 13+**: Chapter text and occasional BW illustrations
- **Last few pages**: Afterword, ads, back matter

For pages classified as `small`, read the actual page image to determine if they are:
- **Chapter title pages** (sparse text with chapter name)
- **Blank pages**
- **Table of contents**

The thresholds are per-PDF: `extract_pdf.py` computes `color_cutoff_kb` and `small_cutoff_kb` from this book's own median page size and writes both into `pages.json`. Keep in mind the size heuristic is only a hint — partial-bleed color illustrations on white backgrounds can be smaller than a dense text page, so they'll be classified as `text`. Trust the OCR pass in Step 4 as the ground truth, and use size as a cue for which pages to sample manually. A reasonable manual sample is: any `text` page whose `size_kb` is within ~20% of `color_cutoff_kb` (just below the boundary — often BW or hybrid illustration+text spreads).

### Step 4: OCR text pages

This is the core step. For each text page, read the page image and extract the text.

**Important:** Launch OCR agents with `model: "sonnet"` — Opus is overkill for OCR. Launch agents in parallel, each handling a batch of ~40–60 pages; pick the batch count from the total text-page count (a short volume may want 3 agents, a long one 8+).

Process pages in batches. For each batch:
1. Read the page images (PNG files in `source/pages/NNN.png`)
2. Extract the text faithfully, preserving:
   - Paragraph breaks (double newlines)
   - Dialogue markers (opening/closing quotes)
   - Scene breaks (*** or similar)
   - Italicized text markers if visible
3. Skip watermark text at the bottom of pages (e.g. "Page N Goldenagato | mp4directs.com" — the exact wording varies by source)
4. Note chapter headers (e.g., "Chapter 2: Getting Ready for the Cultural Festival")
5. **Emit valid JSON.** The `text`, `description`, and `caption` fields will contain `"` (dialogue quotes) and `\` — escape them as `\"` and `\\` before writing the batch file. Every dialogue line like `"huh?"` must appear in the JSON as `\"huh?\"`. After writing, parse the file with `json.loads` to confirm it's valid; if parsing fails, fix the escaping and rewrite before returning.

Build up the text chapter by chapter. When you encounter a new chapter header, start a new chapter entry.

### Step 5: Produce book.json

Write the structured JSON to `source/book.json`:

```json
{
  "title": "Book Title",
  "total_pages": 289,
  "book_slug": "<series>/<volume>",
  "front_matter": {
    "illustrations": [
      {"page": 1, "image_path": "pages/001.png", "classification": "cover", "description": "..."},
      {"page": 2, "image_path": "pages/002.png", "classification": "color_illustration", "description": "..."}
    ]
  },
  "chapters": [
    {
      "title": "Chapter Title",
      "start_page": 13,
      "text": "Chapter 1: Chapter Title\n\nFull text of the chapter...",
      "pov_character": null,
      "illustrations": [
        {"page": 54, "image_path": "pages/054.png", "description": "Brief description"}
      ]
    }
  ],
  "back_matter": {
    "afterword": "Full afterword text, or null if absent",
    "illustrations": [
      {"page": 285, "image_path": "pages/285.png", "classification": "back_cover", "description": "..."}
    ]
  }
}
```

**Chapter detection rules:**
- Lines matching `Chapter N:`, `Prologue`, or `Epilogue` start a new chapter.
- Illustrations between two text pages of the same chapter belong to that chapter.
- Illustrations before the first chapter are front matter.
- Afterword, ads, and back-cover pages go into `back_matter`, **not** a trailing chapter. If there's no afterword, set `back_matter.afterword` to `null`.

**Important:** The `text` field should contain the full chapter text with the header as the first line, followed by a blank line, then body text.

### Step 6: Describe every illustration

For **every** illustration — front matter, interior (inside a chapter's `illustrations[]`), and back matter — read the image and write a 1–2 sentence `description`. Include character names where recognizable. Don't leave `description` empty for interior illustrations; that field is required across the board.

### Step 7: Report

Report to the user:
- Total pages processed
- Chapters found (with titles and page ranges)
- Illustrations found (front matter + interior + back matter)
- Path to `book.json`

Remind them to run `lnvo split <series>/<volume>` next — it will auto-detect the `book.json`.
