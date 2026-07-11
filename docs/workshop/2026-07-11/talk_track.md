# Talk Track: Workshop AI Second Brain (Juli 2026)

> Companion untuk `deck.html` (46 slide). Buka deck di browser, navigasi panah kiri/kanan. Durasi target: 90-100 menit materi + 45-60 menit install bareng + Q&A.
>
> Struktur: kenalan → jualan besar (8 slide showcase + multi-agent) → problem 70/30 → FONDASI 8 slide (apa itu AI, token, cara kerja, model-model, RAG, agentic, harness, 5 prinsip) → KAMUS 2 slide (prompt, tools, tool call, MCP, subagent, skill, slash command, memory, API key, OAuth) → mindset & arsitektur → safety → IDE vs CLI → install step-by-step bareng (6 step + pit stop) → level 1-2 → koneksi tools (Drive, Email, Slack+Jira) → benefit-cost → AI Circle → feedback → penutup.

## Slide 1: Pembuka

Selamat datang, terima kasih meluangkan waktunya. Hari ini kita gak cuma nonton demo AI. Di akhir sesi, setiap orang pulang dengan second brain yang jalan di laptopnya. Setengah pertama gw tunjukin bisa ngapain aja, setengah kedua kita install bareng.

## Slide 2: Kenalan

Dua dekade di produk. Tokopedia: optimasi OTP hemat ~$2 juta/tahun. Flip: efisiensi ~$2,12 juta/tahun. Sekarang product leader di Merit, Saudi Arabia, megang 4 tim sekaligus, plus jalanin Brobri. Poinnya: yang bikin beban 4 tim ini mungkin bukan gw kerja lebih keras, tapi satu sistem AI.

## Slide 3: Teaser "bisa ngapain aja"

Baca cepat sembilan contoh di layar. Jangan dijelasin satu-satu di sini, ini pancingan. Bilang: "sembilan ini cuma pembuka, sekarang kita lihat satu per satu." Tujuannya bikin penasaran sebelum masuk detail.

## Slide 4: Sehari-hari yang gw minta (bukti frekuensi)

Ini slide kredibilitas. Angka di layar dari log kerja nyata 6 hari terakhir: dashboard sync 62×, balas Slack 24×, doc/BRD 32×, morning + evening tiap hari, MOM tiap meeting. Pesannya: ini bukan fitur brosur, ini yang beneran gw pakai tiap hari. Boleh cerita satu contoh nyata (misal MOM meeting tadi pagi yang langsung jadi).

## Delapan slide showcase (JUALAN UTAMA)

Ini bagian terpenting sesi. Jualan dulu sebelum teori. Untuk tiap slide, ambil 1-2 kartu dan ceritain pengalaman nyata, jangan bacain semua kartu.

- **Slide 4 Komunikasi**: highlight Slack sweep + balas sebagai kamu (bukan bot), tekankan approval gate.
- **Slide 5 Dokumen**: highlight "edit bedah", tambah link + sisip diagram tanpa overwrite editan tangan.
- **Slide 6 Meeting**: highlight rekam lokal (gratis, tanpa Fathom) + MOM yang langsung isi to-do dengan owner.
- **Slide 7 Laporan**: highlight weekly report yang "menimbang mana yang penting, bukan yang terbaru" + dashboard hidup di localhost:3737 (buka live kalau bisa).
- **Slide 8 Data**: highlight Jira "flag kalau ada yang megang >40% tiket".
- **Slide 9 Desain**: tekankan deck yang lagi mereka lihat ini dibuat pakai sistem yang sama.
- **Slide 10 Konten & video**: JELASKAN pipeline generate-post penuh, terutama **de-AI pass** (biar gak kerasa AI: buang pola "ini bukan soal X tapi soal Y", em-dash). Lalu clipper long→shorts.
- **Slide Konten & video**: JELASKAN pipeline generate-post penuh, terutama **de-AI pass**.

## Slide studi kasus: Content Distribution Engine (setelah Konten & video)

Slide paling "wow" buat audiens creator/marketing. Ceritakan flow nyata konten gw: rekam video → `video-suite` edit otomatis (skor viral, potong, subtitle, closing screen) → bilang "gas" → auto-upload YouTube Shorts + IG Reels (native, ada bukti post minggu ini) + LinkedIn/FB via Repliz → post WA Channel → auto-forward ke grup WA. Tekankan JUJUR: WA Story masih difinalisasi, jangan diklaim jalan. Angle jualan: yang biasanya makan setengah hari editing + posting manual, kelar sambil ngopi. Ini bukti pola second brain bisa dipakai buat hidup content creator, bukan cuma kerjaan kantor.

