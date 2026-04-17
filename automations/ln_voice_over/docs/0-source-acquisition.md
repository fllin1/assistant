# Stage 0: Source Acquisition

The `/setup-book` Claude skill handles the full source-acquisition flow: download an AnyFlip book as a PDF, extract page images, OCR the text, classify illustrations, and produce `source/book.json` ready for `lnvo split`.

This doc covers the one-time prerequisite installs. Once those are in place, usage is just:

```
/setup-book <anyflip-url> <book-slug>
```

See `.claude/commands/setup-book.md` for the skill's step-by-step logic.

## Prerequisites

### 1. anyflip-downloader (Go binary)

[anyflip-downloader](https://github.com/Lofter1/anyflip-downloader) handles Cloudflare protection and produces a PDF directly. Install via Go:

```bash
brew install go  # if needed
go install github.com/Lofter1/anyflip-downloader@latest
```

The binary lands in `~/go/bin/anyflip-downloader`. Add `~/go/bin` to your PATH if not already:

```bash
export PATH="$HOME/go/bin:$PATH"
```

### 2. Java 21 (required by opendataloader-pdf)

```bash
brew install openjdk@21
echo 'export PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

The skill prepends this PATH itself when invoking `extract_pdf.py`, so the export is only needed if you want to run the script manually.

### 3. opendataloader-pdf (Python)

```bash
uv pip install opendataloader-pdf
```

## Browser fallback

If `anyflip-downloader` fails (some books have download protection), fall back to the browser:

1. Open the book in your browser: e.g. `https://anyflip.com/cnyjl/qwpk/`
2. Use the browser's Print dialog (Cmd+P on Mac)
3. Select "Save as PDF"
4. Save to `~/.assistant/ln_voice_over/projects/<book-slug>/source/volume.pdf`

Then skip Step 1 of `/setup-book` and start from Step 2 (the skill auto-detects any `*.pdf` in `source/`).

## What you get

After `/setup-book` finishes, the project's `source/` directory contains:

- `<title>.pdf` — the downloaded PDF
- `pages/NNN.png` — one image per page
- `pages.json` — per-page classification (text / color_illustration / small)
- `book.json` — the structured output: chapters with OCR'd text, front-matter illustrations, per-chapter illustrations, back-matter

`lnvo split <slug>` picks up `book.json` automatically — no further configuration.

## What's next

```
SPLIT → CLEAN → PARSE → EXTRACT → RESOLVE → REVIEW → SYNTHESIZE
```

See the main [README](../README.md) for each downstream stage.
