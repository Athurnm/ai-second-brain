# Meeting Recorder (local note-taker)

Record meetings on your own machine, transcribe them locally on your GPU (or via the
Gemini API), and get a meeting-minutes (MOM) draft automatically. This is a local,
private alternative to a cloud recorder like Fathom. Use either or both: the recorder
writes into the same registry Fathom does, so one meeting still produces one MOM.

It lives in `meeting-recorder/`. Everything is plain Python (stdlib) plus `ffmpeg`;
the local-GPU transcription step is optional.

- [How it works](#how-it-works)
- [Platform support](#platform-support)
- [Quick start](#quick-start)
- [Transcription engines](#transcription-engines)
- [Daily use](#daily-use)
- [Advanced: Vexa auto-join bot](#advanced-vexa-auto-join-bot)
- [Troubleshooting](#troubleshooting)

---

## How it works

```
recorder.py  →  .wav in your recordings folder  →  watcher.py
                                                     ├─ transcribe.py  (whisper.cpp GPU, or Gemini)
                                                     ├─ journal/fathom_registry.json   (dedupe key)
                                                     └─ MOM draft in your Clients/<context>/meetings folder
```

1. **Capture**: `recorder.py` records system audio + mic to a `.wav` (optionally a screen-record `.mp4` too).
2. **Watch**: `watcher.py` notices new audio files and runs the pipeline.
3. **Transcribe**: `transcribe.py` turns audio into a timestamped transcript.
4. **Draft**: the transcript is turned into a MOM draft you review (never sent anywhere).

Steps 2 to 4 also run standalone, so you can drop in an `.m4a` from any source and get the same result.

---

## Platform support

The recorder runs on macOS, Windows, and Linux/WSL. What differs is how each OS captures audio:

| Platform | Audio capture | Local GPU transcription | Notes |
|---|---|---|---|
| **macOS** (Apple Silicon) | `ffmpeg` + avfoundation; use a loopback device (e.g. BlackHole) for system audio | whisper.cpp with Metal (`brew install whisper-cpp`) | Fully native. |
| **Windows** | `pyaudiowpatch` (WASAPI loopback, captures system audio cleanly) | whisper.cpp (Vulkan/CUDA) via `whisper-server.exe` | A small GUI (`gui_win.pyw`) is included. |
| **Linux / WSL** | `ffmpeg` + PulseAudio (`<sink>.monitor`) | whisper.cpp (CUDA/Vulkan) if you have a GPU | In WSL, capture often runs on the Windows side and the pipeline runs in WSL. |

If you have no GPU, skip local transcription and use the Gemini engine (see [engines](#transcription-engines)); everything else works the same.

---

## Quick start

### 1. Install prerequisites

`ffmpeg` is the only hard requirement.

```bash
# macOS
brew install ffmpeg
brew install whisper-cpp          # optional: local GPU transcription

# Linux / WSL (Debian/Ubuntu)
sudo apt install -y ffmpeg pulseaudio-utils

# Windows (in your Windows Python, for capture)
pip install PyAudioWPatch
```

For local GPU transcription you need a whisper.cpp build and a model file
(`ggml-large-v3-turbo.bin` is a good default). Building whisper.cpp is per-platform;
see the whisper.cpp project. This step is optional.

### 2. Configure

```bash
cp meeting-recorder/config.example.json meeting-recorder/config.json
```

Open `config.json` and, under the section for your platform (`macos` / `windows` / `wsl`), set:

- `recordings_dir`: where `.wav` files are written.
- `whispercpp_bin` and `whispercpp_model`: paths to your whisper.cpp binary + model. Leave empty to skip local GPU and use Gemini.
- macOS only: `avfoundation_audio_device`: the loopback device index from `--list-devices`.

### 3. Record and process

```bash
# List audio devices (find your loopback/monitor device)
python3 meeting-recorder/recorder.py --list-devices

# Record (Ctrl-C to stop)
python3 meeting-recorder/recorder.py "Sprint Planning"

# Process every new recording once (transcribe + MOM draft), then exit
python3 meeting-recorder/watcher.py --once
```

On Windows you can instead double-click the `gui_win.pyw` GUI: type a meeting name,
click Start / Stop, and optionally tick "Auto-process after stop."

---

## Transcription engines

`config.json`'s `engine` field controls the chain. Default is `auto`:

1. **`whispercpp`**: local GPU. Fast, private, free, no API key. Skipped automatically if the GPU probe fails (unless you force it).
2. **`cli`**: Gemini API (audio-in, gives speaker labels). Needs a Google AI API key. Put it in `.agent/skills/gemini-image/token.env` as your Gemini key, or set the model in `config.json` (`gemini_model`).

`auto` tries whisper.cpp first, then falls back to Gemini. It never silently falls back to
slow CPU whisper; set `engine: "cpu"` explicitly if you actually want that. Set
`require_gpu: false` to allow whisper.cpp without a detected GPU.

Run a single file through any engine:

```bash
python3 meeting-recorder/transcribe.py --in recording.m4a --out transcript.md --engine auto --lang auto
```

---

## Daily use

Leave the watcher running so recordings are processed as they land:

```bash
python3 meeting-recorder/watcher.py          # poll loop (default every 30s)
```

Each processed meeting writes:

- a timestamped transcript into your meetings/transcripts folder,
- a MOM draft into your meetings folder (review before sharing),
- an entry in `journal/fathom_registry.json` so the same meeting is not double-drafted if you also use Fathom.

To wire it to your calendar and MOM template, see the paths in `meeting-recorder/watcher.py`
(it invokes your calendar connector to match a recording to a calendar event).

---

## Advanced: Vexa auto-join bot

`vexa_bots.py` sends a bot to auto-join and transcribe your Google Meet / Teams calls,
so you do not have to record manually. **This is an advanced, optional path.** It requires
a self-hosted [Vexa](https://github.com/Vexa-ai/vexa) stack (Docker: the Vexa container,
Postgres, object storage, and a whisper transcription service). It is heavier to run than
the local recorder and is best on a Linux/WSL host with Docker.

```bash
cp meeting-recorder/vexa_token.env.example meeting-recorder/vexa_token.env
# fill in VEXA_API_KEY / VEXA_USER_ID from your Vexa instance

python3 meeting-recorder/vexa_bots.py status          # check the stack
python3 meeting-recorder/vexa_bots.py auto --dry-run  # preview which calls it would join
```

Put `vexa_bots.py auto` on a `*/5 * * * *` cron to auto-join every meeting with a link.
If you do not run a Vexa server, ignore this section entirely; the local recorder does not need it.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No audio / silent recording | Run `--list-devices` and set the right loopback/monitor device. On macOS install BlackHole; on Linux check `pactl list sources`. |
| Local transcription skipped | The GPU probe failed. Check `whispercpp_bin`/`whispercpp_model` paths, or set `engine: "cli"` to use Gemini. |
| "no module named pyaudiowpatch" (Windows) | `pip install PyAudioWPatch` in the Windows Python that runs `recorder.py`. |
| MOM draft step fails | The transcript still lands. The draft step needs your draft backend (e.g. agy-bridge) configured; check `draft_backend` in `config.json`. |
| Gemini engine errors | Confirm your Google AI key and that `gemini_model` in `config.json` is a model you have access to. |
