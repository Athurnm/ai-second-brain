# Talk Track: Workshop AI Second Brain (Juli 2026)

> Companion untuk `deck.html` (22 slide). Buka deck di browser, navigasi panah kiri/kanan. Durasi target: 40-50 menit materi + 45-60 menit hands-on install + Q&A.
>
> Struktur: kenalan → jualan besar (8 slide showcase + multi-agent) → mindset & arsitektur → install → benefit-cost → AI Circle → penutup.

## Slide 1: Pembuka

Selamat datang, terima kasih meluangkan waktunya. Hari ini kita gak cuma nonton demo AI. Di akhir sesi, setiap orang pulang dengan second brain yang jalan di laptopnya. Setengah pertama gw tunjukin bisa ngapain aja, setengah kedua kita install bareng.

## Slide 2: Kenalan

Dua dekade di produk. Tokopedia: optimasi OTP hemat ~$2 juta/tahun. Flip: efisiensi ~$2,12 juta/tahun. Sekarang product leader di Merit, Saudi Arabia, megang 4 tim sekaligus, plus jalanin Brobri. Poinnya: yang bikin beban 4 tim ini mungkin bukan gw kerja lebih keras, tapi satu sistem AI.

## Slide 3: Teaser "bisa ngapain aja"

Baca cepat sembilan contoh di layar. Jangan dijelasin satu-satu di sini, ini pancingan. Bilang: "sembilan ini cuma pembuka, sekarang kita lihat satu per satu." Tujuannya bikin penasaran sebelum masuk detail.

## Slide 4-11: Delapan slide showcase (JUALAN UTAMA)

Ini bagian terpenting sesi. Jualan dulu sebelum teori. Untuk tiap slide, ambil 1-2 kartu dan ceritain pengalaman nyata, jangan bacain semua kartu.

- **Slide 4 Komunikasi**: highlight Slack sweep + balas sebagai kamu (bukan bot), tekankan approval gate.
- **Slide 5 Dokumen**: highlight "edit bedah", tambah link + sisip diagram tanpa overwrite editan tangan.
- **Slide 6 Meeting**: highlight rekam lokal (gratis, tanpa Fathom) + MOM yang langsung isi to-do dengan owner.
- **Slide 7 Laporan**: highlight weekly report yang "menimbang mana yang penting, bukan yang terbaru" + dashboard hidup di localhost:3737 (buka live kalau bisa).
- **Slide 8 Data**: highlight Jira "flag kalau ada yang megang >40% tiket".
- **Slide 9 Desain**: tekankan deck yang lagi mereka lihat ini dibuat pakai sistem yang sama.
- **Slide 10 Konten & video**: JELASKAN pipeline generate-post penuh, terutama **de-AI pass** (biar gak kerasa AI: buang pola "ini bukan soal X tapi soal Y", em-dash). Lalu clipper long→shorts.
- **Slide 11 Learn & memory**: momen "aha" terbesar. Ceritakan: di ChatGPT tiap chat mulai dari nol. Di sini, kamu koreksi sekali ("jangan em-dash"), `/learn`, dan dia inget selamanya. Tunjukkan contoh nyata: aturan Slack permalink, gaya bahasa.

## Slide 12: Multi-agent

Konsep: satu perintah menggerakkan satu tim agent yang kamu pimpin. Router (kamu) bagi kerja, model murah harvest, model flagship sintesis. Lalu tunjuk kotak contoh hidup: "deck ini butuh harga 20-an tools, gw sebar 5 agent paralel barusan, kelar 2,5 menit sambil ngobrol." Ini demo meta yang selalu bikin kagum karena baru saja terjadi.

## Slide 13: Ekosistem

Pesan: yang kalian pelajari itu satu POLA, bukan satu tools. Dari pola yang sama gw turunin lamar-ai (career), wa-for-pm (WhatsApp), Brobri content engine, agy-bridge (hemat biaya). Satu pola, banyak kehidupan.

## Slide 14: Problem 70/30

Tanya audiens: seminggu berapa jam habis buat admin? Biarkan 2-3 jawab. Lalu: ~70% waktu knowledge worker habis di admin. Second brain membalik rasio itu.

## Slide 15: Mindset AI-Using vs AI-Native

Slide konsep paling penting, pelan-pelan. Tekankan kalimat kunci: bedanya bukan modelnya, modelnya bisa sama persis, bedanya sistem di sekelilingnya.

## Slide 16: Arsitektur 3 lapisan

Otak (CLAUDE.md), refleks (perintah + guardrail), tangan (konektor). Semua file lokal, open template.

## Slide 17: Safety

Singkat tapi jangan dilewat, ini pertanyaan pertama orang kantoran. Local-first, kredensial diblokir dari git, approval eksplisit, quality gate.

## Slide 18: Install Level 0 (hands-on dimulai)

Semua buka laptop. Pandu langkah 1-6, ikuti `docs/INSTALL_ID.md`. Sediakan 30-45 menit, keliling ruangan. Trik andalan: yang macet, minta dia tempel error ke Claude dan minta dibenerin, itu momen AI-Native pertama mereka.

## Slide 19: Level 1-2

Set ekspektasi: hari ini cukup Level 0. Level 1 (Google OAuth) di rumah, 1-2 jam. Level 2 pasang sesuai kebutuhan, jangan semua sekaligus.

## Slide 20: Benefit-cost (interaktif)

Centang/uncentang tools sesuai yang audiens pakai. Narasi: stack "do it all" kalau dibeli satu-satu ~$220/bln, hampir Rp 3,6 juta, dan tools-nya gak saling kenal. Yang paling mahal justru media: gambar + clipper + edit video + avatar. Dengan pola second brain: satu Claude Pro + AI Circle, semua kemampuan tadi dalam SATU konteks. Hemat ~Rp 3,1 juta/bulan. Catat: Otter dan Fireflies itu substitusi, jangan dihitung dua.

## Slide 21: AI Circle (harga asli dari brianarfi.com/ai-circle)

Nada tawaran, bukan tekanan. Repo sudah open, silakan jalan sendiri. AI Circle buat yang mau lebih cepat:
- Founding Workshop Rp 997.000 (dari Rp 2.397.000, hemat ~58%), sesi inti 12 Jul + Q&A 19 Jul, 50 kursi pertama.
- Founding Bundle (Best Value) Rp 1.387.000, workshop + 12 bulan membership, garansi uang kembali buat 10 pendaftar pertama.
- Membership: bulanan Rp 95rb, 6 bulan Rp 475rb, tahunan Rp 790rb.
Tunjukkan QR, kasih 30 detik. Positioning: "turn AI into your second brain at work."

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
