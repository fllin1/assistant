Series Parameters are accepted once per series and referenced by every volume.

They are external parameters: human-led, AI-assisted, stable before volume processing.

## Purpose

| Parameter | Contract | Consumers |
| --- | --- | --- |
| Story profile | story-specific structure rules. | Prepare, Transform, Scenes. |
| Character registry | canonical characters, aliases, gender, role. | Dialogue, Scenes, Generation. |
| Voice mapping | accepted TTS voice per voice key. | Generation. |
| Narration profile | narration adaptation settings. | Scenes. |
| Visual profile | backgrounds and character image bank. | Scenes, Generation. |
| Render profile | final media dimensions and formats. | Generation. |

## Story Profile

```json
{
  "schema_version": 1,
  "profile_id": "classroom-of-the-elite",
  "display_name": "Classroom of the Elite",
  "rules": {}
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `schema_version` | yes | profile schema version. |
| `profile_id` | yes | stable profile id. |
| `display_name` | yes | human label. |
| `rules` | yes | story-specific rule object. |

## Character Registry

```json
{
  "schema_version": 1,
  "characters": [
    {
      "name": "Horikita Suzune",
      "aliases": ["Horikita"],
      "description": "",
      "gender": "female",
      "role": "main"
    }
  ]
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `characters[].name` | yes | canonical character name. |
| `characters[].aliases` | yes | accepted name variants. |
| `characters[].description` | yes | attribution context. |
| `characters[].gender` | yes | voice fallback and metadata. |
| `characters[].role` | yes | story priority label. |

## Voice Mapping

```json
{
  "schema_version": 1,
  "entries": {
    "Horikita Suzune": {
      "engine": "hume",
      "voice_id": "voice-id",
      "speed": 1.0,
      "params": {},
      "playback_speed": 1.0
    }
  }
}
```

| Key | Required | Contract |
| --- | --- | --- |
| `entries` | yes | map from voice key to accepted voice. |
| `engine` | yes | TTS engine id. |
| `voice_id` | yes | engine voice id. |
| `speed` | yes | engine render speed. |
| `params` | yes | engine-specific params. |
| `playback_speed` | yes | post-render playback speed. |

## Narration Profile

```json
{
  "schema_version": 1,
  "profile_id": "default",
  "settings": {}
}
```

## Visual Profile

```json
{
  "schema_version": 1,
  "profile_id": "default",
  "backgrounds": {},
  "character_images": {}
}
```

## Render Profile

```json
{
  "schema_version": 1,
  "profile_id": "default",
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "audio_format": "wav",
  "video_format": "mp4"
}
```

## Validation

- referenced profile ids exist;
- character names are unique;
- voice mapping keys cover required speakers before generation;
- visual asset ids resolve before scenes or generation;
- render profile values are positive and supported.
