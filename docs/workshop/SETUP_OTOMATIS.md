### Biarkan AI yang Memasang: setup nyaris tanpa tangan

Panduan lain (**Mulai Dari Sini**, **Panduan Koneksi**, **Panduan Cursor & Antigravity**) menuntunmu memasang second brain langkah demi langkah dengan tanganmu sendiri. Dokumen ini menawarkan jalan yang lebih malas dan lebih cepat: **serahkan sebagian besar pekerjaannya ke AI.**

Idenya sederhana. Repo ini sudah berisi satu file bernama `SETUP_AGENT.md`, yaitu **buku panduan untuk AI-nya**, bukan untukmu. Kamu tinggal menyuruh AI membacanya dan menjalankannya. AI yang mewawancaraimu, mengisi file konteksmu, membuat file aturan, dan menyambungkan tools. Tugasmu menyusut jadi empat hal saja.

Ini bekerja di **Cursor**, **Antigravity**, maupun **Claude Code**. Kamu tetap **tidak perlu bisa coding.**

---

## Pembagian Kerja: Kamu vs AI

| Yang **kamu** lakukan (4 hal) | Yang **AI** lakukan (sisanya) |
| :--- | :--- |
| 1. Pasang editor & buka repo | Cek kondisi repo, jalankan `install.sh` kalau perlu |
| 2. Tempel satu kalimat perintah | Baca `SETUP_AGENT.md`, mewawancaraimu satu per satu |
| 3. Jawab pertanyaannya (siapa kamu, kerjamu, aturanmu) | Menyusun & menulis `CLAUDE.md` dan `AGENTS.md` |
| 4. Klik layar login Google/Slack saat diminta | Membuat file, menjalankan test, membaca error, memperbaikinya |

Tiga hal yang **tetap butuh kamu**, dan memang tidak bisa didelegasikan: **keputusan** (siapa kamu, aturan mainmu), **rahasia** (token/password, yang kamu masukkan langsung ke file atau browser, bukan ke chat), dan **klik login** di layar Google atau Slack. Selebihnya AI yang urus.

---

## Yang Perlu Kamu Siapkan

Sama seperti panduan lain: laptop, salah satu editor AI (**Cursor**, **Antigravity**, atau **Claude Code**), koneksi internet, dan akun tools yang benar-benar kamu pakai. Kalau belum tahu memilih editor yang mana, baca dulu **Panduan Cursor & Antigravity**, bagian "Cursor atau Antigravity?".

---

## Langkah 1: Pasang Editor & Buka Repo

Pasang editor pilihanmu, lalu ambil repo template:

```bash
git clone https://github.com/BrianArfi/ai-second-brain.git
cd ai-second-brain
bash install.sh
```

Belum punya `git`, atau lebih nyaman lewat ZIP? Buka `docs/INSTALL_ID.md` di repo, semuanya ada di sana. Setelah folder-nya ada, buka folder `ai-second-brain` itu di editormu (**File → Open Folder**).

> **TIPS.** Kalau `install.sh` bikin bingung, lewati saja. Nanti di Langkah 2, AI akan mengeceknya dan menjalankannya sendiri kalau memang belum jalan.

---

## Langkah 2: Suruh AI Membaca Buku Panduannya

Buka panel Agent editormu (di Cursor: **Cmd/Ctrl + I**; di Antigravity: panel Agent; di Claude Code: terminal `claude`). Lalu tempel **satu kalimat ini**:

```
Baca file SETUP_AGENT.md di root repo ini, lalu jalankan langkah-langkahnya
untuk membantuku memasang AI Second Brain-ku. Ajak aku ngobrol dalam Bahasa
Indonesia, satu pertanyaan sekelompok, jangan sekaligus.
```

Itu saja. AI akan membuka buku panduannya dan mulai memandumu.

> **PENTING.** Di Cursor, pastikan model di panel Agent di-set ke yang kuat (**Claude Sonnet** atau **Opus** disarankan). Di Antigravity, pastikan **Gemini 3 Pro**. Setup melibatkan membaca file dan menjalankan perintah, jadi model yang lemah akan lebih sering tersendat.

---

## Langkah 3: Jawab Pertanyaan AI

AI akan mewawancaraimu pelan-pelan, satu topik demi satu topik: siapa kamu, konteks kerjamu, rekam jejakmu, pekerjaan rutin yang mau kamu lepas, lalu aturan main dan pagar pengamanmu. Jawab sejujur dan sespesifik mungkin. Ini bagian yang **cuma bisa kamu** yang isi, dan justru bagian yang membuat second brain-mu benar-benar mengenalmu.

Kalau ada yang belum kamu tahu, bilang saja "belum tahu" atau "lewati dulu". AI akan menandainya `TODO` dan kamu bisa mengisinya nanti. Jangan biarkan AI menebak nama klien atau angka, koreksi kalau dia mulai mengarang.

> **CEK BERHASIL.** AI menunjukkan draft `CLAUDE.md`-mu dan meminta persetujuan sebelum menyimpannya. Baca sekilas, kalau sudah pas, bilang setuju. Dia lalu menulis `CLAUDE.md` dan `AGENTS.md` untukmu.

---

## Langkah 4: Klik Login Saat Diminta (Menyambung Tools)

Kalau kamu mau second brain-mu bisa membuat Google Docs, menyapu Slack, atau membaca Jira, AI akan memandumu menyambungkannya. Di sini muncul satu-satunya hal teknis yang **harus kamu** lakukan: **membuka layar login Google/Slack di browser dan mengizinkan aksesnya.**

AI yang menyiapkan semua file dan menjalankan perintahnya; kamu yang klik "Allow" dan menyalin apa yang dia minta **ke file atau ke browser, bukan ke kotak chat**. Kalau ada error, biarkan AI yang membacanya dan memperbaikinya. Ingat aturan emas: **kalau macet, biar AI yang benerin.**

> **PENTING soal rahasia.** AI tidak akan pernah, dan tidak boleh, memintamu menempelkan token atau password ke dalam chat. Rahasia selalu masuk langsung ke filenya sendiri. Kalau AI meminta token di chat, tolak dan minta dia memandumu menyimpannya ke file.

Tidak semua tools harus disambung sekarang. Bilang saja tool mana yang kamu pakai; sisanya bisa menyusul kapan saja dengan meminta AI "lanjutkan setup".

---

## Selesai

Setelah ini kamu punya second brain yang mengenalmu (`CLAUDE.md` terisi), portabel ke editor mana pun (`AGENTS.md` menunjuk ke sana), dan tersambung ke tools yang kamu pilih, semuanya dirakit oleh AI dengan kamu cukup mengarahkan.

Mau lebih paham apa yang terjadi di balik layar, atau lebih suka memasang dengan tanganmu sendiri? Baca **Panduan Cursor & Antigravity** (langkah manual) dan **Panduan Koneksi** (detail tiap tool). Dokumen ini adalah jalan cepatnya; keduanya adalah peta lengkapnya.

---

_Setup Otomatis: AI Second Brain · dibagikan untuk peserta workshop AI Circle · repo template: github.com/BrianArfi/ai-second-brain_