- **Slide Learn & memory**: momen "aha" terbesar. Ceritakan: di ChatGPT tiap chat mulai dari nol. Di sini, kamu koreksi sekali ("jangan em-dash"), `/learn`, dan dia inget selamanya. Tunjukkan contoh nyata: aturan Slack permalink, gaya bahasa.

## Slide 12: Multi-agent

Konsep: satu perintah menggerakkan satu tim agent yang kamu pimpin. Router (kamu) bagi kerja, model murah harvest, model flagship sintesis. Lalu bawakan kotak contoh nyata weekly report Senin pagi: satu perintah, 4 agent nyebar (kalender+notulen, Slack, Jira, email), flagship nimbang dan nulis, kerjaan 1-2 jam jadi ±10 menit review. Ceritakan sebagai rutinitasmu beneran, sebut angka dari pengalaman. Kalau mau efek "wow" tambahan, boleh tambah lisan: deck yang mereka tonton juga disusun dengan pola yang sama (risetnya disebar ke beberapa agent paralel), tanpa perlu ngaku-ngaku "barusan".

## Slide 13: Ekosistem

Pesan: yang kalian pelajari itu satu POLA, bukan satu tools. Dari pola yang sama gw turunin lamar-ai (career), wa-for-pm (WhatsApp), Brobri content engine, agy-bridge (hemat biaya). Satu pola, banyak kehidupan.

## Slide 14: Problem 70/30

Tanya audiens: seminggu berapa jam habis buat admin? Biarkan 2-3 jawab. Lalu: ~70% waktu knowledge worker habis di admin. Second brain membalik rasio itu.

## Blok Fondasi (8 slide, setelah Problem 70/30)

Ini blok "kuliah 12-15 menit" yang bikin peserta gak cuma ikut-ikutan istilah. Bawakan santai, banyak analogi, nol matematika. Intinya disarikan dari 4 sumber populer: Google AI Essentials, Generative AI for Everyone (Andrew Ng), Co-Intelligence (Ethan Mollick), Building Effective Agents (Anthropic). Sebut sumbernya sekali di slide prinsip, itu nambah kredibilitas.

- **Apa itu AI (1/8)**: LLM = mesin nebak kata berikutnya hasil baca triliunan kata. Analogi kunci: karyawan baru yang sudah baca seisi internet tapi nol soal kamu. Tutup dengan: "hari ini kita benerin bagian 'nol soal kamu'-nya."
- **Token (2/8)**: token = potongan kata; 1.000 token kira-kira 700 kata. SEMUA diukur pakai token: harga, context window, kecepatan. Analogi meteran listrik / kWh. Praktisnya: lampiran panjang = mahal + meja penuh; ringkas dan relevan itu strategi. Pancing audiens: "pernah ngerasa ChatGPT makin ngaco di chat yang panjang banget? Itu mejanya penuh."
- **Cara kerja (3/8)**: tekankan CONTEXT WINDOW sebagai meja kerja. Tiga konsekuensi praktis: konteks bagus = jawaban bagus; chat baru = meja kosong (kenapa ChatGPT "lupa"); halusinasi = ngarang pede kalau gak dikasih sumber. Landing: second brain = mesin penyaji konteks ke meja itu.
- **Model-model AI (4/8)**: tiga keluarga (Claude, GPT, Gemini) + open-source (Llama, GLM, Qwen). Tier flagship vs kecil-murah. Cerita nyata: sistem gw pakai flagship buat mikir, model murah buat harvest. Punchline WAJIB digantung: "semua orang bisa langganan model yang sama, jadi pembedanya bukan modelnya. Lalu apa?"
- **RAG (5/8)**: jawaban pertama atas "AI gak tahu data kantormu": buka contekan dulu sebelum jawab. Tiga langkah di layar: cari potongan relevan dari gudang dokumen → taruh di meja → jawab grounded sambil nunjuk sumber. Contoh kantoran: tanya aturan cuti, dijawab dari PDF HR. Tekankan batasnya keras-keras: RAG cuma MENJAWAB, gak bisa bales email atau update sheet. Gantung: "buat mengerjakan, butuh konsep berikutnya."
- **Agentic (6/8)**: definisi Anthropic disederhanakan: model yang memakai tools dalam sebuah loop. Bawakan loop-nya pelan-pelan: tujuan (kamu kasih hasil akhir) → rencana + aksi pakai tools → cek hasil NYATA tiap langkah, bukan nebak → koreksi sampai beres, lapor. Analogi penutup wajib diucapkan: chatbot ngasih resep, RAG ngasih resep dari buku dapurmu, agent MASAK, nyicip, dan lapor makanannya sudah di meja. Landing: second brain kita = agentic + gudang konteks lokal, dua-duanya sekaligus.
- **Harness (7/8)**: jawab gantungan tadi. Definisikan sekali, pakai istilahnya terus sepanjang sesi: model = mesin, harness = mobil lengkapnya (tools + file + memory + guardrail); loop agentic tadi hidupnya di dalam harness. ChatGPT web vs Claude Code = dua harness beda buat model sekelas. Ini yang bikin slide Mindset berikutnya nampol.
- **Lima prinsip (8/8)**: slide "pegangan pulang". (1) Selalu ajak AI ke meja, kemampuannya jagged, satu-satunya cara tahu petanya ya dicoba; (2) kamu human in the loop: AI draft, kamu keputusan, verifikasi sebelum kirim; (3) perlakukan kayak orang + kasih peran; (4) konteks menentukan kualitas, spesifik soal tujuan-format-contoh; (5) anggap ini AI terburuk yang akan pernah kamu pakai, skill dan sistemmu yang compounding. Kalau peserta cuma ingat satu blok, harusnya blok ini.

