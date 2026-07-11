# meeting-recorder: Local Note-Taker (Fathom lokal)

Record meetings on your own machine, transcribe locally (GPU) or via Gemini
(CLI/API), and get a MOM draft in `Clients/Work/meetings/`, no Fathom needed.

## Routing policy (final, 2026-07-06)

| Recorder | Peran | Kapan |
| :--- | :--- | :--- |
| **Vexa bot** | **PRIMARY auto** | Cron `*/5` (`vexa_bots.py auto`): join otomatis SEMUA event kalender Work ber-Meet/Teams-link, sebagai bot "Your Name" |
| **Fathom** | Backup + video | Tetap jalan di meeting yang You hadiri; satu-satunya sumber video meeting attended (`fathom-frame-grab`) |
| **Desktop recorder** | Manual fallback + video on-demand | Bot gagal join / meeting offline / non-Meet; `--video` atau checkbox GUI untuk screen-record |

**Dedupe: satu meeting -> satu MOM.** Semua recorder nulis ke
`journal/fathom_registry.json`; entri untuk calendar meeting yang sama
(matched_meeting + tanggal) saling di-cross-ref via `related_recordings`, dan
MOM draft di-skip kalau entri terkait sudah punya `mom_path`.
`fathom_registry_sync.py` melakukan linking yang sama saat sync Fathom.

```
recorder.py (per mesin)  →  WAV di recordings_dir  →  watcher.py (host repo)
                                                        ├─ transcribe.py (whisper.cpp GPU → Gemini)
                                                        ├─ journal/fathom_registry.json (local-*)
                                                        ├─ MOM draft via agy-bridge (GLM/Gemini)
                                                        └─ heartbeat → dashboard :3737
```

**Engine rule (You):** GPU dulu (whisper.cpp Vulkan/Metal); kalau GPU tidak
tersedia, fallback ke **Gemini API** (audio-in, dapat speaker labels). TIDAK
pernah otomatis jatuh ke CPU; `engine: "cpu"` hanya kalau diset manual.

## Setup per mesin

### Windows (capture) + WSL (pipeline), mesin utama
1. **Windows-side** (PowerShell, sekali):
   ```powershell
   pip install pyaudiowpatch
   mkdir C:\Users\You\MeetingRecordings
   ```
2. Rekam (PowerShell): jalankan dengan Python Windows dari folder repo via WSL path:
   ```powershell
   python \\wsl.localhost\Ubuntu\home\you\antigravity-projects\product-second-brain\meeting-recorder\recorder.py "Nama Meeting"
   ```
   Stop dengan Ctrl-C. Hasil: `<stamp>_<slug>.sys.wav` (system audio) +
   `<stamp>_<slug>.mic.wav` (mic) + sidecar `.json`. Watcher yang me-mix.
3. **WSL-side** (pipeline): `python3 meeting-recorder/watcher.py` (atau `--once`).
4. **whisper.cpp GPU (Radeon RX 6600) -- SUDAH TERPASANG (2026-07-06)**: dibuild
   dari source v1.9.1 dengan Vulkan (tidak ada prebuilt resmi). Lokasi:
   binary `C:\tools\whisper.cpp-src\build\bin\whisper-cli.exe`, model
   `C:\tools\whisper.cpp-src\models\ggml-large-v3-turbo.bin`; sudah diisi di
   `config.json` section `wsl` (path `/mnt/c/...`). Benchmark: 2 menit audio =
   ~10 detik. Rebuild kalau perlu: `cmd.exe /c C:\tools\build_whisper.bat`
   (butuh VS BuildTools 2019 + Windows SDK 22621 + cmake + Ninja + Vulkan SDK
   1.4.350, semua sudah terpasang). Tanpa ini `auto` jatuh ke Gemini (metered
   ~$0.05-0.10 per meeting 1 jam).

