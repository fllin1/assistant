"""Fast dialogue attribution using Gemini Flash Lite via OpenRouter.

Windowed approach: sends ~25 segments per API call with rolling context
from previous windows. Uses the OpenAI-compatible API at OpenRouter.

Replaces the per-dialogue Ollama extraction pipeline with ~55 API calls
instead of 578 for a typical chapter.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import openai

from .config import PROJECTS_DIR
from .models import Chapter, SegmentType
from .serialization import load_chapter

logger = logging.getLogger(__name__)

MODEL = "google/gemini-3.1-flash-lite-preview"
DEFAULT_WINDOW_SIZE = 25
DEFAULT_OVERLAP = 8

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _load_schema(name: str) -> dict:
    return json.loads((_PROMPTS_DIR / name).read_text(encoding="utf-8"))


_TYPE_CODES = {
    SegmentType.NARRATION: "N",
    SegmentType.DIALOGUE: "D",
    SegmentType.CHAPTER_HEADER: "H",
    SegmentType.SCENE_BREAK: "S",
    SegmentType.INNER_THOUGHT: "T",
}


def _get_client() -> openai.OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY environment variable is not set")
    return openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def detect_pov(client: openai.OpenAI, chapter_text: str) -> dict:
    """Detect the POV character(s) of a chapter using Gemini Flash Lite.

    Args:
        client: OpenAI-compatible client pointed at OpenRouter.
        chapter_text: Full cleaned chapter text.

    Returns:
        Dict with "pov_character" (str) and "pov_ranges" (list | None).
    """
    system_prompt = _load_prompt("pov_detection.txt")
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": chapter_text},
        ],
        response_format=_load_schema("pov_detection_schema.json"),
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


def _build_window_prompt(
    segments: list[tuple[int, str, str]],
    pov_character: str,
    previous_attributions: dict[str, str] | None,
) -> str:
    """Build the user prompt for a single window.

    Args:
        segments: List of (index, type_code, truncated_text) tuples.
        pov_character: Name of the narrator / "I" character.
        previous_attributions: Compact {index: speaker} from overlap of
            the prior window, or None for the first window.
    """
    lines = [f'POV (narrator, "I"): {pov_character}']

    if previous_attributions:
        lines.append(f"Previous: {json.dumps(previous_attributions)}")

    lines.append("")
    for idx, code, text in segments:
        lines.append(f"[{idx}] {code}: {text}")

    lines.append("")
    lines.append("Attribute each dialogue.")
    return "\n".join(lines)


def _call_flash(client: openai.OpenAI, user_prompt: str) -> dict[str, str]:
    """Make a single API call with structured output and return {index: speaker}."""
    system_prompt = _load_prompt("attribution_flash_system.txt")
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=_load_schema("attribution_flash_schema.json"),
        temperature=0,
    )
    data = json.loads(response.choices[0].message.content)
    return {item["index"]: item["speaker"] for item in data["attributions"]}


def _get_pov_for_line(
    line_start: int,
    pov_character: str,
    pov_ranges: list[dict] | None,
) -> str:
    """Resolve the POV character for a given line, handling mid-chapter shifts."""
    if not pov_ranges:
        return pov_character
    for r in pov_ranges:
        start = r["start_line"]
        end = r.get("end_line")
        if line_start >= start and (end is None or line_start <= end):
            return r["pov"]
    return pov_character


def attribute_chapter(
    chapter: Chapter,
    pov_character: str,
    window_size: int = DEFAULT_WINDOW_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    pov_ranges: list[dict] | None = None,
) -> tuple[dict[str, str], dict[str, list]]:
    """Attribute all dialogues in a chapter using windowed Flash calls.

    Args:
        chapter: Parsed chapter with segments.
        pov_character: Default POV character name.
        window_size: Number of segments per window.
        overlap: Number of segments shared between consecutive windows.
        pov_ranges: Optional list of POV range dicts for mid-chapter shifts.

    Returns:
        (merged_attributions, conflicts) where:
        - merged_attributions: {segment_index_str: speaker_name}
        - conflicts: {segment_index_str: [window_n_speaker, window_n+1_speaker]}
    """
    client = _get_client()
    segments = chapter.segments
    stride = window_size - overlap

    # Prepare segment data: (index, type_code, truncated_text)
    seg_data = []
    for seg in segments:
        code = _TYPE_CODES.get(seg.segment_type, "N")
        text = seg.text[:200]
        seg_data.append((seg.index, code, text, seg.line_start))

    total = len(seg_data)
    num_windows = max(1, (total - overlap + stride - 1) // stride)

    merged: dict[str, str] = {}
    conflicts: dict[str, list] = {}
    previous_attributions: dict[str, str] | None = None

    for win_idx in range(num_windows):
        start = win_idx * stride
        end = min(start + window_size, total)
        window = seg_data[start:end]

        # Determine POV for this window (use first segment's line)
        win_pov = _get_pov_for_line(window[0][3], pov_character, pov_ranges)

        # Build prompt with (index, code, text) — drop line_start
        prompt_segments = [(idx, code, text) for idx, code, text, _ in window]
        prompt = _build_window_prompt(prompt_segments, win_pov, previous_attributions)

        logger.info(
            "Window %d/%d: segments [%d..%d]",
            win_idx + 1,
            num_windows,
            window[0][0],
            window[-1][0],
        )

        result = _call_flash(client, prompt)

        # Replace "I" with POV character name
        for k, v in result.items():
            if v == "I":
                # Determine POV for this specific segment
                seg_line = None
                for idx, _, _, ls in window:
                    if str(idx) == k:
                        seg_line = ls
                        break
                seg_pov = (
                    _get_pov_for_line(seg_line, pov_character, pov_ranges)
                    if seg_line is not None
                    else win_pov
                )
                result[k] = seg_pov

        # Merge results, detecting conflicts in overlap zone
        for k, v in result.items():
            if k in merged and merged[k] != v:
                conflicts[k] = [merged[k], v]
                logger.warning(
                    "Conflict at segment %s: %s vs %s (using later)",
                    k,
                    merged[k],
                    v,
                )
            merged[k] = v  # later window wins

        # Build previous_attributions for next window from overlap zone
        if overlap > 0:
            overlap_start = end - overlap
            overlap_indices = {str(seg_data[i][0]) for i in range(max(overlap_start, start), end)}
            previous_attributions = {k: v for k, v in merged.items() if k in overlap_indices}
        else:
            previous_attributions = None

    return merged, conflicts


def resolve_conflicts(
    chapter: Chapter,
    conflicts: dict[str, list],
    attributions: dict[str, str],
    pov_character: str,
    context_size: int = 8,
    pov_ranges: list[dict] | None = None,
) -> dict[str, str]:
    """Second pass: re-attribute conflicted dialogues with focused context.

    For each conflict, extracts ±context_size segments around the dialogue
    and makes a single API call to determine the correct speaker.

    Args:
        chapter: Parsed chapter with segments.
        conflicts: {segment_index_str: [speaker_a, speaker_b]} from first pass.
        attributions: Merged attributions from first pass (will be updated).
        pov_character: Default POV character name.
        context_size: Segments before/after the conflicted dialogue.
        pov_ranges: Optional POV ranges for mid-chapter shifts.

    Returns:
        Updated attributions dict with conflicts resolved.
    """
    if not conflicts:
        return attributions

    client = _get_client()
    segments = chapter.segments
    seg_by_index: dict[int, int] = {seg.index: pos for pos, seg in enumerate(segments)}

    logger.info("Resolving %d conflicts...", len(conflicts))

    for conflict_idx_str, candidates in conflicts.items():
        conflict_idx = int(conflict_idx_str)
        pos = seg_by_index.get(conflict_idx)
        if pos is None:
            continue

        # Build a focused window: ±context_size around the conflict
        start = max(0, pos - context_size)
        end = min(len(segments), pos + context_size + 1)
        window_segs = segments[start:end]

        # Determine POV from the conflicted segment's line
        win_pov = _get_pov_for_line(segments[pos].line_start, pov_character, pov_ranges)

        # Include surrounding attributions as context (excluding the conflict)
        surrounding = {}
        for seg in window_segs:
            k = str(seg.index)
            if k != conflict_idx_str and k in attributions:
                surrounding[k] = attributions[k]

        prompt_segments = [
            (seg.index, _TYPE_CODES.get(seg.segment_type, "N"), seg.text[:200])
            for seg in window_segs
        ]
        prompt = _build_window_prompt(prompt_segments, win_pov, surrounding or None)

        result = _call_flash(client, prompt)

        resolved = result.get(conflict_idx_str)
        if resolved:
            if resolved == "I":
                resolved = _get_pov_for_line(segments[pos].line_start, pov_character, pov_ranges)
            logger.info(
                "Conflict %s resolved: %s → %s",
                conflict_idx_str,
                candidates,
                resolved,
            )
            attributions[conflict_idx_str] = resolved

    return attributions


def attribute_chapter_cli(
    book_slug: str,
    chapter_num: int,
    window_size: int = DEFAULT_WINDOW_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    pov_override: str | None = None,
    resolve_only: bool = False,
) -> None:
    """CLI entry point: attribute a single chapter and save results.

    Loads the chapter from parsed/, resolves POV from manifest or detection,
    runs windowed attribution, and saves results to attributed_flash/.

    When resolve_only=True, skips the first pass and loads existing
    attributions + conflicts from attributed_flash/ to run only the
    conflict resolution pass.
    """
    root = PROJECTS_DIR / book_slug
    parsed_path = root / "parsed" / f"chapter_{chapter_num:02d}.json"
    manifest_path = root / "chapters" / "manifest.json"
    output_dir = root / "attributed_flash"
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / f"chapter_{chapter_num:02d}.json"
    conflicts_path = output_dir / f"chapter_{chapter_num:02d}_conflicts.json"

    if not parsed_path.exists():
        raise FileNotFoundError(f"Parsed chapter not found: {parsed_path}")

    chapter = load_chapter(parsed_path)

    # Resolve POV character
    pov_character = pov_override
    pov_ranges = None

    if not pov_character and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest:
            if entry["number"] == chapter_num:
                pov_character = entry.get("pov_character")
                pov_ranges = entry.get("pov_ranges")
                break

    if not pov_character:
        # POV not in manifest — detect it
        logger.info("No POV character set, running detection...")
        client = _get_client()
        cleaned_path = root / "cleaned" / f"chapter_{chapter_num:02d}.txt"
        if not cleaned_path.exists():
            raise FileNotFoundError(f"Cleaned chapter not found for POV detection: {cleaned_path}")
        chapter_text = cleaned_path.read_text(encoding="utf-8")
        pov_result = detect_pov(client, chapter_text)
        pov_character = pov_result.get("pov_character")
        pov_ranges = pov_result.get("pov_ranges")
        logger.info("Detected POV: %s", pov_character)

        if not pov_character:
            raise RuntimeError("Could not detect POV character")

        # Update manifest with detected POV
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest:
                if entry["number"] == chapter_num:
                    entry["pov_character"] = pov_character
                    if pov_ranges:
                        entry["pov_ranges"] = pov_ranges
                    break
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            logger.info("Updated manifest with detected POV")

    if resolve_only:
        # Load existing results and resolve conflicts only
        if not out_path.exists():
            raise FileNotFoundError(
                f"No existing attributions at {out_path}. Run without --resolve-only first."
            )
        if not conflicts_path.exists():
            logger.info("No conflicts file found — nothing to resolve.")
            return

        attributions = json.loads(out_path.read_text(encoding="utf-8"))
        conflicts = json.loads(conflicts_path.read_text(encoding="utf-8"))
        logger.info("Loaded %d attributions, %d conflicts", len(attributions), len(conflicts))

        attributions = resolve_conflicts(
            chapter, conflicts, attributions, pov_character, pov_ranges=pov_ranges
        )
    else:
        logger.info(
            "Attributing chapter %d (POV: %s, window: %d, overlap: %d)",
            chapter_num,
            pov_character,
            window_size,
            overlap,
        )

        attributions, conflicts = attribute_chapter(
            chapter, pov_character, window_size, overlap, pov_ranges
        )

        # Second pass: resolve conflicts with focused context windows
        if conflicts:
            logger.info("%d conflicts from first pass, running resolution...", len(conflicts))
            conflicts_path.write_text(
                json.dumps(conflicts, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            attributions = resolve_conflicts(
                chapter, conflicts, attributions, pov_character, pov_ranges=pov_ranges
            )
        else:
            logger.info("No conflicts detected")

    # Save final attributions
    out_path.write_text(
        json.dumps(attributions, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Saved %d attributions → %s", len(attributions), out_path)