## Blok Kamus Kecil (2 slide, setelah 5 prinsip)

Sepuluh istilah yang PASTI mereka temui: di layar Claude Code, pas install, dan tiap kali kamu ngomong. Jangan dibacain datar; tiap istilah punya analogi, ucapkan analoginya, bukan definisinya.

- **Kamus 1/2 (ngobrol sama AI)**: prompt = nge-brief desainer; tools = tangan-nya AI; tool call = satu kali mencet tombol (kalau layar bilang "calling tool...", dia lagi kerja, bukan mikir); MCP = colokan USB-C universal buat nyambungin aplikasi; subagent = anak buah sekali-tugas yang kerja di ruangan terpisah. Tips panggung: pas demo nanti, tunjuk layar tiap ada tool call: "tuh, itu yang tadi gw bilang".
- **Kamus 2/2 (ingatan + kunci)**: skill = SOP di binder kantor; slash command = speed dial-nya; memory = laci catatan permanen (kontraskan dengan meja/context window yang dikosongin tiap sesi, sambungkan ke slide /learn tadi); API key = kartu akses gedung (jangan difoto, jangan dibagikan); OAuth = surat kuasa resmi yang bisa dicabut. Tutup dengan: "dua istilah terakhir bakal kalian pakai sendiri pas nyambungin Google di rumah."

## Slide 15: Mindset AI-Using vs AI-Native

Slide konsep paling penting, pelan-pelan. Tekankan kalimat kunci: bedanya bukan modelnya, modelnya bisa sama persis, bedanya sistem di sekelilingnya.

## Slide 16: Arsitektur 3 lapisan

Otak (CLAUDE.md), refleks (perintah + guardrail), tangan (konektor). Semua file lokal, open template.

## Slide 17: Safety

Singkat tapi jangan dilewat, ini pertanyaan pertama orang kantoran. Local-first, kredensial diblokir dari git, approval eksplisit, quality gate.

## Slide IDE vs CLI (sebelum blok install)

Satu menit, orientasi alat. Buka VS Code beneran di layar sambil nunjuk tiga area: file kiri, editor tengah, terminal bawah. Kalimat penenang buat non-programmer: "hari ini cuma ±5 perintah, semuanya copy-paste."

## Blok Install bareng (peta + 6 step + pit stop)

Semua buka laptop. Satu slide = satu langkah, jangan lompat. Sediakan 45-60 menit total, keliling ruangan.

- **Peta (15 menit menuju second brain)**: set ekspektasi: 15-30 menit tergantung WiFi. Minta semua buka laptop SEKARANG, jangan nunggu.
- **Step 1 (VS Code + Node)**: korban terbanyak di sini: install Node tapi lupa restart VS Code. Sukses = `node --version` keluar angka.
- **Step 2 (Claude Code)**: `npm install -g`. Sukses = `claude --version`.
- **Step 3 (repo)**: yang gak punya git langsung arahkan jalur ZIP, jangan buang waktu install git di tempat. Sukses = terminal berdiri di folder `ai-second-brain`.
- **Step 4 (install.sh)**: dua centang. Yang error, simpan error-nya buat latihan di pit stop.
- **Step 5 (CLAUDE.md)**: kasih waktu PALING LAMA di sini, 10 menit, keliling. Ini nilai workshop yang sebenarnya: isian jujur = second brain berguna. Tunjukin contoh isian di layar.
- **Step 6 (nyalakan + ngobrol)**: login, prompt perkenalan, lalu tes kerjaan nyata. Momen wow massal: minta 2-3 orang bacain keras-keras jawaban AI-nya yang nyebut detail CLAUDE.md mereka.
- **Pit stop**: urutan resmi kalau macet: tempel error ke Claude → INSTALL_ID.md → angkat tangan. Sebut error paling umum (npm not found, git not found, login gagal).

## Slide 19: Level 1-2

Set ekspektasi: hari ini cukup Level 0. Level 1 (Google OAuth) di rumah, 1-2 jam. Level 2 pasang sesuai kebutuhan, jangan semua sekaligus. Lalu masuk 3 slide koneksi.

