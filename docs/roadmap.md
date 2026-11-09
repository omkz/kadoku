# Kadoku — Roadmap MVP 1 Hari

**Status:** Rencana eksekusi; belum dinyatakan selesai.  
**Tanggal acuan:** 9 November 2026  
**Target:** **MVP demo yang berjalan, dapat diuji ulang, dan dapat didemokan dalam satu hari kerja.** Bukan toko online produksi, tidak menjanjikan fulfillment nyata.

## 1. Scope yang dikunci

**Gunakan yang sudah ada pada `main`:**
- Next.js + FastAPI + PostgreSQL.
- Login email/Google melalui Better Auth.
- Gemini/LiteLLM untuk mengekstraksi kebutuhan hadiah; ranking dan hard filter tetap di backend.
- Sampai tiga rekomendasi dari **12 produk demo** beserta top pick dan alasan.
- Multi-turn refinement, saved recipients/birthdays, dan kuota harian.
- PayPal **Sandbox** saja, jika kredensial pengujian tersedia.

**Tidak dikerjakan dalam target satu hari:** produk/supplier nyata, fulfillment, pajak/ongkir nyata, refund, deploy produksi, mobile app native, AI reranking, embeddings, vector database, agent framework, atau sistem pengingat otomatis.

**Keputusan PR #4:** tetap Draft; **jangan di-merge** untuk milestone ini. Perubahan ranking baru memerlukan bukti peningkatan kualitas.

## 2. Urutan pengerjaan (satu hari kerja)

| Urutan | Pekerjaan | Bukti selesai |
|---|---|---|
| A. Kunci baseline | Gunakan `main`; verifikasi `.env`, migrasi, seed, dan layanan web/API | Kedua aplikasi berjalan, database tersambung, 12 produk demo tersedia |
| B. Regresi otomatis | Jalankan semua test FastAPI, TypeScript typecheck, dan build Next.js | Semua perintah selesai tanpa kegagalan |
| C. Uji alur inti | Uji guest → rekomendasi → kuota; login → rekomendasi → follow-up → pilih hadiah | Setiap alur menghasilkan respons dan status yang diharapkan |
| D. Perbaiki blocker | Hanya perbaiki bug yang menghentikan alur inti atau melanggar batas produk/harga/akses | Tidak ada blocker P0; test regresi lulus setelah perubahan |
| E. Polish minimum | Periksa satu ukuran mobile, state loading/error/empty, dan penanda produk demo | UI dapat digunakan tanpa kesalahan yang menghalangi alur |
| F. Handoff | Dokumentasi cara menjalankan, contoh percakapan, hasil tes, serta known limitations | Orang lain bisa mengulangi demo dari instruksi yang tertulis |

**Aturan timebox:** pekerjaan tambahan tidak otomatis masuk scope. Bila target terhambat, catat blocker dan kurangi scope **secara eksplisit**; jangan mengklaim fitur yang belum berhasil sebagai selesai.

## 3. Acceptance checklist — Definition of Done

- [ ] `cd apps/api && uv run --extra test pytest -q` lulus.
- [ ] `cd apps/web && pnpm typecheck && pnpm build` lulus.
- [ ] Database + Alembic + seed bisa diinisialisasi tanpa langkah tersembunyi.
- [ ] Guest menerima maksimal tiga hadiah dengan harga sesuai budget dan larangan eksplisit; panggilan kedua menerima 429 sesuai kuota.
- [ ] Login yang dikonfigurasi berhasil; pengguna terautentikasi dapat melakukan follow-up tanpa mengulang preferensi.
- [ ] User A tidak dapat membaca/mengubah recipient milik User B.
- [ ] Pilih hadiah, kembali, error/empty/loading state berfungsi di tampilan mobile.
- [ ] Tidak ada produk/harga/stock dari halusinasi model: sumbernya tetap data katalog.
- [ ] Produk diberi label **demo-only**; tidak ada klaim stock/pengiriman nyata.
- [ ] PayPal Sandbox: **jika kredensial tersedia**, uji approval dan capture dengan akun test. Jika tidak, checkout wajib menunjukkan status tidak tersedia dan dicatat **belum teruji**, bukan dianggap selesai.
- [ ] README/demo steps, hasil test, dan known issues diperbarui.

## 4. Kriteria rilis milestone

**MVP demo selesai** hanya jika seluruh checklist wajib di atas terpenuhi; checkout Sandbox boleh ditandai sebagai **integrasi belum diverifikasi** bila kredensial tidak tersedia, dan klaim demo harus menyesuaikannya. Tidak ada pembayaran produksi atau fulfillment sungguhan.

**Tidak termasuk definisi selesai:** katalog nyata, transaksi riil, deploy publik, atau AI yang terbukti lebih bagus. Keempatnya adalah milestone berikutnya, hanya setelah MVP demo stabil.

## 5. Aturan keputusan teknis

1. Mulai dari masalah/bug yang terukur; jangan menambahkan fitur baru hanya karena tersedia teknologinya.
2. Bedakan **sudah diuji**, **baru diimplementasikan**, dan **masih hipotesis**.
3. Perubahan kritis harus punya acceptance test; hasil CI bukan pengganti uji alur di browser.
4. Tidak merge PR eksperimen tanpa alasan, hasil pengujian, dan persetujuan.
5. Setelah setiap pekerjaan, laporkan bukti selesai, blocker, dan apa yang sengaja tidak dikerjakan.