### macOS (Apple Silicon, capture + pipeline satu mesin)
1. `brew install whisper-cpp ffmpeg` (Metal/GPU otomatis di M1).
2. Model: `curl -L -o ~/.cache/whisper-cpp/ggml-large-v3-turbo.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin`
3. System audio butuh **BlackHole**: `brew install blackhole-2ch`, lalu di
   Audio MIDI Setup bikin Multi-Output (speaker + BlackHole) dan Aggregate
   Device (BlackHole + mic). Cari index-nya: `python3 recorder.py --list-devices`,
   isi `avfoundation_audio_device` di config (mis. `":3"`).
4. Rekam: `python3 meeting-recorder/recorder.py "Nama Meeting"`.
   Watcher: `python3 meeting-recorder/watcher.py`.

### Linux native
`ffmpeg` + PulseAudio/PipeWire; recorder otomatis pakai default sink `.monitor`
(system) + `default` source (mic), di-mix live.

## Pemakaian harian (Windows, cara termudah: GUI)

Double-click **"Record Meeting"** di Desktop (shortcut ke `gui_win.pyw`, jalan
tanpa terminal):
1. Ketik nama meeting -> **Start Recording** (window kecil always-on-top,
   timer jalan di title bar).
2. Selesai meeting -> **Stop Recording**.
3. Dengan "Auto-process after stop" tercentang (default), GUI langsung
   menjalankan `watcher.py --once` di WSL secara background: mix audio ->
   transcribe (GPU Radeon) -> MOM draft + registry + heartbeat. Log proses:
   `/tmp/meeting_watcher.log` (WSL). Tidak perlu daemon.

Daemon watcher (`python3 meeting-recorder/watcher.py`) hanya perlu kalau mau
folder dipantau terus-menerus (mis. file audio yang ditaruh manual).

**Video on-demand:** centang "Record video (screen)" di GUI, atau CLI
`recorder.py "Nama" --video` (Windows, ffmpeg gdigrab). Hasil `<base>.mp4`
tercatat sebagai `video_path` di registry entry; transcript tetap dari audio.
Untuk meeting yang You hadiri sendiri, video sudah ada di Fathom.

## Pemakaian harian (CLI)

```bash
# 1. Rekam meeting (mesin mana pun)
python(.exe) recorder.py "OC Finance Sign-off"

# 2. Watcher memproses otomatis (kalau jalan), atau manual:
python3 meeting-recorder/watcher.py --once
python3 meeting-recorder/watcher.py --file /mnt/c/Users/You/MeetingRecordings/xxx.wav

# 3. Hasil
#    Transcript : Clients/Work/meetings/transcripts/<file>.md
#    MOM draft  : Clients/Work/meetings/MOM_<slug>_<date>.md  (Status: DRAFT)
#    Registry   : journal/fathom_registry.json (recording_id "local-*")

# 4. Finalize: /mom <judul atau local-id>  → review draft-reviewer → final/GDoc
```

Transcribe manual tanpa watcher:
```bash
python3 meeting-recorder/transcribe.py --in audio.m4a --out scratch/t.md --engine cli
```

## Config (`config.json`)
- `engine`: `auto` (whispercpp→cli) | `whispercpp` | `cli` | `cpu` (manual saja)
- `language`: `auto|en|id`; meeting campur EN/ID aman di `auto`
- `gemini_model`: model untuk jalur CLI (key dipakai ulang dari skill
  `gemini-image`, **metered**; biaya ter-log di
  `dashboard-data/meeting_recorder_log.jsonl`)
- `auto_draft`: watcher langsung bikin MOM draft via agy-bridge
- `calendar_match`: cocokkan rekaman ke event kalender Work (judul meeting)
- `machines.<platform>`: path per mesin (recordings_dir, whispercpp, ffmpeg)

## Phase 2: multi-meeting bots (Vexa, self-hosted)

Bot join Meet/Teams sebagai participant ("You's Notetaker") untuk meeting yang
You tidak hadiri; bisa ~10 meeting concurrent. Transcript sudah ber-label nama
speaker asli (dari UI meeting) dan masuk pipeline yang sama (registry + MOM).

