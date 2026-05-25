# LN Voice Over V2

LNVO v2 is the contract-first architecture for turning a light novel volume into
audio-first, visual-supported media.

This package currently contains only the skeleton contracts and validators for
the target pipeline:

```text
prepare -> transform -> dialogue -> scenes -> generation
```

It does not implement OCR, parsing, attribution prompts, TTS, video rendering,
CLI commands, or data-porting tools.

Runtime data is stored outside the repository. Repository files define public
contracts, validation rules, path conventions, and tests.
