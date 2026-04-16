# Stage 6a: Voice Assignment

Before synthesizing audio, each character needs a TTS voice. This guide covers browsing, auditioning, and assigning voices using the CLI.

## Overview

```
characters.json (who speaks) + Edge TTS voices (how they sound) → voices.json (mapping)
```

Voice resolution at synthesis time follows this fallback chain:
1. **Exact match** — character has an assigned voice in `voices.json`
2. **Gender default** — falls back to `default_male` or `default_female`
3. **Narrator default** — final fallback for anything unresolved

Main and supporting characters should get unique voices. Minor characters can share gender defaults.

## Step 1: Browse Available Voices

```bash
# List all English voices
lnvo list-voices

# Filter by gender
lnvo list-voices --gender male
lnvo list-voices --gender female

# Filter by locale (e.g. British English only)
lnvo list-voices --locale en-GB
```

### Recommended en-US Voices

**Male:**
| Voice ID | Character |
|----------|-----------|
| `en-US-AndrewNeural` | Natural, conversational |
| `en-US-BrianNeural` | Calm, measured |
| `en-US-ChristopherNeural` | Authoritative |
| `en-US-EricNeural` | Warm, friendly |
| `en-US-GuyNeural` | Neutral, clear |
| `en-US-RogerNeural` | Deep, mature |
| `en-US-SteffanNeural` | Young, energetic |

**Female:**
| Voice ID | Character |
|----------|-----------|
| `en-US-AriaNeural` | Expressive, versatile |
| `en-US-AvaNeural` | Warm, natural |
| `en-US-EmmaNeural` | Soft, friendly |
| `en-US-JennyNeural` | Clear, professional |
| `en-US-MichelleNeural` | Bright, upbeat |
| `en-US-AnaNeural` | Young |

Non-US accents (`en-GB-RyanNeural`, `en-AU-WilliamMultilingualNeural`, etc.) can help differentiate characters who should sound distinct.

## Step 2: Audition Voices

Listen to a voice before assigning it:

```bash
# Default sample text
lnvo audition en-US-BrianNeural

# Custom text
lnvo audition en-US-BrianNeural --text "I have no intention of losing."

# Use a real dialogue line from the character's resolved chapters
lnvo audition en-US-BrianNeural --character "Ayanokouji Kiyotaka" --book classroom-of-the-elite-year-2
```

The `--character` option searches `reviewed/` then `resolved/` chapters for a dialogue line by that character (at least 20 chars). This lets you hear how the voice sounds with actual book dialogue.

## Step 3: Assign Voices

```bash
lnvo assign-voice <book-slug> "<character-name>" <voice-id>
```

Example:

```bash
lnvo assign-voice classroom-of-the-elite-year-2 "Ayanokouji Kiyotaka" en-US-AndrewNeural
lnvo assign-voice classroom-of-the-elite-year-2 "Horikita Suzune" en-US-EmmaNeural
lnvo assign-voice classroom-of-the-elite-year-2 "Ryuuen Kakeru" en-GB-RyanNeural
```

- The character name must match `characters.json` (canonical name or alias)
- Re-running the command for the same character updates the assignment
- Assignments are saved to `config/voices.json`

## Step 4: Review Assignments

```bash
lnvo show-voices <book-slug>
```

Output groups characters into:
- **Assigned** — characters with explicit voice mappings
- **Unassigned (main/supporting)** — these should get unique voices
- **Unassigned (minor)** — can share gender defaults
- **Defaults** — narrator, male fallback, female fallback

## Changing Defaults

The gender defaults and narrator voice are set in `config/voices.json`. To change them, edit the file directly:

```json
{
  "default_narrator": {
    "speaker": "Narrator",
    "provider": "edge",
    "voice_id": "en-US-AriaNeural",
    "settings": null
  },
  "default_male": {
    "speaker": "__default_male__",
    "provider": "edge",
    "voice_id": "en-US-GuyNeural",
    "settings": null
  },
  "default_female": {
    "speaker": "__default_female__",
    "provider": "edge",
    "voice_id": "en-US-JennyNeural",
    "settings": null
  }
}
```

## Available Providers

| Provider | Voices | Cost | Quality | Notes |
|----------|-------:|------|---------|-------|
| **Edge TTS** | 47 English (17 en-US) | Free | Good | No API key. Default provider |
| **OpenAI TTS** | 10 | ~$15/1M chars | Excellent | Requires `OPENAI_API_KEY` |
| **Kokoro TTS** | 27 (20 American + 7 British) | Free | Very good | Local, no API key, ~350MB model |

Use `--provider edge|openai|kokoro` with `list-voices`, `audition`, and `assign-voice --provider-name`.

---

## Classroom of the Elite — Year 2 Volume 7

Book slug: `classroom-of-the-elite-year-2-v7`

10 chapters covering the cultural festival arc and its aftermath. POV alternates between Ayanokouji (7 chapters), Horikita (2 chapters), and Hasebe (1 chapter).

### Character Registry

