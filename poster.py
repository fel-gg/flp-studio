"""Poster film minimalis (gaya "minimalist movie poster"): foto atau cuplikan video di kotak atas, judul besar,
tahun + jam, lalu baris running time / directed by / produced by / starring yang rata seperti tabel.
Foto -> JPG, video -> MP4 (cuplikan bergerak di kotak, kertas tetap diam).

    python poster.py foto.jpg --judul "One Day" --tahun 2026 --sutradara "Nama" --pemain "A, B"
    python poster.py video.mp4 --mulai 12 --durasi 8 --judul "Sunday Walk" --jam "16:30-18:00"
"""
import argparse
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import autoedit as ae

FONT = r"C:\Windows\Fonts\bahnschrift.ttf"  # font variabel; dipakai potongan Condensed-nya
RASIO = {"2:3": (1080, 1620), "4:5": (1080, 1350), "9:16": (1080, 1920)}
# tinggi kotak gambar sebagai pecahan tinggi poster (sisanya untuk tulisan)
KOTAK = {"2:3": 0.575, "4:5": 0.53, "9:16": 0.56}
# warna "serasi": grade foto/video supaya nyambung dengan kertas posternya (bukan seperti tempelan)
SERASI = {"kertas": "matte", "krem": "vintage", "gelap": "film"}
TEMA = {  # (kertas, tinta judul, tinta label)
    "kertas": ("#E3E0DB", (40, 40, 42), (70, 70, 72)),
    "krem": ("#EDE6D8", (52, 40, 32), (88, 74, 62)),
    "gelap": ("#1C1B1A", (236, 232, 224), (190, 186, 178)),
}


def font(ukuran, gaya):
    f = ImageFont.truetype(FONT, ukuran)
    f.set_variation_by_name(gaya)
    return f


def nama_nama(teks):
    """'A, B, C' -> ['A', 'B', 'C'] (huruf kapital seperti di poster)."""
    return [x.strip().upper() for x in str(teks or "").replace(";", ",").split(",") if x.strip()]


def durasi_teks(detik):
    if detik >= 60:
        m = round(detik / 60)
        return f"{m} MINUTE" + ("S" if m != 1 else "")
    return f"{round(detik)} SECONDS"