## Blok Sambungkan Tools (3 slide: Google Drive, Email, Slack+Jira)

Tujuannya bukan dikerjain di tempat, tapi biar KEBAYANG dan gak takut nyoba di rumah. Bawakan sebagai "gambaran besar 4 langkah", jangan baris-per-baris.

- **Google Drive (1/3)**: akui jujur ini langkah paling teknis dari seluruh setup, tapi sekali seumur hidup. 4 langkah besar: proyek Cloud → enable API → consent + credential Desktop app → taruh file + login pertama. Wanti-wanti dua jebakan: layar "unsafe" (normal, Advanced → lanjut) dan email harus masuk test users.
- **Email (2/3)**: kabar baiknya numpang OAuth yang sama, gak ada proyek baru. Tekankan guardrail: AI gak pernah kirim email tanpa approval.
- **Slack + Jira (3/3)**: Slack = bikin app + salin token, 10-15 menit. User token berarti AI bertindak sebagai kamu (bukan bot yang harus di-invite). Jira sebut sekilas: Atlassian API token + minta Claude arahkan ke board-mu. Tutup blok dengan: "semua ini ada panduan visualnya, langkah demi langkah dengan gambar, dikirim ke yang isi feedback."

## Slide 20: Benefit-cost (interaktif)

Centang/uncentang tools sesuai yang audiens pakai. Narasi: stack "do it all" kalau dibeli satu-satu ~$220/bln, hampir Rp 3,6 juta, dan tools-nya gak saling kenal. Yang paling mahal justru media: gambar + clipper + edit video + avatar. Dengan pola second brain: satu Claude Pro + AI Circle, semua kemampuan tadi dalam SATU konteks. Hemat ~Rp 3,1 juta/bulan. Catat: Otter dan Fireflies itu substitusi, jangan dihitung dua.

## Slide 21: AI Circle (harga asli dari brianarfi.com/ai-circle)

Nada tawaran, bukan tekanan. Repo sudah open, silakan jalan sendiri. AI Circle buat yang mau lebih cepat:
- Founding Workshop Rp 997.000 (dari Rp 2.397.000, hemat ~58%), sesi inti 12 Jul + Q&A 19 Jul, 50 kursi pertama.
- Founding Bundle (Best Value) Rp 1.387.000, workshop + 12 bulan membership, garansi uang kembali buat 10 pendaftar pertama.
- Membership: bulanan Rp 95rb, 6 bulan Rp 475rb, tahunan Rp 790rb.
Tunjukkan QR, kasih 30 detik. Positioning: "turn AI into your second brain at work."

## Slide Feedback: Isi feedback, dapat Panduan Koneksi (sebelum Penutup)

Momen tukar nilai, bukan jualan. Sampaikan tiga aksi konkret sebelum pulang: (1) pastikan Level 0 jalan, (2) isi feedback workshop di Goakal, (3) yang isi feedback gw kirimin Panduan Koneksi lengkap. Jelaskan isi guide-nya singkat: cara nyambungin Google Drive, Email, Slack, Jira satu per satu, visual dengan diagram tiap langkah, plus dokumen "Mulai Dari Sini". Drop link feedback Goakal live di grup Telegram AI Circle saat slide ini tampil. Framing: "2 menit feedback kalian bikin batch berikutnya lebih bagus, dan kalian dapat panduan lengkap buat lanjut sendiri di rumah." Jangan bikin terasa transaksional dingin; ini genuine give.

## Slide 22: Penutup

Tutup dengan kalimat di layar. Ajakan konkret: sebelum pulang, pastikan Level 0 jalan dan CLAUDE.md terisi minimal "siapa kamu". Foto bareng, selesai.

---

## Checklist sebelum hari H

- [ ] Deck dites di laptop presentasi (arrow keys + kalkulator slide 20)
- [ ] QR code brianarfi.com/ai-circle final di slide 21
- [ ] Cek ulang tanggal: deck pakai "Juli 2026" netral; slide AI Circle pakai 12 Jul (sesi inti) + 19 Jul (Q&A) sesuai halaman. Sesuaikan kalau tanggal live workshop beda.
- [ ] Demo environment: transcript dummy di inbox/, hasil weekly report kemarin, dashboard localhost:3737 nyala
- [ ] Screenshot backup tiap langkah demo (kalau internet mati)
- [ ] Link repo dishare ke grup peserta sebelum sesi (biar bisa clone duluan)
- [ ] Internet backup (tethering) buat sesi install
- [ ] Link feedback Goakal siap di-drop ke grup Telegram saat slide Feedback tampil
- [ ] Panduan Koneksi + Mulai Dari Sini (GDoc + PDF) siap kirim ke peserta yang isi feedback
