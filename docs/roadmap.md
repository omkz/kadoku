# Kadoku — Roadmap Implementasi MVP dalam 1 Hari (v2)

**Target:** Satu alur Kadoku yang bisa dipakai dan didemokan dari awal sampai akhir dalam **satu hari kerja (~8 jam waktu pengerjaan)**, memanfaatkan kode yang telah ada. Ini adalah **demo MVP dengan produk contoh**, bukan toko yang siap menerima pesanan atau pengiriman nyata.

**Produk yang dibangun:** Mobile-first AI gifting companion. Pengguna menceritakan calon penerima hadiah lewat **teks atau voice**, Kadoku memberikan **satu rekomendasi utama**; alternatif muncul **hanya jika diminta**. Pengguna dapat mengubah preferensi dalam chat, membuka hadiah, dan mencoba checkout di PayPal Sandbox bila kredensial tersedia.

## A. Baseline — jangan dibangun ulang

| Sudah ada di `main` | Batas saat ini |
|---|---|
| Next.js + FastAPI + PostgreSQL, Better Auth email/Google | Belum dibuktikan siap production |
| Gemini via LiteLLM untuk ekstraksi intent | Bergantung provider/key; fallback rules sudah tersedia |
| Ranking katalog sederhana, maksimal 3 rekomendasi | UI sekarang menampilkan beberapa kartu sejak awal, perlu diubah agar **satu top pick** tampil pertama |
| Percakapan multi-turn, budget/avoidance, quota | Guest 1 rekomendasi/hari; follow-up yang menghasilkan rekomendasi baru menggunakan kuota |
| Profil penerima dan ulang tahun | Belum ada reminder terjadwal |
| 12 produk **demo-only**, gift detail/note | Bukan stok/supplier sungguhan |
| Checkout PayPal Sandbox | Integrasi tersedia; hasil transaksi nyata **belum dapat diklaim** |

**PR #4 (Gemini reranking) tetap Draft dan tidak masuk scope.** Tidak membuat recommendation engine baru, embedding, vector DB, LangChain, atau fine-tuning.

## B. User journey yang HARUS bekerja

1. Pengguna membuka homepage; kolom percakapan, bukan katalog.
2. Ia mengetik/menyuarakan: **"Birthday gift for my mom, loves gardening and tea, budget $100, no plants."**
3. Gemini mengekstraksi kebutuhan. Backend memilih dari katalog sesuai budget, availability dan exclusions. **Hanya satu top pick** tampil lebih dulu dengan harga dan alasan berbasis data.
4. Pengguna meminta **"Make it cheaper"**, **"Something more personal"**, atau mengubah budget; konteks lama dipertahankan dan kendala baru diterapkan.
5. Pengguna bisa memilih **"Show alternatives"** untuk mengungkapkan paling banyak dua rekomendasi tambahan dari respons yang sudah tersedia (tidak menambah panggilan AI/kuota).
6. Pengguna membuka detail, menulis pesan hadiah, dan melihat checkout.
7. Bila PayPal Sandbox terkonfigurasi, pengguna bisa menyelesaikan transaksi menggunakan **akun test**; jika tidak, UI menjelaskan bahwa checkout belum tersedia. Tidak ada transaksi riil.

## C. Jadwal eksekusi — total 8 jam, estimasi bukan jaminan

| Waktu kerja | Prioritas | Implementasi konkret | Kriteria selesai (DoD) |
|---|---|---|---|
| **00:00–00:30** | P0 | Jalankan backend/web dari `main`, migrasi dan seed; periksa `.env` yang sudah ada tanpa menimpa key | API health OK, Next.js terbuka, 12 produk demo terbaca; catat blocker |
| **00:30–02:00** | P0 | **Perbaiki UI rekomendasi:** tampilkan **1 Top Pick** sebagai default; tombol **Show alternatives** untuk maksimal 2 produk lain; tampilkan alasan, harga, dan label demo | Satu top pick terlihat pada mobile; alternatif tersembunyi sampai diminta; tidak ada API call ekstra saat membuka alternatif |
| **02:00–03:00** | P0 | **Rapikan chat/refinement:** loading saat meminta ide, kirim pesan lanjutan tanpa kehilangan konteks, feedback jika kuota habis; voice input browser yang sudah ada tetap bekerja dengan fallback ketik | Follow-up “cheaper” mengubah hasil; budget/exclusions tetap dipatuhi; input tidak diam-diam gagal |
| **03:00–03:45** | P0 | **Gift detail:** navigasi dari top pick ke detail, pesan pribadi, kembali ke hasil chat, label sample catalog/checkout Sandbox | Detail benar, harga konsisten, catatan tidak terhapus saat bolak-balik dalam satu alur |
| **03:45–04:45** | P1 | **Checkout Sandbox:** cek create→approve→capture dengan PayPal test credentials jika ada; jika tidak ada, tampilkan unavailable tanpa klaim pembayaran berhasil | Transaksi Sandbox tercatat benar **atau** dependency kredensial ditandai belum terverifikasi |
| **04:45–06:15** | P0 | **Uji alur menyeluruh dan perbaiki blocker:** backend tests, typecheck/build frontend, guest/member quota, exclusion, ownership recipient, alur chat→gift | Tests lulus; tidak ada bug P0; bila gagal, perbaiki dan ulangi tes |
| **06:15–07:15** | P1 | **Mobile polish:** layar 375px, kartu, keyboard/input, loading/empty/error, navigasi back; tidak mendesain ulang branding | Alur bisa dipakai pada viewport 375×812 tanpa elemen penting terpotong |
| **07:15–08:00** | P0 | **Final QA + handoff:** smoke test fresh session; README langkah run; catat hasil tes, bug tersisa, demo script ringkas | Bisa didemokan ulang dari instruksi; status fitur jelas (lulus/belum diuji/blocker) |

