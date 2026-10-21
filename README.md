# FLP Studio

Masukkan video, keluar video yang terasa diedit editor profesional. Untuk orang awam: tidak perlu belajar
editing.

**Edit Pro** jalan sendiri begitu video dimasukkan:
- buang jeda mati dan bagian gagal
- bingkai berganti (punch-in) setiap ~4 detik
- hook pembuka dari kalimat pertama, subtitle otomatis
- koreksi warna, musik pelan yang mengecil saat kamu bicara, suara dibersihkan dan diratakan
- video tegak otomatis 9:16 dengan wajah tetap di tengah

Setelah itu tinggal pilih **gaya sekali klik** (Bersih, Sinematik, Monokrom, Energik, Lembut) lalu **Export**.
Mau atur sendiri? Semua bisa diubah di **Full Edit**: potong, urutkan, zoom, kecepatan, efek (Blur, Monokrom,
Sepia, VHS, Glow, Cermin, Getar), transisi, teks, warna, volume, subtitle .srt, dan kirim ke CapCut sebagai draft.

Semua berjalan di komputermu. Gemini (opsional) membuat edit lebih pintar; tanpa kunci API semuanya tetap
jalan dengan versi offline.

## Pasang (Windows)

1. Pasang [Python 3.12](https://www.python.org/downloads/) dan [ffmpeg](https://www.gyan.dev/ffmpeg/builds/)
   (pastikan `ffmpeg` bisa dipanggil dari terminal).
2. Di folder ini:
   ```
   pip install -r requirements.txt
   ```
3. Jalankan **UI.bat**, atau buat aplikasi dengan ikon:
   ```
   python buat_exe.py
   ```
   lalu klik dua kali **FLPStudio.exe**.

Transkrip memakai faster-whisper. Dengan kartu NVIDIA (CUDA) jauh lebih cepat; tanpa itu tetap jalan di CPU.

## Kunci API Gemini (opsional)

Fitur Gemini (Edit Otomatis, Magic, caption pintar) meminta kunci saat dipakai. Ambil gratis di
[aistudio.google.com/apikey](https://aistudio.google.com/apikey), lalu isi di **Setelan → Kunci API Gemini**.
Kunci disimpan di komputermu (`~/.config/watch/.env`), tidak pernah ikut ke repo ini.

## Lisensi pihak ketiga

`vendor/pyJianYingDraft` berasal dari [capcut-mate](https://github.com/Hommy-master/capcut-mate)
(Apache-2.0); lihat `vendor/pyJianYingDraft/LICENSE-capcut-mate` dan `NOTICE-capcut-mate`.
Proyek ini tidak berafiliasi dengan CapCut.
