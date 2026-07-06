# Talk Track: Workshop AI Second Brain (Sabtu, 11 Juli 2026)

> Companion untuk `deck.html`. Buka deck di browser, navigasi pakai panah kiri/kanan. Durasi target: 30-40 menit materi + 45-60 menit hands-on install + Q&A.

## Slide 1: Pembuka

Selamat datang, terima kasih sudah meluangkan Sabtu-nya. Hari ini kita gak cuma nonton demo AI. Di akhir sesi, setiap orang di ruangan ini pulang dengan second brain yang jalan di laptopnya sendiri. Setengah pertama gw cerita sistemnya dan mindset-nya, setengah kedua kita install bareng, langkah demi langkah.

## Slide 2: Kenalan

Perkenalan singkat: dua dekade di produk. Di Tokopedia, optimasi OTP yang menghemat sekitar $2 juta per tahun. Di Flip, efisiensi biaya sekitar $2,12 juta per tahun. Sekarang product leader di Merit, perusahaan loyalty & rewards di Saudi Arabia, megang 4 tim produk sekaligus. Plus jalanin Brobri sebagai content creator.

Poin pentingnya bukan angkanya. Poinnya: beban kerja 4 tim lintas negara itu mustahil gw pegang sendirian dengan cara kerja lama. Yang bikin mungkin adalah sistem yang mau gw tunjukkan hari ini.

## Slide 3: Seminggu gw

Ceritakan sehari beneran, jangan teori. Jam 9 pagi briefing sudah jadi sebelum gw buka laptop: 60 channel Slack, 5 board Jira, kalender, email, semua sudah disapu. Habis meeting, transcript langsung jadi MOM lengkap dengan action item. Kamis sore, weekly report tinggal satu perintah. Tekankan: ini rutinitas harian yang jalan berbulan-bulan, bukan demo yang disiapkan semalam.

## Slide 4: Masalah 70/30

Tanya audiens dulu: seminggu, berapa jam kalian habis buat notulen, laporan, follow-up, nyari file? Biarkan 2-3 orang jawab. Lalu: riset internal gw sendiri konsisten, sekitar 70% waktu PM dan knowledge worker habis di admin. Second brain dirancang untuk membalik rasio itu.

## Slide 5: Mindset AI-Using vs AI-Native

Ini slide paling penting sesi ini, pelan-pelan di sini. AI-Using: kamu buka tab ChatGPT, tempel, salin balik. Tiap sesi mulai dari nol. AI-Native: AI hidup di dalam sistem kerjamu, punya akses ke file dan konteksmu, dan kamu tinggal minta. Perbedaannya bukan kecerdasan model. Model yang dipakai bisa sama persis. Yang beda adalah sistem di sekelilingnya: konteks, memori, akses, guardrail.

## Slide 6: Tiga lapisan

Analogi tubuh: otak (CLAUDE.md, siapa kamu dan aturan mainmu), refleks (perintah dan guardrail otomatis), tangan (konektor ke Google, Slack, kalender, recorder). Tekankan: semuanya file teks lokal di laptop sendiri. Bisa dibaca, bisa diedit, bisa dihapus. Gak ada black box.

## Slide 7: Live demo

Demo langsung dari terminal, urutan aman:
1. `claude` lalu minta dia baca CLAUDE.md dan jelaskan konteks kerjanya. Menunjukkan "dia kenal gw".
2. Lempar satu file transcript dummy ke inbox/, minta "organize my inbox".
3. Tunjukkan hasil weekly report yang sudah jadi (jangan generate live, terlalu lama; tunjukkan hasil kemarin).
4. Minta draft pesan Slack, tunjukkan bahwa dia berhenti minta approval sebelum kirim.

Backup kalau internet/demo mati: screenshot tiap langkah ada di folder ini.

## Slide 8: Ekosistem

Pesannya: yang kalian install hari ini bukan satu tools, tapi satu POLA. Begitu polanya nempel, kalian bisa menurunkan sistem lain: lamar-ai buat career, wa-for-pm buat WhatsApp, content engine buat personal brand. Semua anak dari pola yang sama: brain + refleks + tangan.

## Slide 9: Safety

Singkat tapi jangan dilewat, ini pertanyaan pertama orang kantoran: datanya aman gak? Local-first, kredensial diblokir dari git, dan aturan besinya: AI gak pernah kirim apa pun keluar tanpa approval eksplisit di terminal.

## Slide 10: Install Level 0 (hands-on dimulai)

Pindah ke mode hands-on. Semua buka laptop. Pandu langkah 1-6 di layar, ikuti `docs/INSTALL_ID.md`. Dua opsi untuk peserta: manual ikuti panduan, atau yang sudah punya Claude Code tinggal minta AI-nya sendiri yang setup. Sediakan 30-45 menit. Keliling ruangan.

Trik yang selalu berhasil: kalau ada yang macet, minta dia tempel error-nya ke Claude dan minta dibenerin. Itu momen "aha" pertama mereka sebagai AI-Native.

## Slide 11: Level 1-2

Set ekspektasi: hari ini cukup Level 0. Level 1 (Google OAuth) dikerjakan santai di rumah, 1-2 jam, panduannya lengkap. Level 2 pasang sesuai kebutuhan. Jangan pasang semua konektor sekaligus, pasang yang dipakai.

## Slide 12: Benefit-cost

Interaktif: centang/uncentang tools di kalkulator sesuai yang audiens benar-benar pakai. Narasinya: stack AI kalau dibeli satu-satu itu $85-an per bulan, hampir 1,4 juta rupiah, dan tools-nya gak saling kenal. Notulenmu gak tahu isi todo-mu. Dengan pola second brain: satu langganan Claude, semua kemampuan tadi, dalam SATU konteks yang saling nyambung. Dan tools barunya kamu rakit sendiri, gratis, tiap kali butuh.

## Slide 13: AI Circle

Nada: tawaran, bukan tekanan. Repo dan panduan sudah open, silakan jalan sendiri. AI Circle buat yang mau lebih cepat dan gak jalan sendirian: workshop 2 hari + komunitas + sesi live bulanan. Founding member 50 kursi pertama Rp 499rb, harga membership terkunci Rp 99rb selamanya. Tunjukkan QR, kasih waktu 30 detik.

## Slide 14: Penutup

Tutup dengan kalimat di layar. Lalu ajakan konkret: sebelum pulang, pastikan Level 0 kalian jalan dan CLAUDE.md sudah terisi minimal bagian "siapa kamu". Foto bareng, selesai.

---

## Checklist sebelum hari H

- [ ] Deck dibuka dan dites di laptop presentasi (arrow keys, kalkulator slide 12)
- [ ] QR code GoAkal/landing AI Circle final, ganti placeholder di slide 13
- [ ] Demo environment siap: satu transcript dummy di inbox/, hasil weekly report kemarin
- [ ] Screenshot backup tiap langkah demo
- [ ] Link repo dishare ke grup peserta sebelum sesi (biar bisa clone duluan)
- [ ] Internet backup (tethering) untuk sesi install