def lapisan_teks(data, w, h, y0, tema):
    """Gambar semua tulisan di kanvas transparan; ukuran diukur langsung dari font supaya rapi."""
    _, tinta, tinta_label = TEMA[tema]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = round(w * 0.05)
    lebar = w - 2 * m

    # judul: sebesar mungkin (maks 0.115w), dipecah jadi 2 baris kalau terlalu panjang
    judul = str(data.get("judul") or "UNTITLED").upper()
    tahun = str(data.get("tahun") or "")
    jam = str(data.get("jam") or "").strip()
    f_tahun = font(round(w * 0.042), "Regular")
    ukuran = round(w * 0.115)
    while True:
        fj = font(ukuran, "Bold Condensed")
        kata, baris = judul.split(), [""]
        for k in kata:
            coba = (baris[-1] + " " + k).strip()
            if d.textlength(coba, font=fj) <= lebar and baris[-1] or not baris[-1]:
                baris[-1] = coba
            else:
                baris.append(k)
        ekor = d.textlength(baris[-1], font=fj) + w * 0.025 + d.textlength(tahun, font=f_tahun)
        if (len(baris) <= 2 and max(d.textlength(b, font=fj) for b in baris) <= lebar) or ukuran < w * 0.06:
            break
        ukuran -= 4
    asc, desc = fj.getmetrics()
    y = y0
    for i, b in enumerate(baris):
        d.text((m - ukuran * 0.03, y), b, font=fj, fill=tinta)
        if i == len(baris) - 1 and tahun:
            x_tahun = m + d.textlength(b, font=fj) + w * 0.025
            if ekor > lebar:  # tahun tidak muat di samping judul: turun ke bawah
                x_tahun = m
            d.text((x_tahun, y + asc - f_tahun.getmetrics()[0]), tahun, font=f_tahun, fill=tinta)
            if jam:  # jam di samping tahun, sedikit lebih ringan
                f_jam = font(round(w * 0.03), "Light")
                xj = x_tahun + d.textlength(tahun, font=f_tahun) + w * 0.02
                d.text((xj, y + asc - f_jam.getmetrics()[0]), jam, font=f_jam, fill=tinta_label)
        y += round(ukuran * 0.98)
    y += round(w * 0.012)

    # baris keterangan: label kecil ringan, nilai kapital; kolom nilai rata satu garis (seperti tab di Word)
    f_label = font(round(w * 0.031), "Light SemiCondensed")
    f_nilai = font(round(w * 0.034), "SemiCondensed")
    tinggi_baris = round(w * 0.047)
    baris_info = [("running time", data.get("running_time")), ("directed by", data.get("sutradara")),
                  ("produced by", data.get("produser"))]
    baris_info = [(a, b) for a, b in baris_info if b]
    pemain = nama_nama(data.get("pemain"))
    kolom = m + max([d.textlength(a, font=f_label) for a, _ in baris_info] +
                    [d.textlength("starring", font=f_label)]) + w * 0.03

    def tulis_nilai(x, y, nilai):
        """Nama-nama dipisah spasi lebar; kalau melebihi lebar, lanjut di baris berikut pada kolom yang sama."""
        nama = nama_nama(nilai) if "," in str(nilai) else [str(nilai).upper()]
        jarak = w * 0.022
        for n in nama:
            lb = d.textlength(n, font=f_nilai)
            if x > kolom and x + lb > w - m:
                x, y = kolom, y + tinggi_baris
            d.text((x, y), n, font=f_nilai, fill=tinta)
            x += lb + jarak
        return y

    for label, nilai in baris_info:
        d.text((m, y + w * 0.003), label, font=f_label, fill=tinta_label)
        y = tulis_nilai(kolom, y, nilai) + tinggi_baris
    if pemain:
        y += round(w * 0.03)
        d.text((m, y + w * 0.003), "starring", font=f_label, fill=tinta_label)
        tulis_nilai(kolom, y, ", ".join(pemain))
    return img


