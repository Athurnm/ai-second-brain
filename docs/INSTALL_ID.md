# Panduan Instalasi AI Second Brain (Bahasa Indonesia)

> Companion untuk workshop. Ikuti berurutan dari Level 0. Level 0 saja sudah menghasilkan second brain yang bisa dipakai kerja hari ini juga. Level 1 dan 2 opsional, kerjakan setelah workshop kalau mau.
>
> Versi English lengkap: [SETUP.md](SETUP.md)

---

## Sebelum Mulai: Yang Perlu Disiapkan

| Kebutuhan | Keterangan |
| :--- | :--- |
| Laptop | Windows 10/11, macOS, atau Linux |
| Akun Claude | Langganan Claude Pro (atau Claude API key). Daftar di [claude.ai](https://claude.ai) |
| VS Code | Gratis, [code.visualstudio.com](https://code.visualstudio.com) |
| Koneksi internet | Untuk instalasi dan login |

Tidak perlu bisa coding. Kalau bisa copy-paste, bisa install ini.

---

## Level 0: Second Brain Percakapan (15 menit)

Target level ini: kamu bisa ngobrol dengan AI yang kenal kamu, gaya kerjamu, dan aturanmu, langsung di dalam editor.

### Langkah 1: Install VS Code

1. Download dari [code.visualstudio.com](https://code.visualstudio.com)
2. Install seperti aplikasi biasa, buka, selesai.

### Langkah 2: Install Claude Code

Claude Code adalah asisten AI yang jalan di terminal dan di dalam VS Code.

**Windows:**
1. Buka VS Code, lalu buka terminal (menu `Terminal > New Terminal`)
2. Install Node.js dulu kalau belum ada: download dari [nodejs.org](https://nodejs.org) (pilih LTS), install, lalu tutup dan buka lagi VS Code
3. Di terminal, jalankan:
   ```
   npm install -g @anthropic-ai/claude-code
   ```

**macOS:**
1. Buka Terminal (Cmd+Space, ketik "Terminal")
2. Jalankan:
   ```
   npm install -g @anthropic-ai/claude-code
   ```
   Kalau `npm` tidak ditemukan, install Node.js dulu dari [nodejs.org](https://nodejs.org)

### Langkah 3: Download repo ini

Di terminal:
```
git clone https://github.com/BrianArfi/ai-second-brain.git
cd ai-second-brain
```

Kalau `git` tidak ditemukan: Windows install dari [git-scm.com](https://git-scm.com), macOS jalankan `xcode-select --install`.

### Langkah 4: Jalankan installer

```
bash install.sh
```

Installer akan mengecek tools kamu, membuat file `CLAUDE.md` (otak kamu), dan menyiapkan `.env`. Aman dijalankan berulang kali.

### Langkah 5: Isi otaknya

Buka file `CLAUDE.md` di VS Code, lalu isi bagian-bagiannya:

1. **Siapa kamu**: nama, role, perusahaan/klien, bahasa kerja
2. **Konteks kerja**: proyek apa saja yang sedang jalan, siapa stakeholder-nya
3. **Aturan main**: format dokumen favorit, bahasa per klien, hal yang tidak boleh dilakukan

Ini bagian paling penting dari seluruh instalasi. Makin jujur dan spesifik isinya, makin berguna second brain kamu. Panduan menulis yang bagus ada di [CUSTOMIZING.md](CUSTOMIZING.md).

### Langkah 6: Mulai ngobrol

Di terminal, dari folder `ai-second-brain`:
```
claude
```

Login dengan akun Claude kamu saat diminta, lalu coba:
```
Baca CLAUDE.md dan perkenalkan dirimu sebagai second brain saya.
```

Lalu tes dengan kerjaan beneran:
```
Buatkan draft email untuk atasan saya tentang progress proyek X, pakai gaya bahasa saya.
```

**Selesai. Ini Level 0.** AI ini sekarang menulis dengan konteksmu, bukan jawaban generik.

---

## Level 1: Sambungkan Google (1-2 jam, setelah workshop)

Target level ini: second brain bisa membuat Google Docs asli, membaca Drive, dan mengelola kalender kamu.

Ini langkah paling teknis dari seluruh setup karena harus membuat "kunci" (OAuth credential) di Google Cloud Console. Tidak berbahaya, hanya banyak klik.

1. Buka [SETUP.md bagian 7: Google OAuth Setup](SETUP.md#7-google-oauth-setup) dan ikuti pelan-pelan
2. Intinya: buat project di Google Cloud Console, aktifkan API (Drive, Docs, Calendar, Gmail), buat OAuth Client ID tipe Desktop, download `credentials.json`
3. Taruh `credentials.json` di folder skill yang mau dipakai, jalankan skill-nya sekali, browser akan terbuka untuk login Google, selesai

Tips: kerjakan sambil santai, dan kalau macet, tanyakan langsung ke Claude Code di terminal. Tempel pesan errornya, dia yang membereskan.

## Level 2: Skill Lanjutan (opsional, sesuai kebutuhan)

Sambungkan hanya yang benar-benar kamu pakai:

| Kamu pakai... | Aktifkan skill | Panduan |
| :--- | :--- | :--- |
| Slack di kantor | `slack-connector` | [SETUP.md bagian 8](SETUP.md#8-slack-setup) |
| Meeting recorder (Fathom) | `fathom-connector` | [SETUP.md bagian 9](SETUP.md#9-other-api-keys) |
| Jira / sprint tracking | `jira-connector` | isi `token.env` dari `token.env.example` |
| Figma | `figma-connector` | [SETUP.md bagian 9](SETUP.md#9-other-api-keys) |
| Analytics (Mixpanel/Metabase) | `mixpanel-connector`, `metabase-connector` | [SETUP.md bagian 9](SETUP.md#9-other-api-keys) |

Daftar lengkap dan cara memilihnya: [SETUP.md bagian 10: Which Skills Do You Actually Need?](SETUP.md#10-which-skills-do-you-actually-need)

---

## Kalau Macet

1. **Tanya Claude Code dulu.** Serius. Tempel pesan error ke terminal `claude`, minta dia diagnosa dan perbaiki. Ini juga latihan mindset AI-Native: AI bukan cuma objek yang di-setup, dia partner yang ikut membereskan setup-nya sendiri.
2. Cek [SETUP.md bagian 13: Troubleshooting](SETUP.md#13-troubleshooting)
3. Masih macet juga: bawa ke komunitas, sertakan screenshot error dan langkah yang sudah dicoba.
