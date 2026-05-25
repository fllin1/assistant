Voice Tuning is the companion sub-project for auditioning and accepting TTS voices.

Project path:

```text
/Users/regiswoof/_workspace/tools/voice-tuning
```

## Purpose

| Responsibility | Contract |
| --- | --- |
| Audition | generate comparable samples across supported engines. |
| Selection | store accepted cast choices per character slot. |
| Engine boundary | provide rendering access to configured TTS engines. |
| Secret boundary | keep provider keys inside the Voice Tuning environment. |

## Engines

| Engine | Provider | Contract |
| --- | --- | --- |
| `kokoro` | local | local voice generation. |
| `orpheus` | local | local voice generation. |
| `hume` | cloud | requires `HUME_API_KEY` in Voice Tuning `.env`. |

## Stored Data

| Table | Meaning |
| --- | --- |
| `results` | generated samples with engine, voice, speed, params, cache hash. |
| `casting` | accepted sample per character slot. |
| `voice_notes` | slot notes, ratings, playback speed. |

## Voice Mapping Entry

Accepted voices are promoted into the voice mapping shape:

```json
{
  "engine": "hume",
  "voice_id": "voice-id",
  "speed": 1.0,
  "params": {},
  "playback_speed": 1.0
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `engine` | yes | engine registry key. |
| `voice_id` | yes | engine-specific voice id. |
| `speed` | yes | engine render speed. |
| `params` | yes | engine-specific params. |
| `playback_speed` | yes | post-render playback adjustment. |

## Boundary

Voice Tuning decides accepted voice sound.

LN Voice Over decides speaker identity, exact spoken text, cache policy, timing, concatenation, and final media layout.