**Jika waktu tidak cukup:** selesaikan P0 lebih dahulu. PayPal Sandbox manual dan kosmetik P1 boleh ditunda secara transparan; **jangan** mengklaim seluruh MVP terverifikasi jika checkout atau alur inti belum diuji.

## D. Bagian kode yang benar-benar dikerjakan

| Area | Lokasi sekarang | Tindakan |
|---|---|---|
| UX chat, kartu hadiah, detail | `apps/web/components/KadokuApp.tsx` | Ubah top pick jadi satu kartu utama, alternatif on-demand, perbaiki state/error |
| Styling mobile | `apps/web/app/globals.css` | Penyesuaian responsif minimum, bukan redesign |
| Pemilihan hadiah | `apps/api/app/services/gifting.py` | Tetap baseline yang ada; perbaiki **hanya** bila pengujian menemukan bug yang dapat direproduksi |
| HTTP rekomendasi | `apps/api/app/routers/gifts.py` | Tidak perlu endpoint baru kecuali terbukti diperlukan |
| Checkout | `apps/api/app/routers/` dan `apps/web/components/KadokuApp.tsx` | Verifikasi integrasi Sandbox dan error states |
| Tes | `apps/api/tests/` | Tambahkan regresi untuk bug nyata; jalankan semua test dan web build |
| Dokumentasi | `README.md`, `docs/roadmap.md` | Cara run/demo dan status akhir yang dapat diaudit |

## E. Acceptance checklist / arti kata “selesai”

- [ ] Home terasa seperti percakapan; tidak ada katalog-first.
- [ ] User bisa mengetik prompt dan voice input browser (di browser pendukung; fallback ketik bila tidak didukung).
- [ ] AI atau fallback mengekstraksi kebutuhan tanpa mengarang produk/harga.
- [ ] Satu top pick tampil pertama; maksimal dua alternatif hanya saat diminta.
- [ ] Tidak ada rekomendasi yang melanggar harga USD, stok, atau exclusions yang diuji.
- [ ] Follow-up mempertahankan konteks dan menghormati kuota harian.
- [ ] Login Google/email yang dikonfigurasi berjalan; recipient data terlindungi berdasarkan user.
- [ ] Detail hadiah, pesan, navigasi kembali berfungsi.
- [ ] PayPal **Sandbox-only** diverifikasi jika test credentials ada; jika tidak, tampilkan unavailable dan catat **belum teruji**.
- [ ] `cd apps/api && uv run --extra test pytest -q` lulus.
- [ ] `cd apps/web && pnpm typecheck && pnpm build` lulus.
- [ ] Uji manual di viewport mobile, termasuk error/loading/empty.
- [ ] Bukti pengujian, known issues, dan langkah demo tercatat.

## F. Di luar milestone ini

Tidak membuat toko produksi, katalog/stock supplier nyata, ongkir/pajak/pengiriman, refund, notifikasi birthday, AI reranker, chat history permanen, aplikasi native, atau deployment publik. Semua itu **backlog pasca-MVP** dan tidak menjadi alasan untuk menunda satu alur demo yang bekerja.

## G. Cara eksekusi dan pelaporan

1. Kerjakan urut sesuai tabel, bukan mengarang fitur baru ketika user berkata “lanjut”.
2. Setiap tahap selesai hanya setelah kriteria ujinya terbukti. Status yang sah: **DONE (teruji)**, **BLOCKED**, atau **NOT DONE**.
3. Buat perubahan kode dalam PR terfokus; periksa diff dan CI, kemudian uji manual. Jangan otomatis merge eksperimen.
4. Laporan akhir wajib berisi **commit/PR**, hasil test aktual, hasil uji pengguna, dan bagian yang belum selesai.

> **Definisi hasil akhir:** Demo Kadoku satu hari yang fokus pada **chat → satu rekomendasi → refinement → detail → Sandbox checkout (jika tersedia)**. Tidak sama dengan peluncuran toko sungguhan.
