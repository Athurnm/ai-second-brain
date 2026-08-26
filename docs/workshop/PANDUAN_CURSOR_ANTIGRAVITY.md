### Setup AI Second Brain tanpa Claude Code: pakai Cursor atau Antigravity

Dokumen ini untuk kamu yang **tidak memakai Claude Code**, tapi memakai **Cursor** atau **Google Antigravity** sebagai editor AI-mu. Kabar baiknya: kamu tetap bisa memasang second brain yang sama persis. Yang berubah cuma "pintu masuknya", bukan isinya.

Baca **"Mulai Dari Sini"** lebih dulu kalau belum, untuk paham peta jalan 3 level dan filosofinya. Dokumen ini menggantikan langkah "buka terminal `claude`" dengan langkah setara di Cursor / Antigravity. Semua langkah lain (menyambung Google, Slack, Jira) sama persis, karena connector-nya adalah script yang berdiri sendiri.

Sama seperti panduan lain: kamu **tidak perlu bisa coding.** Kalau kamu bisa copy-paste dan ikut langkah, kamu bisa memasang ini.

---

## Kenapa Ini Tetap Jalan Tanpa Claude Code

Rahasianya: **second brain ini pada dasarnya cuma kumpulan file.**

- **Otaknya** adalah satu file teks berisi konteksmu dan aturanmu (di Claude Code namanya `CLAUDE.md`).
- **Tangannya** adalah folder skill (`.agent/skills/`), yang isinya script Python biasa yang dipanggil lewat terminal.
- **Perintahnya** (`/prd`, `/weekly-report`, dll) cuma file teks berisi instruksi.

Tidak ada satu pun dari itu yang terikat ke Claude Code. Editor AI apa pun yang bisa **(1) membaca file aturan** dan **(2) menjalankan perintah di terminal** bisa memakainya. Cursor bisa. Antigravity bisa.

Malah, desain repo ini sengaja mengikuti dua standar terbuka yang sekarang dipakai lintas tool:

- **`AGENTS.md`**: standar file aturan yang dibaca Cursor, Antigravity, dan hampir semua editor AI modern.
- **`SKILL.md`**: standar folder skill (satu folder = satu kemampuan), yang juga jadi format skill native Antigravity.

Artinya kamu tidak sedang "menambal" second brain agar muat di tool lain. Kamu memakainya persis sebagaimana ia dirancang: tool-agnostic sejak awal.

> **Prinsip yang sama seperti di panduan lain:** kalau macet, **tanya AI-nya**. Copy pesan error, tempel ke chat Cursor/Antigravity, minta dia perbaiki. Bedanya cuma kotak chat-nya; polanya identik.

---

## Yang Perlu Kamu Siapkan

