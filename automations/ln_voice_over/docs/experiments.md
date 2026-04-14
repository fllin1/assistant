# Extraction Experiments — Command Reference

## Setup

```bash
# Pull models (one-time)
ollama pull gemma4:26b
ollama pull qwen3.5:27b
```

All commands use `lnvo` (or `python -m automations.ln_voice_over.cli`).
Chapter 2 has 578 dialogues (6 batches of 100).

---

## Experiment 1: Baseline (±5 symmetric context, gemma4:26b, prompt v1)

```bash
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 0 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 100 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 200 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 300 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 400 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 500 --batch-size 100 --pov "Ayanokouji Kiyotaka"
```

## Experiment 2: Asymmetric context (10 before / 3 after, gemma4:26b, prompt v1)

```bash
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 0 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 100 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 200 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 300 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 400 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 500 --batch-size 100 --pov "Ayanokouji Kiyotaka"
```

## Experiment 3: Cross-validation with Qwen (±5, qwen3.5:27b, prompt v1)

```bash
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 0 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 100 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 200 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 300 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 400 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 5 --context-after 5 --batch-start 500 --batch-size 100 --pov "Ayanokouji Kiyotaka"
```

## Experiment 4: Qwen with asymmetric context (10/3, qwen3.5:27b, prompt v1)

```bash
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 0 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 100 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 200 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 300 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 400 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model qwen3.5:27b --prompt-version v1 --context-before 10 --context-after 3 --batch-start 500 --batch-size 100 --pov "Ayanokouji Kiyotaka"
```

## Experiment 5: Prompt v2 + rolling context (±5, gemma4:26b)

Tests the improved prompt (tag-linking guidelines, "I" in narration clarification) with rolling previous attributions.

```bash
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 5 --context-after 5 --rolling-context --batch-start 0 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 5 --context-after 5 --rolling-context --batch-start 100 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 5 --context-after 5 --rolling-context --batch-start 200 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 5 --context-after 5 --rolling-context --batch-start 300 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 5 --context-after 5 --rolling-context --batch-start 400 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 5 --context-after 5 --rolling-context --batch-start 500 --batch-size 100 --pov "Ayanokouji Kiyotaka"
```

## Experiment 6: Prompt v2 + asymmetric + rolling (10/3, gemma4:26b)

Combines all improvements: better prompt, more context before, rolling attributions.

```bash
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 10 --context-after 3 --rolling-context --batch-start 0 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 10 --context-after 3 --rolling-context --batch-start 100 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 10 --context-after 3 --rolling-context --batch-start 200 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 10 --context-after 3 --rolling-context --batch-start 300 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 10 --context-after 3 --rolling-context --batch-start 400 --batch-size 100 --pov "Ayanokouji Kiyotaka"
lnvo extract classroom-of-the-elite-year-2 --chapter 2 --model gemma4:26b --prompt-version v2 --context-before 10 --context-after 3 --rolling-context --batch-start 500 --batch-size 100 --pov "Ayanokouji Kiyotaka"
```

---

## Comparing Results

```bash
# List all experiments
ls ~/.assistant/ln_voice_over/projects/classroom-of-the-elite-year-2/experiments/extraction/

# Compare a specific experiment against ground truth
lnvo compare classroom-of-the-elite-year-2 <experiment_id>
```

---

## Notes

- Run all 6 batches of one model before switching to the next (avoids model loading/unloading)
- Experiment IDs are printed after each `extract` command
- Each experiment saves `config.json` + `results.json` + `comparison.json` (after compare)
- Ground truth: `~/.assistant/ln_voice_over/projects/classroom-of-the-elite-year-2/ground_truth_chapter_02.json`