**Arsitektur:**
- Vexa Lite: container tunggal di Docker WSL (`~/tools/vexa`, API `localhost:8056`,
  dashboard `:3000`). Deploy/redeploy: `sg docker -c ~/tools/vexa/deploy_lite.sh`.
- Transcription bot = `whisper-server.exe` (Vulkan, Radeon) di Windows, port 8083,
  bind `0.0.0.0` (WAJIB -- kalau bind `127.0.0.1`, WSL/container tidak bisa lihat).
  Endpoint OpenAI-compatible (`--inference-path /v1/audio/transcriptions`), di-refer
  dari `~/tools/vexa/.env` (`TRANSCRIPTION_SERVICE_URL=http://<WSL-gateway-IP>:8083/...`).
  **Gotcha: IP gateway WSL (172.x.x.1) bisa berubah setelah reboot** -- kalau bot
  tidak menghasilkan transcript, cek `ip route show default` dan update .env +
  restart container.
- **Keep-alive (2026-07-08): `meeting-recorder/windows/whisper-keeper.ps1` +
  `install-whisper-service.ps1`.** whisper-server itu proses console biasa yang mati
  diam-diam -> setiap bot lalu menghasilkan transcript KOSONG. Startup-shortcut lama
  cuma jalan sekali saat logon (tidak recover kalau crash), dan restart via WSL
  PowerShell interop gagal kalau interop mati. Fix permanen: jalankan sekali (elevated)
  `powershell -ExecutionPolicy Bypass -File C:\tools\install-whisper-service.ps1` ->
  bikin firewall rule inbound 8083 + Scheduled Task yang cek/hidupkan whisper-server
  tiap 3 menit (crash-recovery, tidak bergantung interop). Log di `C:\tools\whisper-logs\`.
  **Timeout (bukan "connection refused") saat curl ke `<gateway>:8083` = firewall Windows
  drop paket ATAU proses mati; "refused" = host hidup tapi port tutup.**

**Pemakaian (`meeting-recorder/vexa_bots.py`):**
```bash
python3 meeting-recorder/vexa_bots.py setup            # sekali: bikin API key
python3 meeting-recorder/vexa_bots.py send --meet <url|xxx-yyyy-zzz> --title "Nama"
python3 meeting-recorder/vexa_bots.py pull --meet <id>  # transcript -> registry + MOM draft
python3 meeting-recorder/vexa_bots.py stop --meet <id>
python3 meeting-recorder/vexa_bots.py auto              # cron mode: join dari kalender + pull yang kelar
python3 meeting-recorder/vexa_bots.py auto --dry-run    # lihat keputusan join/pull tanpa kirim bot
```
`auto` men-scan kalender Work (Meet link dari `hangoutLink`/description, Teams
juga): event yang mulai dalam window -10..+3 menit di-join otomatis; meeting
selesai di-pull + diproses. **Cron sudah terpasang (2026-07-06): `*/5 * * * *`,
log `/tmp/vexa_auto.log`, heartbeat job `vexa-auto` di dashboard :3737.**

Self-healing di `auto`:
- gateway IP di-resolve live (`ip route`); kalau `TRANSCRIPTION_SERVICE_URL` di
  `~/tools/vexa/.env` drift, .env dipatch + container di-restart otomatis
- Vexa API down -> `docker start` sekali; whisper-server down -> restart via keeper
  (`C:\tools\whisper-keeper.ps1`) lewat PowerShell interop. Kalau interop mati,
  heartbeat lapor pesan ACTIONABLE (jalankan installer di Windows), bukan generik
- transcript kosong saat meeting selesai -> status `failed_empty_transcript`
  + heartbeat fail (BUKAN completed diam-diam, tidak ada file kosong ditulis)
- entry `bot_sent` yang 404 di Vexa >3 jam -> `failed_not_found` (stop retry)

Catatan compliance: bot SELALU visible di participant list. Untuk Meet di luar
domain, seseorang harus admit bot dari waiting room.
