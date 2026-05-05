# Please use https://github.com/balu100/RenpyUniversalTTS

## Ren'Py Universal VibeVoice TTS

A drop-in Ren'Py script that replaces Ren'Py self-voicing with low-latency
VibeVoice TTS.

Put `ai_tts_vibevoice_ffplay_raw_pcm_stream.rpy` and `ffplay.exe` into a
game's `game/` folder, run the VibeVoice server, and press `V` in-game to
toggle self-voicing.

## Quick Start

1. Start VibeVoice:

```powershell
git clone https://github.com/balu100/vibevoice-realtime-openai-api
cd vibevoice-realtime-openai-api
docker compose up -d --build
```

First run downloads models and voice presets, so it can take a while before
the server is ready.

2. Copy these files into the target game's `game/` folder:

```text
ai_tts_vibevoice_ffplay_raw_pcm_stream.rpy
ffplay.exe
```

3. Start the game.
4. Press `V` to enable Ren'Py self-voicing.
5. Press `V` again to turn it off.

Do not install multiple Ren'Py TTS replacement scripts at the same time. This
script sets `config.tts_function`.

## Requirements

- A Ren'Py game.
- Docker, for the VibeVoice server.
- `curl.exe`.
- `ffplay.exe`.

Windows includes `curl.exe` on most modern installs. This repo includes
`ffplay.exe` beside the `.rpy` file for convenience.

The default server URL is:

```text
http://localhost:8880/v1/audio/speech
```

## Basic Configuration

Open `ai_tts_vibevoice_ffplay_raw_pcm_stream.rpy` and edit the config values
near the top of the file.

### Default voice

```python
VIBEVOICE_DEFAULT_VOICE = "Emma"
```

This voice is used when the script cannot identify a speaker or no speaker
mapping exists.

### Speaker voices

```python
VIBEVOICE_VOICE_BY_SPEAKER = {
    "Narrator": "Davis",
    "MC": "Mike",
    "Daniel": "Mike",
}
```

Add or edit names to match the game:

```python
VIBEVOICE_VOICE_BY_SPEAKER = {
    "Narrator": "Davis",
    "Alice": "Emma",
    "Bob": "Carter",
    "Custom Character": "Grace",
}
```

Common VibeVoice voice IDs:

```text
OpenAI-style aliases:
alloy, echo, fable, onyx, nova, shimmer

VibeVoice names:
Carter, Davis, Emma, Frank, Grace, Mike, Samuel
```

Your running VibeVoice server is the final source of truth. If your server
supports a voice-list endpoint, check:

```text
http://localhost:8880/v1/audio/voices
```

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

### Server URL

```python
VIBEVOICE_URL = "http://localhost:8880/v1/audio/speech"
```

Change this if your VibeVoice server runs somewhere else.

## How It Works

This script sets Ren'Py's `config.tts_function`, so it only runs when Ren'Py
self-voicing is enabled. It does not patch every dialogue line directly.

When Ren'Py asks for a line to be spoken, the script starts this pipeline:

```text
curl.exe -sN --json @request.json http://localhost:8880/v1/audio/speech | ffplay.exe -nodisp -autoexit -f s16le -sample_rate 24000 -ch_layout mono -i -
```

`ffplay` receives one continuous raw PCM stream:

```text
s16le / 24000 Hz / mono
```

This avoids chunked WAV decoding and avoids waiting for a full MP3 file before
audio starts.

When a new line starts or self-voicing is turned off, the script stops the
current process tree so `cmd.exe`, `curl.exe`, and `ffplay.exe` do not keep
running in the background.

## Advanced Configuration

### VibeVoice request

```python
VIBEVOICE_MODEL = "tts-1"
VIBEVOICE_RESPONSE_FORMAT = "pcm"
VIBEVOICE_REQUEST_STREAM = True
```

### PCM playback format

```python
VIBEVOICE_PCM_SAMPLE_FORMAT = "s16le"
VIBEVOICE_PCM_SAMPLE_RATE = 24000
VIBEVOICE_PCM_CHANNEL_LAYOUT = "mono"
```

These values must match the raw PCM stream produced by the server.

### External tools

```python
VIBEVOICE_CURL_PATH = "curl.exe"
VIBEVOICE_FFPLAY_PATH = "ffplay.exe"
VIBEVOICE_FFPLAY_LOGLEVEL = "error"
VIBEVOICE_FFPLAY_VOLUME = None
VIBEVOICE_FFPLAY_EXTRA_ARGS = ()
```

If `ffplay.exe` is not beside the script and not on `PATH`, set an absolute
path:

```python
VIBEVOICE_FFPLAY_PATH = "C:/Tools/ffmpeg/bin/ffplay.exe"
```

Optional volume example:

```python
VIBEVOICE_FFPLAY_VOLUME = 80
```

## Test The Server

PowerShell:

```powershell
$body = @{
  model = "tts-1"
  voice = "Carter"
  input = "Hello from VibeVoice."
  response_format = "pcm"
  stream = $true
} | ConvertTo-Json -Compress

$tmp = Join-Path $env:TEMP "vibevoice_tts.json"
Set-Content -NoNewline -Encoding ascii $tmp $body

cmd /c "curl.exe -sN --json @$tmp http://localhost:8880/v1/audio/speech | ffplay.exe -nodisp -autoexit -f s16le -sample_rate 24000 -ch_layout mono -i -"
```

If that command works, the Ren'Py script is using the same audio path.

## Troubleshooting

### Nothing happens when pressing `V`

- Make sure `ai_tts_vibevoice_ffplay_raw_pcm_stream.rpy` is inside the game's
  `game/` folder.
- Make sure the game supports Ren'Py self-voicing.
- Check `log.txt` for lines starting with `VIBEVOICE FFPLAY RAW PCM TTS`.

### The game logs VibeVoice connection errors

- Make sure the VibeVoice server is still running.
- Open `http://localhost:8880/health` in a browser if your server provides a
  health endpoint.
- Check that `VIBEVOICE_URL` matches the server address.

### The API works but no sound plays

- Run the PowerShell test command from `Test The Server`.
- Make sure `ffplay.exe` is beside the `.rpy` file or on `PATH`.
- Make sure your server is returning raw PCM for `response_format = "pcm"`.
- Check that the PCM format is `s16le / 24000 Hz / mono`.

### Voice volume is too low or muted

This version plays through external `ffplay`, not Ren'Py's voice mixer.
Ren'Py voice volume and mute settings do not control it.

Use:

```python
VIBEVOICE_FFPLAY_VOLUME = 80
```

or adjust system volume.

### Speaker names are still read incorrectly

Ren'Py games format self-voicing text differently. This script detects common
formats like:

```text
Alice: Hello.
Alice. Hello.
Alice - Hello.
```

If a game uses another format, the speaker name may not be detected.

## Expected Logs

```text
VIBEVOICE FFPLAY RAW PCM TTS: stream MISS
VIBEVOICE FFPLAY RAW PCM TTS: pcm decode | format='s16le' | sample_rate=24000 | channel_layout='mono'
VIBEVOICE FFPLAY RAW PCM TTS: cmd pipe started
VIBEVOICE FFPLAY RAW PCM TTS: cmd pipe finished
```

## Notes

- This is meant as a universal drop-in helper, so it avoids editing the target
  game's scripts.
- It depends on Ren'Py self-voicing. Use `V` to control it.
- It expects a local VibeVoice server. The script does not start VibeVoice by
  itself.
- Audio is played by `ffplay`, outside Ren'Py's mixer.
- Security tools may warn when a game starts `cmd.exe`, `curl.exe`, and
  `ffplay.exe`.
