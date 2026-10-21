"""Montage otomatis: banyak foto/video (satu folder liburan, jalan-jalan) -> satu reel yang dipotong mengikuti
ketukan musik. Foto diberi gerak kamera pelan (zoom), video diambil bagian paling "hidup", semua warnanya
disamakan, ada judul pembuka dan pudar di akhir.

    python montage.py folder_atau_file... [--judul "Bandung, 3 days"] [--warna senja] [--rasio 9:16]
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import autoedit as ae
import musik

FPS = 30


def bagian_hidup(video, panjang):
    """Detik mulai potongan video yang paling banyak geraknya (bukan awal yang biasanya goyang/kosong)."""
    import numpy as np
    w, h, d = ae.info_video(video)
    if d <= panjang + 0.5:
        return 0.0
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "fps=4,scale=96:-2,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True, creationflags=ae.TANPA_JENDELA)
    hh = round(96 * h / w / 2) * 2
    n = len(r.stdout) // (96 * hh)
    if n < 4:
        return 0.0
    f = np.frombuffer(r.stdout[: n * 96 * hh], np.uint8).reshape(n, hh, 96).astype(np.float32)
    gerak = np.abs(np.diff(f, axis=0)).mean((1, 2))
    k = max(1, int(panjang * 4))
    skor = np.convolve(gerak, np.ones(k), "valid")
    awal = int(0.8 * 4)  # lewati 0.8 s pertama
    i = awal + int(np.argmax(skor[awal:])) if len(skor) > awal else 0
    return min(i / 4, d - panjang)


def buat_montage(media, keluar, judul="", warna="matte", rasio="9:16", lagu=None, ketuk_per_klip=2, log=print):
    media = [Path(m) for m in media]
    w, h = ae.RASIO[rasio]
    lagu = Path(lagu) if lagu else musik.pilih("ceria")
    beat = musik.ketukan(lagu) if lagu else []
    if len(beat) < 4:
        beat = [i * 0.65 for i in range(400)]
    jarak = (beat[-1] - beat[0]) / (len(beat) - 1)
    # panjang tiap klip = ketuk_per_klip ketukan (min 1.1 s supaya tidak terlalu cepat untuk mata)
    per = max(ketuk_per_klip, round(1.1 / jarak + 0.49))
    titik = [beat[0] + i * per * jarak for i in range(len(media) + 1)]
    grade = ae.WARNA.get(warna, ae.WARNA["matte"])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        daftar = []
        for i, m in enumerate(media):
            durasi = titik[i + 1] - titik[i]
            log(f"[montage] {i + 1}/{len(media)} {m.name}")
            sw, sh, total = ae.info_video(m)
            fx, fy = ae.posisi_wajah(m, [(0, 0.1)] if ae.foto(m) else [(total / 2, total / 2 + 0.1)], sw, sh)[0]
            atur = ae.atur_filter(ae.atur_otomatis(m))
            isi_ = f"{ae.crop_ikut(w, h, fx, fy)},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
            out = tmp / f"k{i:03d}.mp4"
            if ae.foto(m):
                # gerak kamera pelan: zoom masuk/keluar bergantian, dihitung per frame dari gambar 2x
                n = round(durasi * FPS)
                arah = "1.0+0.08*on/{n}" if i % 2 == 0 else "1.08-0.08*on/{n}"
                vf = (f"{isi_},scale={w * 2}:{h * 2},zoompan=z='{arah.format(n=n)}':d={n}:"
                      f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':s={w}x{h}:fps={FPS}")
                masuk = ["-loop", "1", "-t", f"{durasi:.3f}", "-i", str(m)]
            else:
                mulai = bagian_hidup(m, durasi)
                vf = f"{isi_},fps={FPS}"
                masuk = ["-ss", f"{mulai:.3f}", "-t", f"{durasi:.3f}", "-i", str(m)]
            vf += f",setsar=1,{grade}" + (f",{atur}" if atur else "") + ",format=yuv420p"
            ae.jalankan(["ffmpeg", "-y", "-v", "error", *masuk, "-vf", vf, "-frames:v", str(round(durasi * FPS)),
                         "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", str(out)])
            daftar.append(out)
        (tmp / "daftar.txt").write_text("".join(f"file '{p.name}'\n" for p in daftar), encoding="utf-8")
        total = titik[-1] - titik[0]
        teks = ""
        if judul:  # judul pembuka (memakai gaya teks yang sama dengan editor)
            ass = tmp / "teks.ass"
            ass.write_text(ae.buat_ass([], "hangat-serif", w, h, judul, 2.5), encoding="utf-8")
            fonts = ae.FONTS_DIR.replace(":", "\\:")
            teks = f",subtitles=teks.ass:fontsdir='{fonts}'"
        masuk_lagu = ["-ss", f"{max(0, beat[0] - 0.05):.3f}", "-i", str(lagu)] if lagu else []
        audio = (["-map", "1:a", "-af", f"afade=t=in:d=0.3,afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5",
                  "-c:a", "aac", "-b:a", "192k"] if lagu else [])
        ae.jalankan(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "daftar.txt", *masuk_lagu,
                     "-map", "0:v", "-vf", f"fade=t=in:d=0.4,fade=t=out:st={max(0, total - 0.8):.3f}:d=0.8{teks}",
                     *audio, "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                     "-movflags", "+faststart", str(Path(keluar).resolve())], cwd=tmp)
    log(f"[selesai] {keluar}")
    return keluar


def kumpulkan(jalur):
    hasil = []
    for j in jalur:
        j = Path(j)
        if j.is_dir():
            hasil += sorted(f for f in j.iterdir() if f.suffix.lower() in ae.FOTO or
                            f.suffix.lower() in (".mp4", ".mov", ".m4v", ".mkv", ".webm"))
        else:
            hasil.append(j)
    return hasil


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("media", nargs="+")
    ap.add_argument("--judul", default="")
    ap.add_argument("--warna", default="matte")
    ap.add_argument("--rasio", default="9:16", choices=list(ae.RASIO))
    ap.add_argument("--lagu")
    ap.add_argument("--keluar", type=Path)
    a = ap.parse_args()
    m = kumpulkan(a.media)
    buat_montage(m, a.keluar or Path(m[0]).with_name("montage.mp4"), a.judul, a.warna, a.rasio, a.lagu)
