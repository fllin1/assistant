Generation turns accepted scenes into reproducible audio and visual media.

Generation consumes only `scenes/final/` and series-level render configuration.

## Purpose

| Output | Contract |
| --- | --- |
| Generation manifest | `<volume>/generation/chapter_XX[_M]/manifest.json` records source, settings, outputs, and status. |
| Audio manifest | `<volume>/generation/chapter_XX[_M]/audio_manifest.json` maps beats to stems, voices, cache keys, and timing. |
| Visual timeline | `<volume>/generation/chapter_XX[_M]/timeline.json` maps beats to timed visual states. |
| Media outputs | chapter audio and video files recorded by the manifest. |

Sufficient handoff: the generation package identifies every file needed to play or publish the chapter.

## Inputs

```text
<volume>/scenes/final/chapter_XX[_M].json
<series>/config/voice_mapping.json
<series>/config/visual_profile.json
<series>/config/render_profile.json
<series>/assets/
```

## Generation Manifest

```json
{
  "schema_version": 1,
  "artifact_kind": "generation_manifest",
  "series": "classroom-of-the-elite-year-2",
  "volume": "v4",
  "chapter_id": "chapter_07_1",
  "status": "complete",
  "scene_source": "scenes/final/chapter_07_1.json",
  "outputs": {
    "audio": "generation/chapter_07_1/audio.wav",
    "audio_manifest": "generation/chapter_07_1/audio_manifest.json",
    "timeline": "generation/chapter_07_1/timeline.json",
    "video": "generation/chapter_07_1/video.mp4"
  },
  "render_profile": "default",
  "voice_mapping": "config/voice_mapping.json"
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `artifact_kind` | yes | `generation_manifest`. |
| `status` | yes | `pending`, `running`, `complete`, `failed`, `blocked`, or `skipped`. |
| `scene_source` | yes | final scene contract used. |
| `outputs.audio` | yes | final chapter WAV. |
| `outputs.audio_manifest` | yes | audio manifest path. |
| `outputs.timeline` | yes | visual timeline path. |
| `outputs.video` | yes | final video path. |
| `render_profile` | yes | render profile id. |
| `voice_mapping` | yes | voice mapping path. |

## Audio Manifest

```json
{
  "schema_version": 1,
  "artifact_kind": "audio_manifest",
  "series": "classroom-of-the-elite-year-2",
  "volume": "v4",
  "chapter_id": "chapter_07_1",
  "beats": []
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `artifact_kind` | yes | `audio_manifest`. |
| `beats` | yes | ordered audio records. |
| `beats[].beat_id` | yes | source scene beat id. |
| `beats[].beat_type` | yes | source beat type. |
| `beats[].speaker` | spoken beats | resolved speaker. |
| `beats[].voice_key` | spoken beats | key in voice mapping. |
| `beats[].engine` | spoken beats | TTS engine id. |
| `beats[].voice_id` | spoken beats | engine voice id. |
| `beats[].cache_key` | spoken beats | reusable audio cache key. |
| `beats[].stem` | yes | rendered stem path. |
| `beats[].start_ms` | yes | beat start. |
| `beats[].duration_ms` | yes | beat duration. |
| `beats[].end_ms` | yes | beat end. |
| `beats[].silence_ms` | silence | explicit silence duration. |

## Visual Timeline

```json
{
  "schema_version": 1,
  "artifact_kind": "visual_timeline",
  "series": "classroom-of-the-elite-year-2",
  "volume": "v4",
  "chapter_id": "chapter_07_1",
  "beats": []
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `artifact_kind` | yes | `visual_timeline`. |
| `beats` | yes | ordered visual states. |
| `beats[].beat_id` | yes | source scene beat id. |
| `beats[].start_ms` | yes | visual start time. |
| `beats[].end_ms` | yes | visual end time. |
| `beats[].background` | yes | background asset id. |
| `beats[].visible_characters` | yes | visible character image asset ids. |
| `beats[].bubble_text` | no | displayed bubble text. |
| `beats[].visual_action` | no | render instruction. |

## Text Policy

| Beat type | Generation behavior |
| --- | --- |
| `dialogue` | speak `spoken_text`; strip one balanced outer quote pair before TTS. |
| `narration` | speak `spoken_text` unchanged. |
| `silence` | render silence. |
| `omitted`, `note` | no TTS. |
| `chapter_header` | speak only when accepted as a spoken beat. |

## Cache Inputs

- engine version;
- engine;
- voice id;
- speed;
- params;
- resolved TTS text;
- beat type.

## Validation

- scene input has `status: accepted`;
- spoken beats resolve a voice key and engine;
- silence beats have `silence_ms`;
- audio beats have complete timing after render;
- timeline beats reference scene beats;
- visual assets resolve;
- output files match manifest paths.