Characters are listed by dialogue line count. The **Tier** column indicates voice assignment priority:
- **S** — Protagonist/narrator. Heard constantly. Must have a distinctive, pleasant voice.
- **A** — Major characters with 100+ lines. Need unique, well-matched voices.
- **B** — Significant characters with 20–99 lines. Should have unique voices.
- **C** — Minor characters with 5–19 lines. Unique voice is nice but not essential.
- **D** — Background characters with <5 lines. Gender default is fine.

#### Protagonist & Major Characters (Tier S–A)

| Character | Lines | Gender | Class | Tier | Description |
|-----------|------:|--------|-------|:----:|-------------|
| Ayanokouji Kiyotaka | 679 | M | 2-D | S | Protagonist and first-person narrator for 7 of 10 chapters. Calm, analytical, emotionally guarded. Hides exceptional abilities behind an average facade. His inner monologue drives the story. |
| Horikita Suzune | 346 | F | 2-D | A | Class leader and POV character for chapters 4b and 8. Sharp, direct, serious. Lacks social warmth but is fiercely determined. Growing into a capable leader. |
| Yagami Takuya | 179 | M | 1-? | A | First-year student and Student Council secretary. Polite and helpful on the surface — secretly a White Room enforcer. Manipulative, calculating, dangerous. Central antagonist lurking behind a friendly mask. |
| Nagumo Miyabi | 145 | M | 3-A | A | Student Council president and third-year powerhouse. Arrogant, provocative, loves to exert dominance. Targets Ayanokouji as his next challenge. Charismatic but threatening. |
| Kushida Kikyou | 141 | F | 2-D | A | Class 2-D's "angel" — sweet, helpful, adored by everyone. In reality, deeply resentful and manipulative. Refuses to cooperate during festival prep, forcing a confrontation. Two distinct personalities: saccharine public vs venomous private. |
| Kanzaki Ryuuji | 116 | M | 2-B | A | Principled, serious, strategically-minded. Questioning Ichinose's idealistic leadership and whether kindness alone can win. Recruiting allies for a potential class revolt. |
| Hasebe Haruka | 113 | F | 2-D | A | POV character for chapter 1. Part of Ayanokouji's friend group. Emotional, loyal, but harboring deep resentment over Sakura Airi's expulsion. Her anger toward Ayanokouji drives the opening arc. |

#### Significant Supporting Characters (Tier B)

| Character | Lines | Gender | Class | Tier | Description |
|-----------|------:|--------|-------|:----:|-------------|
| Chabashira Sae | 74 | F | Teacher | B | Class 2-D homeroom teacher. Stern, no-nonsense, occasionally sardonic. Has a personal stake in her class reaching Class A. Authority figure voice. |
| Ryuuen Kakeru | 60 | M | 2-C | B | Class 2-C's aggressive, intimidating leader. Loud, cocky, confrontational. Running a Japanese-style cafe at the festival. Speaks with brash confidence and casual threats. |
| Himeno Yuki | 49 | F | 2-B | B | Recruited by Kanzaki to challenge Ichinose's leadership. Thoughtful, observant, willing to question the status quo. A quieter presence than most. |
| Sudou Ken | 48 | M | 2-D | B | Hot-headed, impulsive, physically strong. Has matured somewhat but still speaks bluntly. Athletic type. |
| Asahina Nazuna | 44 | F | 3-? | B | Third-year student. Warm, approachable, but navigating complex third-year politics around Nagumo. Acts as a bridge between year groups. |
| Amasawa Ichika | 40 | F | 1-? | B | First-year student. Playful, teasing, unpredictable. Another White Room agent but with her own agenda — doesn't simply follow orders. Mischievous and slightly dangerous. |
| Karuizawa Kei | 39 | F | 2-D | B | Ayanokouji's girlfriend. Warm, emotional, socially savvy. Former bully victim who reinvented herself. Protective of her relationship. Affectionate in private, composed in public. |
| Matsushita Chiaki | 39 | F | 2-D | B | Observant, competent, quietly ambitious. Excels as the maid cafe lead during the festival. Speaks with composed confidence. |
| Mashima Tomonari | 30 | M | Teacher | B | Class 2-A homeroom teacher. Formal, measured, authoritative. Delivers announcements and rules with dry precision. |
| Ibuki Mio | 28 | F | 2-C | B | Tough, combative, resistant to authority. Forced into a Japanese outfit by Ryuuen (which she hates). Speaks sharply and defensively. |
| Maezono An | 28 | F | 2-D | B | Vocal, assertive, questions absences and unfairness openly. Class conscience — speaks up when others stay quiet. |
| Ishizaki Daichi | 26 | M | 2-C | B | Ryuuen's loyal follower. Not the sharpest, but enthusiastic and loud. Runs the festival stall with Albert. |
| Satou Maya | 25 | F | 2-D | B | Cheerful, social, close with Kei. Had a crush on Ayanokouji earlier. Sweet-natured, gossip-prone. |
| Hashimoto Masayoshi | 23 | M | 2-A | B | Smooth, calculating, double-agent type. Monitors other classes for Sakayanagi while keeping his own options open. Speaks with casual charm hiding sharp observations. |
| Ike Kanji | 23 | M | 2-D | B | Comedic relief. Loud, excitable, not very bright. Enthusiastic about everything. |
| Wang Mei-Yu | 21 | F | 2-D | B | Extremely shy, soft-spoken, nervous. Working as a maid at the cafe is agonizing for her. Speaks hesitantly. |
| Tsubaki Sakurako | 21 | F | 1-? | B | First-year student. Calm, strategic, calculating. Working behind the scenes as part of the first-year power plays. Controlled, measured speech. |
| Miyake Akito | 20 | M | 2-D | B | Ayanokouji's friend group. Reliable, level-headed, quiet. The steady one in the group. Doesn't talk much, but when he does it matters. |