def tanpa_bingkai(media, waktu, sw, sh):
    """Cari bingkai hitam bawaan (letterbox/pillarbox) dari beberapa frame; kembalikan filter crop atau ''."""
    import subprocess
    import numpy as np
    lebar = 320
    tinggi = max(2, round(lebar * sh / sw / 2) * 2)
    atas = bawah = kiri = kanan = None
    for t in waktu:
        ss = [] if ae.foto(media) else ["-ss", f"{t:.2f}"]
        r = subprocess.run(["ffmpeg", "-v", "error", *ss, "-i", str(media), "-frames:v", "1", "-vf",
                            f"scale={lebar}:{tinggi}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True, creationflags=ae.TANPA_JENDELA)
        if len(r.stdout) != lebar * tinggi:
            continue
        g = np.frombuffer(r.stdout, np.uint8).reshape(tinggi, lebar)
        baris, kolom = g.mean(1) > 10, g.mean(0) > 10
        if not baris.any() or not kolom.any():
            continue
        ys, xs = np.flatnonzero(baris), np.flatnonzero(kolom)
        # ambil yang paling longgar di antara frame (frame gelap tidak boleh membuat crop terlalu dalam)
        atas = ys[0] if atas is None else min(atas, ys[0])
        bawah = ys[-1] if bawah is None else max(bawah, ys[-1])
        kiri = xs[0] if kiri is None else min(kiri, xs[0])
        kanan = xs[-1] if kanan is None else max(kanan, xs[-1])
    if atas is None or (atas < 4 and bawah > tinggi - 5 and kiri < 4 and kanan > lebar - 5):
        return ""
    y0, y1 = (atas + 1) / tinggi, (bawah - 1) / tinggi
    x0, x1 = (kiri + 1) / lebar, (kanan - 1) / lebar
    return (f"crop=trunc(iw*{x1 - x0:.4f}/2)*2:trunc(ih*{y1 - y0:.4f}/2)*2:"
            f"trunc(iw*{x0:.4f}):trunc(ih*{y0:.4f}),")


def titik_menarik(media, waktu, sw, sh, rasio_kotak):
    """Tanpa wajah: pilih jendela crop yang paling banyak detailnya (tepi/kontras), supaya orang/objek tidak
    terpotong. Kembalikan (fx, fy) titik tengah jendela itu."""
    import subprocess
    import numpy as np
    lebar = 320
    tinggi = max(2, round(lebar * sh / sw / 2) * 2)
    energi = np.zeros((tinggi, lebar), np.float32)
    for t in waktu:
        ss = [] if ae.foto(media) else ["-ss", f"{t:.2f}"]
        r = subprocess.run(["ffmpeg", "-v", "error", *ss, "-i", str(media), "-frames:v", "1", "-vf",
                            f"scale={lebar}:{tinggi}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True, creationflags=ae.TANPA_JENDELA)
        if len(r.stdout) == lebar * tinggi:
            g = np.frombuffer(r.stdout, np.uint8).reshape(tinggi, lebar).astype(np.float32)
            energi += np.abs(np.diff(g, axis=1, prepend=g[:, :1])) + np.abs(np.diff(g, axis=0, prepend=g[:1]))
    if not energi.any():
        return 0.5, 0.5
    # lebar/tinggi jendela di sumber yang akan tampil di kotak
    jw = min(lebar, round(tinggi * rasio_kotak))
    jh = min(tinggi, round(lebar / rasio_kotak))
    kol, bar = np.convolve(energi.sum(0), np.ones(jw), "valid"), np.convolve(energi.sum(1), np.ones(jh), "valid")
    return (int(np.argmax(kol)) + jw / 2) / lebar, (int(np.argmax(bar)) + jh / 2) / tinggi


def titik_otomatis(media, waktu, sw, sh, rasio_kotak):
    """Titik crop bawaan: wajah kalau ada, kalau tidak bagian paling banyak detailnya."""
    t = waktu[len(waktu) // 2]
    wajah = ae.posisi_wajah(media, [(t, t + 0.1)], sw, sh)[0]
    if wajah != (0.5, 0.45):
        return {"x": wajah[0], "y": wajah[1]}
    fx, fy = titik_menarik(media, waktu, sw, sh, rasio_kotak)
    return {"x": fx, "y": fy}


def buat_poster(media, keluar, data, rasio="2:3", mulai=0.0, durasi=None, tema="kertas",
                warna="serasi", atur=None, crop=None, pratinjau=False):
    """crop = {"x": 0..1, "y": 0..1, "zoom": 1..3} posisi titik tengah di dalam media; kosong = otomatis
    (wajah, atau bagian paling detail). pratinjau=True: video jadi satu gambar JPG (cepat, untuk UI)."""
    media, keluar = Path(media), Path(keluar)
    w, h = RASIO[rasio]
    m = round(w * 0.05)
    kw, kh = w - 2 * m, round(h * KOTAK[rasio])
    sw, sh, total = ae.info_video(media)
    gambar = ae.foto(media)
    satu_frame = gambar or pratinjau
    if not gambar:
        durasi = min(durasi or total - mulai, total - mulai)
        data = {**data, "running_time": data.get("running_time") or durasi_teks(durasi)}
    crop = crop or {}
    waktu = [0] if gambar else [mulai + durasi * f for f in (0.2, 0.5, 0.8)]
    if "x" not in crop or "y" not in crop:
        crop = {**titik_otomatis(media, waktu, sw, sh, kw / kh), **crop}
    z = max(1.0, min(3.0, float(crop.get("zoom", 1.0))))
    # buang bingkai hitam bawaan dulu, perbesar sampai menutup kotak (x zoom), lalu potong di titik pilihan
    potong = (tanpa_bingkai(media, waktu, sw, sh) + f"scale={kw}*{z:.3f}:{kh}*{z:.3f}:force_original_aspect_ratio=increase,"
              f"crop={kw}:{kh}:'min(max(iw*{crop['x']:.3f}-{kw}/2,0),iw-{kw})':"
              f"'min(max(ih*{crop['y']:.3f}-{kh}/2,0),ih-{kh})',setsar=1")
    if warna == "serasi":
        # koreksi dulu (eksposur, white balance) lalu grade yang cocok dengan tema kertas
        grade = ae.WARNA[SERASI[tema]]
        atur = atur or ae.atur_otomatis(media)
    else:
        grade = ae.WARNA.get(warna or "asli", "null")
    tambahan = ae.atur_filter(atur or {})
    kertas = TEMA[tema][0].lstrip("#")

    with tempfile.TemporaryDirectory() as tmp:
        teks = Path(tmp) / "teks.png"
        lapisan_teks(data, w, h, m + kh + round(w * 0.035), tema).save(teks)
        # kertas: warna polos + noise sangat halus yang diam (seperti cetakan), bukan grain bergerak
        bg = f"color=c=0x{kertas}:s={w}x{h}:r=30,noise=alls=4:allf=0"
        rantai = (f"{bg}[bg];[0:v]{potong},{grade}" + (f",{tambahan}" if tambahan else "") +
                  (",fps=30" if not gambar else "") + f"[m];[bg][m]overlay={m}:{m}:shortest=1[a];"
                  f"[a][1:v]overlay=0:0,format=yuv420p[v]")
        masuk = (["-i", str(media)] if gambar else
                 ["-ss", f"{mulai + (durasi / 2 if pratinjau else 0):.3f}", "-t", f"{durasi:.3f}", "-i", str(media)])
        masuk += ["-loop", "1", "-i", str(teks)]
        if satu_frame:
            ae.jalankan(["ffmpeg", "-y", "-v", "error", *masuk, "-filter_complex", rantai, "-map", "[v]",
                         "-frames:v", "1", "-q:v", "1", "-update", "1", str(keluar)])
        else:
            audio = (["-map", "0:a?", "-af", f"afade=t=in:d=0.4,afade=t=out:st={max(0, durasi - 0.8):.2f}:d=0.8",
                      "-c:a", "aac", "-b:a", "192k"])
            ae.jalankan(["ffmpeg", "-y", "-v", "error", *masuk, "-filter_complex", rantai, "-map", "[v]", *audio,
                         "-t", f"{durasi:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                         "-movflags", "+faststart", str(keluar)])
    return keluar


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Poster film minimalis dari foto atau cuplikan video.")
    ap.add_argument("media", type=Path)
    ap.add_argument("--judul", default="")
    ap.add_argument("--tahun", default="")
    ap.add_argument("--jam", default="", help='misal "16:30 - 18:00"')
    ap.add_argument("--running-time", default="", help="kosong = dihitung dari panjang cuplikan video")
    ap.add_argument("--sutradara", default="", help="directed by; beberapa nama pisahkan koma")
    ap.add_argument("--produser", default="", help="produced by")
    ap.add_argument("--pemain", default="", help="starring")
    ap.add_argument("--rasio", choices=RASIO, default="2:3")
    ap.add_argument("--tema", choices=TEMA, default="kertas")
    ap.add_argument("--warna", choices=["serasi", *ae.WARNA], default="serasi",
                    help="serasi = otomatis disesuaikan dengan tema poster")
    ap.add_argument("--mulai", type=float, default=0.0, help="video: cuplikan mulai detik ke-")
    ap.add_argument("--durasi", type=float, help="video: panjang cuplikan (detik)")
    ap.add_argument("--crop", default="{}", help='posisi/zoom manual, misal \'{"x":0.4,"y":0.5,"zoom":1.3}\'')
    ap.add_argument("--keluar", type=Path)
    a = ap.parse_args()
    data = {"judul": a.judul, "tahun": a.tahun, "jam": a.jam, "running_time": a.running_time,
            "sutradara": a.sutradara, "produser": a.produser, "pemain": a.pemain}
    ext = ".jpg" if ae.foto(a.media) else ".mp4"
    keluar = a.keluar or a.media.with_name(a.media.stem + "_poster" + ext)
    print(buat_poster(a.media, keluar, data, a.rasio, a.mulai, a.durasi, a.tema, a.warna, None, json.loads(a.crop)))
