# Setup Book — Download, Extract, and Prepare a Light Novel Volume

Download a light novel PDF from AnyFlip, extract page images, OCR text, classify illustrations, and produce a structured `book.json` ready for `lnvo split`.

**Usage:** `/setup-book <anyflip-url> [book-slug]`

Example: `/setup-book https://anyflip.com/cnyjl/fhfw/ classroom-of-the-elite-year-2-v6`

## Instructions

You are setting up a new light novel volume for the voice-over pipeline. This covers the full flow: download the PDF, create the project, extract pages, OCR text, and produce the structured input for the rest of the pipeline.

Parse `$ARGUMENTS`: the first argument is the AnyFlip URL. The optional second argument is the book slug. If no slug is given, ask the user what slug to use.

### Step 1: Download the PDF

The user needs to download the PDF using `anyflip-downloader` (a Go tool). Tell them to run:

```
~/go/bin/anyflip-downloader "<anyflip-url>"
```

This produces a PDF in the current directory. Ask the user to confirm the PDF path once downloaded.

If the project doesn't exist yet, create it:

```
python -m automations.ln_voice_over.cli init
```

Then ensure the `downloads/` directory exists and the PDF is placed there:

```
mkdir -p ~/.assistant/ln_voice_over/projects/<slug>/downloads
mv "<pdf-path>" ~/.assistant/ln_voice_over/projects/<slug>/downloads/
```

### Step 2: Extract page images from PDF

Run the extraction script:

```
PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH" python automations/ln_voice_over/scripts/extract_pdf.py <slug>
```

This extracts all page images to `downloads/pages/` and writes `downloads/pages.json` with initial classifications (color_illustration, text, small). Capture the JSON output for the summary.

Report to the user: total pages, classification breakdown (color illustrations, text pages, small pages).

### Step 3: Review classifications

Read `downloads/pages.json` to understand the book structure.

Typical light novel structure:
- **Pages 1-6**: Cover + color illustrations (classified as `color_illustration`)
- **Pages 7-12**: Title page, copyright, ToC (classified as `small` or `text`)
- **Pages 13+**: Chapter text and occasional BW illustrations
- **Last few pages**: Afterword, ads, back matter

For pages classified as `small`, read the actual page image to determine if they are:
- **Chapter title pages** (sparse text with chapter name)
- **Blank pages**
- **Table of contents**

For any `text` pages with unusually high file size (>1.5MB), check if they might be BW illustrations.

### Step 4: OCR text pages

This is the core step. For each text page, read the page image and extract the text.

**Important:** Launch OCR agents with `model: "sonnet"` — Opus is overkill for OCR. Split the pages into ~5 parallel agents, each handling ~50 pages.

Process pages in batches. For each batch:
1. Read the page images (PNG files in `downloads/pages/NNN.png`)
2. Extract the text faithfully, preserving:
   - Paragraph breaks (double newlines)
   - Dialogue markers (opening/closing quotes)
   - Scene breaks (*** or similar)
   - Italicized text markers if visible
3. Skip watermark text at the bottom of pages (e.g., "Page N Goldenagato | mp4directs.com")
4. Note chapter headers (e.g., "Chapter 2: Getting Ready for the Cultural Festival")

Build up the text chapter by chapter. When you encounter a new chapter header, start a new chapter entry.

### Step 5: Produce book.json

Write the structured JSON to `downloads/book.json`:

```json
{
  "title": "Book Title",
  "total_pages": 289,
  "book_slug": "<slug>",
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
  "front_matter": {
    "illustrations": [
      {"page": 1, "image_path": "pages/001.png", "classification": "cover"},
      {"page": 2, "image_path": "pages/002.png", "classification": "color_illustration", "description": "..."}
    ]
  }
}
```

**Chapter detection rules:**
- Lines matching `Chapter N:` or `Prologue` or `Epilogue` or `Afterword` start a new chapter
- Illustrations between two text pages of the same chapter belong to that chapter
- Illustrations before the first chapter are front matter

**Important:** The `text` field should contain the full chapter text with the header as the first line, followed by a blank line, then body text.

### Step 6: Describe front matter illustrations

For each color illustration in the front matter, read the image and write a brief description (1-2 sentences). Include character names if recognizable.

### Step 7: Report

Report to the user:
- Total pages processed
- Chapters found (with titles and page ranges)
- Illustrations found (front matter + interior)
- Path to `book.json`

Remind them to run `lnvo split <slug>` next — it will auto-detect the `book.json`.
