# Stage 0: Source Acquisition

Before the pipeline can run, you need the light novel as a PDF. This document covers how to obtain it and extract text + illustrations using `opendataloader-pdf`.

## Overview

```
AnyFlip book → PDF (via anyflip-downloader) → /setup-book skill → source/book.json + illustrations/
```

This replaces the old manual copy-paste workflow. The PDF is the single source of truth for both text and illustrations.

## Step 1: Install anyflip-downloader

The Go-based [anyflip-downloader](https://github.com/Lofter1/anyflip-downloader) handles Cloudflare protection and produces a PDF directly.

```bash
# Install Go if needed
brew install go

# Install the downloader
go install github.com/Lofter1/anyflip-downloader@latest
```

The binary lands in `~/go/bin/anyflip-downloader`. Add `~/go/bin` to your PATH if not already:

```bash
export PATH="$HOME/go/bin:$PATH"
```

## Step 2: Download the PDF

```bash
# Create the project first (if not already done) — bare `lnvo` opens the guided menu
lnvo

# Download — pass the anyflip book URL
anyflip-downloader "https://anyflip.com/cnyjl/qwpk"
```

This produces a PDF file in the current directory. Move it into the project:

```bash
mv *.pdf ~/.assistant/ln_voice_over/projects/<book-slug>/source/volume.pdf
```

### Troubleshooting

- **Rate limited?** The downloader fetches pages sequentially. If it stalls, try again after a minute.
- **No PDF output?** Some books have download protection. Try the browser fallback below.

### Fallback: Browser print-to-PDF

If the Go downloader doesn't work:

1. Open the book in your browser: `https://anyflip.com/cnyjl/qwpk/`
2. Use the browser's Print dialog (Cmd+P on Mac)
3. Select "Save as PDF"
4. Save to `~/.assistant/ln_voice_over/projects/<book-slug>/source/volume.pdf`

## Step 3: Install extraction dependencies

```bash
# Java 21 (required by opendataloader-pdf)
brew install openjdk@21
echo 'export PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# opendataloader-pdf
uv pip install opendataloader-pdf
```

## Step 4: Extract text and illustrations

> **Note:** This step will be automated by the `/download-book` skill (not yet implemented). For now, the PoC script handles it.

Run the extraction script:

```bash
python automations/ln_voice_over/data/poc_extract.py
```

This produces:
- `source/book.json` — structured book with chapters and illustration metadata
- `source/pages/` — extracted page images (cache)

The output is compatible with the existing pipeline — run `lnvo split` next.

## Reference: AnyFlip URL patterns

| Book | AnyFlip URL |
|------|-------------|
| COTE Y2V7 | `https://anyflip.com/cnyjl/qwpk` |

Add rows as you process more volumes.

## What's next

Once you have the PDF in `source/`, the rest of the pipeline runs as documented in the [README](../README.md):

```
SPLIT → CLEAN → PARSE → EXTRACT → RESOLVE → REVIEW → SYNTHESIZE
```