#### Minor Characters (Tier C)

| Character | Lines | Gender | Class | Tier | Description |
|-----------|------:|--------|-------|:----:|-------------|
| Ichihashi | 16 | F | 2-D | C | Delivers a love letter in chapter 4a. Brief but memorable scene. |
| Shiina Hiyori | 15 | F | 2-C | C | Gentle bookworm. Works the register at Ryuuen's cafe. Soft-spoken and kind. |
| Hirata Yousuke | 13 | M | 2-D | C | Class mediator and peacekeeper. Popular, empathetic, diplomatic. |
| Ichinose Honami | 11 | F | 2-B | C | Class 2-B leader. Idealistic, earnest, kind to a fault. Her leadership style is under scrutiny from Kanzaki. |
| Sakayanagi Arisu | 8 | F | 2-A | C | Class 2-A leader. Brilliant, elegant, physically frail (uses a cane). Speaks with refined confidence and hidden amusement. Keeps her festival plans secret. |
| Housen Kazuomi | 7 | M | 1-D | C | First-year delinquent. Aggressive, confrontational, runs a target shooting stall. |
| Kiriyama Ikuto | 6 | M | 3-? | C | Third-year, Student Council Vice President. Serious, formal, politically aware. |
| Sakura Airi | 5 | F | ex-2-D | C | Former classmate, expelled before this volume. Central to chapter 7's emotional weight. Shy, insecure, gentle. Appears in flashbacks/references. |
| Onodera Kayano | 5 | F | 2-D | C | Minor presence in class scenes. |

#### Background Characters (Tier D — gender default voice is fine)

| Character | Lines | Gender | Class | Description |
|-----------|------:|--------|-------|-------------|
| Hondou Ryoutarou | 3 | M | 2-D | Festival food delivery. |
| Shinohara Satsuki | 2 | F | 2-D | Reconciling with classmates. |
| Kaneda Satoru | 2 | M | 2-C | Brief appearance. |
| Komiya Shiho | 2 | M | 1-? | Victim of Yagami's attack on the island. Referenced. |
| Kinoshita Minori | 2 | F | 1-? | Victim of Yagami's attack on the island. Referenced. |
| Utomiya Riku | 2 | M | 1-? | Tsubaki's classmate. Brief appearance. |
| Yamada Albert | 1 | M | 2-C | Works with Ishizaki. Barely speaks (canon — he's very quiet). |
| Horikita Manabu | 1 | M | Grad | Former Student Council president, Suzune's brother. Referenced. |
| Kamuro Masumi | 1 | F | 2-A | Brief appearance. |
| Sakagami Kazuma | 1 | M | Teacher | Class 2-B homeroom teacher. Brief appearance. |
| Tsukishiro | 1 | M | Staff | Acting director, sent by the White Room. Brief appearance. |
| Kouenji Rokusuke | 0 | M | 2-D | Refuses to participate. No dialogue this volume. |
| Yukimura Teruhiko | 0 | M | 2-D | Ayanokouji's study group. No dialogue this volume. |
| Sotomura Hideo | 0 | M | 2-D | Helps with festival prep. No dialogue this volume. |
| Inogashira Kokoro | 0 | F | 2-D | No dialogue this volume. |

### Current Assignments

| Character | Voice | Provider |
|-----------|-------|----------|
| Ayanokouji Kiyotaka | echo | OpenAI |
| Horikita Suzune | coral | OpenAI |
| Yagami Takuya | fable | OpenAI |
| Nagumo Miyabi | onyx | OpenAI |
| Kushida Kikyou | nova | OpenAI |
| Kanzaki Ryuuji | ash | OpenAI |
| Hasebe Haruka | sage | OpenAI |
| Chabashira Sae | alloy | OpenAI |
| Karuizawa Kei | shimmer | OpenAI |

9 characters assigned (OpenAI). 1 OpenAI voice remaining (`ballad`). 20 Kokoro American + 7 British + 17 Edge en-US voices available for the rest.

---

## Tips

- **Prioritize main characters.** They have the most dialogue — distinct voices matter most here.
- **Use accent variety.** A British voice for one character, Australian for another, helps listeners distinguish speakers without conscious effort.
- **Narrator voice should be neutral.** The narrator reads the most text — pick something easy to listen to for long stretches.
- **Test with actual dialogue.** Always use `--character` to hear how the voice handles the character's actual speech patterns.
- **Re-synthesis is cheap.** Changing a voice assignment only re-synthesizes that character's segments (cache key includes voice ID). Everything else stays cached.
