# Ren'Py Universal VibeVoice TTS

A drop-in Ren'Py script that replaces Ren'Py self-voicing with local VibeVoice
TTS.

Put `ai_tts_vibevoice.rpy` into a game's `game/` folder, run a local VibeVoice
server, and press `V` in-game to toggle self-voicing. When self-voicing is on,
Ren'Py sends text to this script, the script generates speech through
VibeVoice, caches the MP3, and plays it through Ren'Py's voice mixer.

## Requirements

- A Ren'Py game.
- Docker, if you use the VibeVoice Realtime container below.
- A VibeVoice OpenAI-compatible speech endpoint running at:

```text
http://localhost:8880/v1/audio/speech
```

## Start VibeVoice

```shell
git clone https://github.com/balu100/vibevoice-realtime-openai-api
cd vibevoice-realtime-openai-api
docker compose up -d --build
```

First run downloads models and voice presets, so it can take a while before the
server is ready.

## Install

1. Copy `ai_tts_vibevoice.rpy` into the target game's `game/` folder.
2. Start VibeVoice.
3. Start the game.
4. Press `V` to enable Ren'Py self-voicing.
5. Press `V` again to turn it off. Current VibeVoice playback and pending TTS
   work will be stopped.

## Configuration

Open `ai_tts_vibevoice.rpy` and edit the config values near the top of the
file.

### VibeVoice endpoint

```python
VIBEVOICE_URL = "http://localhost:8880/v1/audio/speech"
VIBEVOICE_MODEL = "tts-1-hd"
VIBEVOICE_RESPONSE_FORMAT = "mp3"
VIBEVOICE_TIMEOUT = 120
```

Change `VIBEVOICE_URL` if your VibeVoice server runs somewhere else.

Supported response formats include `mp3`, `wav`, `opus`, `flac`, `aac`, and
`pcm`. `mp3` is the default because it is compact and Ren'Py-friendly.

### Speaker name reading

```python
VIBEVOICE_READ_SPEAKER_NAMES = "on_speaker_change"
```

Options:

```python
VIBEVOICE_READ_SPEAKER_NAMES = "always"
VIBEVOICE_READ_SPEAKER_NAMES = "never"
VIBEVOICE_READ_SPEAKER_NAMES = "on_speaker_change"
```

- `"always"` reads the speaker name before every line.
- `"never"` removes speaker names from spoken dialogue.
- `"on_speaker_change"` reads the speaker name only when the speaker changes.

Example:

```text
Alice: Hello.      -> reads "Alice. Hello."
Alice: Come here.  -> reads "Come here."
Bob: Wait.         -> reads "Bob. Wait."
```

### Audio cache location

```python
VIBEVOICE_STORE_AUDIO_IN_GAME_DIR = False
```

Options:

```python
VIBEVOICE_STORE_AUDIO_IN_GAME_DIR = False
```

Prefer Ren'Py's save/user area for cached MP3 files. This is the safer default
because installed games may not allow writing inside the game folder.

```python
VIBEVOICE_STORE_AUDIO_IN_GAME_DIR = True
```

Prefer `game/tts_cache_vibevoice`, keeping generated audio beside the script
when the game folder is writable.

### Default voice

```python
VIBEVOICE_DEFAULT_VOICE = "Emma"
```

This voice is used when the script cannot identify a speaker or no speaker
mapping exists.

### Speaker voices

```python
VIBEVOICE_VOICE_BY_SPEAKER = {
    "Narrator": "Emma",
    "MC": "Carter",
}
```

Add or edit names to match the game:

```python
VIBEVOICE_VOICE_BY_SPEAKER = {
    "Narrator": "Emma",
    "Alice": "Grace",
    "Bob": "Carter",
    "Frank": "Frank",
}
```

Make sure every dictionary entry has a colon between the speaker and voice:

```python
"Custom Character": "Grace",
```

Available VibeVoice voice names:

```text
Carter
Davis
Emma
Frank
Grace
Mike
Samuel
```

OpenAI-style aliases also work:

```text
alloy   -> Carter
ash     -> Davis
ballad  -> Emma
coral   -> Grace
echo    -> Davis
fable   -> Emma
marin   -> Mike
onyx    -> Frank
nova    -> Grace
sage    -> Carter
shimmer -> Mike
verse   -> Samuel
```

Your running VibeVoice server is the final source of truth. To see the voices
available in your current container, open:

```text
http://localhost:8880/v1/audio/voices
```

## How It Works

This script sets Ren'Py's `config.tts_function`, so it only runs when Ren'Py
self-voicing is enabled. It does not patch every dialogue line directly.

Generated audio is requested in a background thread so a slow VibeVoice request
does not block the game UI. When the MP3 is ready, it is played through a custom
Ren'Py channel using the `voice` mixer, so the player's voice volume and mute
settings still apply.

The VibeVoice server can stream audio responses, but this script uses the safer
Ren'Py-compatible path: receive a complete audio file, cache it, then play it.
Ren'Py's normal audio API does not provide a stable public way to feed live HTTP
audio chunks directly into the mixer.

The cache key includes the VibeVoice URL, model, response format, voice, and
spoken text. If you change engine/model behavior and want to force
regeneration, change:

```python
VIBEVOICE_CACHE_VERSION = "vibevoice-realtime-openai-v1"
```

For example:

```python
VIBEVOICE_CACHE_VERSION = "vibevoice-realtime-openai-v2"
```

## Troubleshooting

### Nothing happens when pressing `V`

- Make sure `ai_tts_vibevoice.rpy` is inside the game's `game/` folder.
- Make sure the game supports Ren'Py self-voicing.
- Check `log.txt` for lines starting with `VIBEVOICE TTS`.

### The game logs VibeVoice connection errors

- Make sure the VibeVoice container is still running.
- Open `http://localhost:8880/health` in a browser to confirm the server
  responds.
- Check that `VIBEVOICE_URL` matches the server address.

### Test the endpoint manually

```powershell
$body = @{
  model = "tts-1-hd"
  input = "Welcome to VibeVoice."
  voice = "Emma"
  response_format = "mp3"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "http://localhost:8880/v1/audio/speech" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -OutFile "vibe_test.mp3"
```

### The first line is slow

That is expected on a cache miss. The script sends text to VibeVoice, waits for
the MP3, and then caches it. The same line should be faster next time.

### Voice volume is too low or muted

The script uses Ren'Py's `voice` mixer. Check the game's voice volume and mute
settings.

### Speaker names are still read incorrectly

Ren'Py games format self-voicing text differently. This script detects common
formats like:

```text
Alice: Hello.
Alice. Hello.
Alice - Hello.
```

If a game uses another format, the speaker name may not be detected.

## Notes

- This is meant as a universal drop-in helper, so it avoids editing the target
  game's scripts.
- It depends on Ren'Py self-voicing. Use `V` to control it.
- It expects a local VibeVoice server. The script does not start VibeVoice by
  itself.