| Kebutuhan | Keterangan | Biaya |
| :--- | :--- | :--- |
| **Laptop** | Windows 10/11, macOS, atau Linux | Sudah punya |
| **Editor AI** | **Cursor** ([cursor.com](https://cursor.com)) **atau** **Antigravity** ([antigravity.google](https://antigravity.google)). Pilih salah satu. | Ada tier gratis |
| **Akses model** | Cursor: langganan Cursor (sudah termasuk Claude/GPT/Gemini). Antigravity: login akun Google (Gemini 3, ada tier gratis). | Cursor ~$20/bln · Antigravity gratis untuk mulai |
| **Koneksi internet** | Untuk instalasi dan login | Sudah punya |
| **Akun tools yang kamu pakai** | Google, Slack, Jira: hanya yang benar-benar kamu pakai | Sudah punya |

> **Catat.** Beda dengan Claude Code (yang butuh langganan Claude), di sini "otaknya" ikut dengan editornya. Cursor sudah membawa Claude/GPT/Gemini di dalam langganannya. Antigravity membawa Gemini 3 dan bisa gratis untuk mulai. Kamu tetap merakit tools-mu sendiri dari satu langganan, cuma pintunya beda.

> **Cursor atau Antigravity?** Cursor lebih matang dan lebih banyak dipakai, bisa memilih model (Claude Sonnet/Opus, GPT, Gemini). Antigravity lebih baru, berbasis Gemini 3, dan punya "Agent Manager" untuk menjalankan banyak agent sekaligus, plus tier gratis. Untuk second brain, keduanya sama-sama sanggup. Kalau ragu: **Cursor** kalau kamu mau yang paling mulus dan bisa pakai Claude; **Antigravity** kalau kamu mau gratis dan nyaman dengan Gemini.

---

## Apa yang Sama, Apa yang Beda

Sebelum langkah teknis, kenali peta ini. Ini inti pemahamannya. Hanya baris **1-4** yang berbeda antar-tool; sisanya identik.

| Bagian | Claude Code | Cursor | Antigravity |
| :--- | :--- | :--- | :--- |
| 1. File aturan (otak) | `CLAUDE.md` | Baca `CLAUDE.md` otomatis, **atau** `AGENTS.md` | `AGENTS.md` |
| 2. Cara menyuruh AI | Terminal `claude` | Panel **Agent** (Cmd/Ctrl+I) | Panel **Agent** / Agent Manager |
| 3. Perintah (`/prd` dll) | `.claude/commands/*.md` | `.cursor/commands/*.md` | Skill / workflow, atau tempel isi file perintah |
| 4. Konfigurasi MCP | `.mcp.json` | `.cursor/mcp.json` | Pengaturan MCP Antigravity |
| 5. **Skill / connector** | `.agent/skills/*/` | **Sama persis** (script dipanggil di terminal) | **Sama persis** (bahkan native `SKILL.md`) |
| 6. **Menjalankan script** | Terminal | **Terminal bawaan** (sama) | **Terminal bawaan** (sama) |
| 7. **Menyambung Google/Slack/Jira** | Panduan Koneksi | **Identik** | **Identik** |

Perhatikan: **baris 5-7 tidak berubah sama sekali.** Semua kerja berat (bikin Google Docs, sapu Slack, baca Jira) dilakukan oleh script Python yang sama, dipanggil dari terminal yang sama. Itu sebabnya second brain ini portabel.

---

# Jalur A: Setup di Cursor

Perkiraan waktu Level 0: **15-20 menit.**

### Langkah A.1: Pasang Cursor & Ambil Repo

Unduh dan pasang Cursor dari [cursor.com](https://cursor.com), lalu login. Setelah itu ambil repo template:

```bash
git clone https://github.com/BrianArfi/ai-second-brain.git
cd ai-second-brain
bash install.sh
```

Belum punya `git`? Buka `docs/INSTALL_ID.md` di repo (ada cara pasang git untuk Windows/macOS, plus cara download ZIP tanpa git). Setelah folder-nya ada, di Cursor pilih **File → Open Folder** dan buka folder `ai-second-brain`.

### Langkah A.2: Isi Otaknya (CLAUDE.md)

Ini **langkah terpenting dari semuanya**, dan sama untuk semua tool. Buka file `CLAUDE.md` di root repo, lalu isi tiga hal dengan jujur dan spesifik:

1. **Siapa kamu**: nama, peran, perusahaan.
2. **Konteks kerjamu**: proyek yang jalan, siapa stakeholder-nya.
3. **Aturan mainmu**: format dokumen favorit, bahasa, hal yang tidak boleh dilakukan.

Makin jujur, makin berguna. Ini yang membedakan AI generik dengan partner yang benar-benar kenal kamu.

> **TIPS AI-Native.** Malas mengisi manual? Buka panel Agent Cursor dan tempel: _"Baca CLAUDE.md, lalu wawancarai aku satu per satu untuk mengisinya: siapa aku, konteks kerjaku, dan aturan mainku. Ajukan pertanyaan, lalu tuliskan jawabanku ke CLAUDE.md."_ Biarkan AI yang menyusunnya dari jawabanmu.

### Langkah A.3: Buat AGENTS.md agar Cursor Selalu Baca Otaknya

Cursor sebenarnya sudah membaca `CLAUDE.md` otomatis. Tapi agar rapi dan tahan ke depan, buat satu file `AGENTS.md` di root yang menunjuk ke sana. Di panel Agent Cursor, tempel:

```
Buat file AGENTS.md di root repo yang isinya mengarahkan agent untuk
mengikuti seluruh instruksi di CLAUDE.md sebagai sumber utama. Cukup
singkat: satu paragraf yang bilang "Ikuti semua aturan operasi di
CLAUDE.md." Jangan menduplikasi isinya.
```

Dengan begini, apa pun tool yang kamu (atau temanmu) pakai nanti akan menemukan otak yang sama.

### Langkah A.4: Cek Otaknya Hidup

Di panel Agent Cursor (buka dengan **Cmd/Ctrl + I**), pastikan modelnya di-set ke model yang kuat (Claude Sonnet atau Opus disarankan untuk kerja second brain), lalu tanya sesuatu yang hanya bisa dijawab kalau dia sudah baca otakmu:

```
Berdasarkan CLAUDE.md, siapa aku dan apa aturan utama yang harus kamu
ikuti saat membantuku? Sebutkan singkat.
```

> **CEK BERHASIL.** Cursor menjawab dengan nama, peran, dan aturanmu, bukan jawaban generik. Kalau dia menjawab generik, ingatkan: _"Baca dulu CLAUDE.md di root, lalu jawab."_

### Langkah A.5: (Opsional) Pindahkan Perintah ke Cursor

Repo punya folder `.claude/commands/` berisi perintah seperti `/prd`, `/weekly-report`, `/mom`. Cursor punya sistem serupa di `.cursor/commands/`. Untuk memindahkannya, minta AI:

```
Salin semua file dari .claude/commands/ ke .cursor/commands/ agar aku
bisa memanggilnya dengan mengetik "/" di panel Agent. Jangan ubah isinya.
```

Setelah itu, ketik `/` di panel Agent Cursor dan perintahmu muncul di dropdown. **Cara lain yang selalu bisa** (tanpa menyalin): buka file perintah misalnya `.claude/commands/prd.md`, copy isinya, tempel ke Agent sambil bilang _"Ikuti prosedur ini."_

Level 0 selesai. Lanjut ke **Level 1 & 2** di bawah untuk menyambung tools.

---

# Jalur B: Setup di Antigravity

Perkiraan waktu Level 0: **15-20 menit.**

### Langkah B.1: Pasang Antigravity & Ambil Repo

Unduh Antigravity dari [antigravity.google](https://antigravity.google) dan login dengan akun Google-mu. Antigravity adalah editor (turunan VS Code), jadi tampilannya akan familiar. Lalu ambil repo:

```bash
git clone https://github.com/BrianArfi/ai-second-brain.git
cd ai-second-brain
bash install.sh
```

Belum punya `git`? Sama seperti jalur Cursor: buka `docs/INSTALL_ID.md` untuk cara pasang atau download ZIP. Setelah folder ada, di Antigravity pilih **Open Folder** dan buka `ai-second-brain`.

### Langkah B.2: Isi Otaknya (CLAUDE.md)

Sama persis seperti Langkah A.2. Buka `CLAUDE.md`, isi siapa kamu, konteks kerjamu, dan aturan mainmu, sejujur dan sespesifik mungkin. Ini langkah paling menentukan.

> **TIPS AI-Native.** Buka panel Agent Antigravity dan tempel: _"Baca CLAUDE.md, wawancarai aku untuk mengisinya (siapa aku, konteks kerja, aturan main), lalu tulis jawabanku ke CLAUDE.md."_

### Langkah B.3: Buat AGENTS.md agar Antigravity Baca Otaknya

Antigravity membaca file aturan bernama `AGENTS.md` (sejak versi Maret 2026). Buat file itu dan arahkan ke otakmu. Di panel Agent, tempel:

```
Buat file AGENTS.md di root repo. Isinya cukup satu paragraf yang
mengarahkanmu untuk mengikuti seluruh aturan operasi di CLAUDE.md
sebagai sumber utama. Jangan menduplikasi isi CLAUDE.md, cukup
menunjuk ke sana.
```

> **PENTING.** Kalau Antigravity di komputermu juga memakai file `GEMINI.md`, `AGENTS.md` tetap dibaca. Kamu tidak perlu memilih; keduanya bisa hidup berdampingan. Yang penting `AGENTS.md` menunjuk ke `CLAUDE.md`.

### Langkah B.4: Cek Otaknya Hidup

Di panel Agent Antigravity, tanya:

```
Berdasarkan CLAUDE.md, siapa aku dan apa aturan utama yang harus kamu
ikuti? Sebutkan singkat.
```

> **CEK BERHASIL.** Antigravity menjawab dengan konteksmu sendiri, bukan jawaban generik.

### Langkah B.5: (Bonus) Skill Native Antigravity

Antigravity punya sistem **Skills** berbasis `SKILL.md`, format yang **sama** dengan folder `.agent/skills/` di repo ini. Artinya connector di repo bisa dikenali Antigravity sebagai skill langsung. Untuk memanfaatkannya, minta AI:

```
Repo ini punya folder .agent/skills/ dengan banyak SKILL.md. Perlakukan
folder-folder itu sebagai skill yang bisa kamu panggil saat relevan.
Jelaskan skill apa saja yang tersedia dan kapan kamu akan memakainya.
```

Kalaupun kamu lewati langkah ini, tidak masalah: skill tetap bisa dijalankan sebagai script terminal biasa (lihat Level 1 & 2).

Level 0 selesai. Lanjut ke **Level 1 & 2** di bawah.

---

# Level 1 & 2: Menyambung Tools (Google, Email, Slack, Jira)

**Inilah bagian yang identik untuk Cursor, Antigravity, dan Claude Code.** Semua koneksi dilakukan oleh script Python yang sama, dijalankan di **terminal bawaan editor** (di Cursor dan Antigravity: menu **Terminal → New Terminal**).

Ikuti dokumen **"Panduan Koneksi"** apa adanya, dengan **satu penyesuaian saja**:

> Setiap kali Panduan Koneksi bilang _"buka terminal `claude`"_ atau _"tempel ke Claude"_, kamu ganti dengan:
> - **Menjalankan perintah** → buka **terminal bawaan** Cursor/Antigravity (Terminal → New Terminal), tempel perintahnya, Enter. Sama persis.
> - **Bertanya / minta perbaikan** → tempel ke **panel Agent** Cursor/Antigravity, bukan ke terminal `claude`.

Contoh, saat Panduan Koneksi menyuruh menaruh `credentials.json` dan login pertama ke Google Drive, di Cursor/Antigravity kamu jalankan perintah yang sama persis di terminal bawaan:

```bash
cp ~/Downloads/credentials.json .agent/skills/work-drive-connector/credentials.json
python3 .agent/skills/work-drive-connector/gdrive_manager.py search --query "test"
```

Dan saat kamu kena error, kamu tempel errornya ke **panel Agent** (bukan terminal `claude`):

```
Aku dapat error ini waktu menyambungkan Google Drive di terminal.
Tolong diagnosa dan perbaiki, jelaskan pelan-pelan:

[tempel pesan error lengkap di sini]
```

Semua bagian Panduan Koneksi (Google, Gmail, Slack, Jira, verifikasi) berlaku tanpa perubahan lain. Kredensialmu tetap tersimpan aman di folder connector masing-masing dan tidak pernah ikut ter-upload ke GitHub.

> **CEK BERHASIL akhir.** Jalankan penyapu harian di terminal bawaan:
> ```bash
> python3 .agent/scripts/daily_update_runner.py
> ```
> Kalau ini menghasilkan ringkasan tanpa error, connector-mu hidup dan siap dipakai kerja beneran, di editor apa pun.

---

# Kalau Macet: Peta Cepat

| Gejala | Yang dilakukan |
| :--- | :--- |
| AI menjawab generik, tidak kenal aku | Ingatkan: _"Baca CLAUDE.md di root dulu, lalu jawab."_ Pastikan AGENTS.md sudah menunjuk ke CLAUDE.md. |
| Perintah `/prd` tidak muncul di Cursor | Salin `.claude/commands/` ke `.cursor/commands/`, atau tempel isi file perintahnya langsung ke Agent. |
| Antigravity tidak baca aturanku | Pastikan file `AGENTS.md` ada di root dan menunjuk ke CLAUDE.md; restart editor kalau perlu. |
| "This app isn't verified" (Google) | Wajar. Klik **Advanced → Go to (unsafe)**. Ini appmu sendiri. |
| "No module named X" (Python) | Jalankan `pip install -r requirements.txt` di terminal bawaan editor. |
| Model terasa lemah / salah | Di Cursor, ganti model ke Claude Sonnet/Opus di panel Agent. Di Antigravity, pastikan pakai Gemini 3 Pro. |
| Error apa pun yang tidak kamu paham | **Copy, tempel ke panel Agent, minta diperbaiki.** Selalu langkah pertama. |

---

## Ringkasan

Yang berubah saat pindah dari Claude Code ke Cursor/Antigravity cuma tiga hal: **pintu masuk** (panel Agent, bukan terminal `claude`), **file penunjuk aturan** (`AGENTS.md` → `CLAUDE.md`), dan **tempat perintah** (`.cursor/commands/` atau skill native). Semua kerja beratnya, seluruh connector dan otomasi, tetap sama karena mereka cuma script yang berdiri sendiri.

Itulah kekuatan sebenarnya dari second brain ini: kamu tidak terkunci ke satu tool atau satu model. Kamu memiliki otaknya (satu file konteks) dan tangannya (folder skill), dan mereka ikut ke editor mana pun yang kamu pilih hari ini atau besok.

Selamat memulai. Setelah Level 0, kamu punya partner yang menulis dengan konteksmu. Setelah menyambung tools, dia bisa bertindak untukmu, di Cursor, di Antigravity, di mana pun.

---

_Panduan Cursor & Antigravity: AI Second Brain · dibagikan untuk peserta workshop AI Circle · repo template: github.com/BrianArfi/ai-second-brain_
