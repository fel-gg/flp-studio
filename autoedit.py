"""Editor otomatis: video mentah masuk, video siap upload keluar.

Alur: transkrip (faster-whisper) -> potong bagian hening -> reframe ke 9:16
-> color grade -> teks otomatis sesuai gaya -> hook di awal -> render.

Contoh:
    python autoedit.py video.mp4
    python autoedit.py video.mp4 --gaya bold --hook "3 hal yang aku pelajari minggu ini"
    python autoedit.py video.mp4 --gaya pop --hook auto --rasio 4:5
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import peningkat

HERE = Path(__file__).resolve().parent
MODEL_DIR = os.environ.get("AUTOEDIT_MODEL_DIR", "D:/vidio/tm-teks/model")
FONTS_DIR = "C:/Windows/Fonts"
# jangan munculkan jendela console untuk ffmpeg saat dijalankan dari UI (pythonw)
TANPA_JENDELA = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# Warna ASS: &HAABBGGRR
PUTIH = "&H00FFFFFF"
HITAM = "&H00000000"
MINT = "&H00C4F29D"    # hijau mint, dari video "COLOR"
UNGU = "&H00E02B6A"    # ungu highlight, dari video tutorial DaVinci
KREM = "&H00E6F2FF"    # krem hangat #FFF2E6
KUNING = "&H0066CFF2"  # kuning hangat #F2CF66, seperti subtitle "My Creative Process"
COKLAT = "&H70203048"  # coklat tua transparan, glow di belakang teks

# Kata pengisi yang tidak ditampilkan sebagai teks
PENGISI = re.compile(r"^(um+|uh+|uhm+|er+|erm+|eh+|em+|ehm+|hmm+|mm+|ah+|anu)[.,!?]*$", re.I)

# Grade hangat: highlight & kulit hangat, bayangan tetap netral sedikit dingin. Bayangan yang ikut
# dihangatkan jadi coklat/zaitun "butek", warna yang paling tidak disukai (Palmer & Schloss 2010).
# Geser warnanya kecil saja: kulit paling cepat terlihat salah kalau hue-nya bergeser.
GRADE_HANGAT = ("curves=all='0/0.04 0.5/0.52 1/0.97',"
                "colorbalance=rs=-0.01:bs=0.02:rm=0.03:gm=0.005:bm=-0.025:rh=0.05:gh=0.01:bh=-0.05,"
                "eq=saturation=1.04:contrast=1.04,vignette=PI/6")

# Grain film sangat halus: ada di 96% reels estetik yang dianalisis. Halus supaya file tidak membengkak.
GRAIN = "noise=c0s=5:c0f=t+u"

# Preset color grading, bisa dipilih terpisah dari gaya teks dengan --warna.
WARNA = {
    "asli": "null",  # tanpa grade
    # monokrom: warna dibuang lewat channel mixer (kulit tetap terang seperti filter merah film hitam-putih),
    # lalu kurva S. Varian: lembut (hitam pudar), hangat (selenium/sepia), dingin (cyanotype), grain film.
    "monokrom": ("colorchannelmixer=.40:.45:.15:0:.40:.45:.15:0:.40:.45:.15,"
                 "curves=all='0/0.02 0.25/0.2 0.5/0.5 0.75/0.8 1/0.98',eq=contrast=1.06,vignette=PI/5"),
    "monokrom-lembut": ("colorchannelmixer=.40:.45:.15:0:.40:.45:.15:0:.40:.45:.15,"
                        "curves=all='0/0.1 0.3/0.32 0.7/0.72 1/0.92',eq=contrast=0.98"),
    "monokrom-hangat": ("colorchannelmixer=.40:.45:.15:0:.40:.45:.15:0:.40:.45:.15,"
                        "colorbalance=rs=0.06:gs=0.02:bs=-0.05:rm=0.07:gm=0.03:bm=-0.07:rh=0.03:bh=-0.04,"
                        "curves=all='0/0.05 0.5/0.52 1/0.96',vignette=PI/5"),
    "monokrom-dingin": ("colorchannelmixer=.40:.45:.15:0:.40:.45:.15:0:.40:.45:.15,"
                        "colorbalance=rs=-0.05:bs=0.07:rm=-0.03:bm=0.05:bh=0.02,"
                        "curves=all='0/0.03 0.4/0.36 1/0.96',eq=contrast=1.05"),
    "monokrom-film": ("colorchannelmixer=.40:.45:.15:0:.40:.45:.15:0:.40:.45:.15,"
                      "curves=all='0/0.04 0.25/0.18 0.5/0.5 0.75/0.82 1/0.97',eq=contrast=1.1,"
                      "noise=alls=10:allf=t,vignette=PI/4.5"),
    "natural": "eq=contrast=1.03:saturation=1.05",  # hanya dirapikan sedikit
    "hangat": GRADE_HANGAT,  # warm aesthetic halus (default gaya hangat)
    # sore keemasan: seluruh gambar lebih oranye-kuning, lebih berwarna
    "golden": ("colorbalance=rs=0.02:bs=-0.03:rm=0.06:gm=0.02:bm=-0.06:rh=0.07:gh=0.03:bh=-0.08,"
               "curves=all='0/0.02 0.5/0.53 1/0.98',eq=saturation=1.1:contrast=1.03,vignette=PI/5"),
    # film pudar: hitam diangkat, putih diturunkan, warna kalem
    "film": ("curves=all='0/0.08 0.25/0.26 0.75/0.76 1/0.93',"
             "colorbalance=rs=-0.02:gs=0.01:bs=0.03:rm=0.02:bm=-0.02:rh=0.03:bh=-0.03,"
             "eq=saturation=0.88:contrast=1.02,vignette=PI/6"),
    # teal & orange ala film: bayangan kebiruan, kulit tetap hangat
    "sinematik": ("colorbalance=rs=-0.06:gs=-0.01:bs=0.07:rm=0.03:bm=-0.02:rh=0.05:gh=0.01:bh=-0.05,"
                  "curves=all='0/0.02 0.3/0.27 0.7/0.73 1/0.97',eq=saturation=1.06:contrast=1.05,"
                  "vignette=PI/5"),
    # terang & lembut (bright and airy): lebih terang, kontras rendah, sedikit pastel
    "terang": ("curves=all='0/0.07 0.5/0.58 1/1',"
               "colorbalance=rs=-0.01:bs=0.01:rh=0.02:bh=-0.01,eq=saturation=0.92:contrast=0.96"),
    # gelap & dingin: bayangan dalam kebiruan, warna diredam
    "moody": ("curves=all='0/0 0.4/0.33 1/0.94',"
              "colorbalance=rs=-0.04:bs=0.06:rm=-0.01:bm=0.02:rh=0.04:bh=-0.03,"
              "eq=saturation=0.85:contrast=1.08,vignette=PI/4"),
    # film kaya warna (ref. "poetry of colors" & "power of Masking"): kontras dalam, bayangan teal,
    # cahaya emas, warna pekat
    "kaya": ("curves=all='0/0 0.25/0.2 0.5/0.5 0.75/0.8 1/0.98',"
             "colorbalance=rs=-0.07:gs=0.0:bs=0.06:rm=0.02:bm=-0.02:rh=0.07:gh=0.02:bh=-0.06,"
             "eq=saturation=1.18:contrast=1.02,vignette=PI/5"),
    # pastel cerah (ref. "The beauty of Color Grading"): lembut, highlight krem, hijau segar
    "pastel": ("curves=all='0/0.06 0.5/0.55 1/0.97',"
               "colorbalance=gs=0.01:bs=0.01:rm=0.03:gm=0.02:bm=-0.03:rh=0.04:gh=0.02:bh=-0.04,"
               "eq=saturation=1.06:contrast=0.97"),
    # arsip digital (ref. "visual archives"): unfiltered, sedikit kontras dan tajam
    "arsip": ("curves=all='0/0 0.25/0.22 0.75/0.78 1/1',"
              "colorbalance=rs=-0.02:bs=0.02:rh=0.01,eq=saturation=0.95:contrast=1.03,unsharp=5:5:0.6"),
    # camcorder VHS 80-an (ref. "Footage of me from 86"): lembut/blur, pink-peach, hitam pudar,
    # noise warna. Satu-satunya preset dengan noise, karena noise memang bagian dari look ini.
    "vhs": ("scale=iw/2:-2,scale=iw*2:-2,gblur=sigma=0.8,"
            "curves=all='0/0.07 0.5/0.53 1/0.93',"
            "colorbalance=rs=0.05:gs=-0.03:bs=0.04:rm=0.08:gm=-0.03:bm=0.03:rh=0.06:gh=-0.01:bh=-0.01,"
            "eq=saturation=0.9:contrast=0.97,noise=c0s=5:c1s=9:c2s=9:allf=t"),
    # musim panas Mediterania (ref. "Frames from Monaco"): highlight peach hangat, air & langit teal pekat
    "riviera": ("curves=all='0/0.01 0.3/0.28 0.7/0.73 1/0.98',"
                "colorbalance=rs=-0.05:gs=0.0:bs=0.05:rm=0.04:gm=0.01:bm=-0.03:rh=0.06:gh=0.02:bh=-0.05,"
                "eq=saturation=1.12:contrast=1.03,vignette=PI/6"),
    # mimpi (ref. "Willowtree"): cahaya berpendar (halation), hijau-teal lembut, bayangan diangkat
    "mimpi": ("split[mi_a][mi_b];[mi_b]gblur=sigma=14[mi_c];"
              "[mi_a][mi_c]blend=all_mode=screen:all_opacity=0.3,"
              "curves=all='0/0.05 0.5/0.52 1/0.97',"
              "colorbalance=rs=-0.04:gs=0.02:bs=0.03:rm=-0.01:gm=0.02:rh=0.03:bh=-0.02,"
              "eq=saturation=0.95:contrast=0.98"),
    # vintage krem (ref. "Creative cute fonts", jalanan Bangkok): pudar, putih kekuningan, hijau kalem
    "vintage": ("curves=all='0/0.06 0.5/0.52 1/0.93',"
                "colorbalance=rs=0.02:gs=0.01:bs=-0.02:rm=0.03:gm=0.01:bm=-0.04:rh=0.05:gh=0.03:bh=-0.08,"
                "eq=saturation=0.85:contrast=1.0,vignette=PI/5"),
    # retro 70-an (ref. "Vibe"): langit cyan, matahari keemasan, bayangan teal pudar
    "retro70": ("curves=all='0/0.05 0.5/0.52 1/0.96',"
                "colorbalance=rs=-0.05:gs=0.02:bs=0.04:rm=0.02:gm=0.01:bm=-0.02:rh=0.06:gh=0.03:bh=-0.06,"
                "eq=saturation=1.05:contrast=1.0,vignette=PI/5"),
    # indie kalem (ref. "an orchid", "routine"): redup, warna diredam, bayangan kehijauan, vignette kuat
    "indie": ("curves=all='0/0.02 0.3/0.25 0.7/0.68 1/0.92',"
              "colorbalance=rs=-0.02:gs=0.03:bs=0.0:rm=0.02:gm=0.01:bm=-0.02:rh=0.03:bh=-0.03,"
              "eq=saturation=0.8:contrast=1.04,vignette=PI/4"),
    # film Y2K (ref. "See you in Cupertino"): cross-process, highlight oranye-merah, bayangan hijau-cyan,
    # sedikit pendar
    "y2k": ("split[y2_a][y2_b];[y2_b]gblur=sigma=10[y2_c];"
            "[y2_a][y2_c]blend=all_mode=screen:all_opacity=0.18,"
            "curves=all='0/0.03 0.3/0.27 0.7/0.74 1/0.96',"
            "colorbalance=rs=-0.06:gs=0.05:bs=-0.01:rm=0.03:gm=0.0:bm=-0.04:rh=0.08:gh=0.02:bh=-0.08,"
            "eq=saturation=1.12:contrast=1.02,vignette=PI/5"),
    # --- dari analisis 118 reels (Gemini + penilaian visual), dikalibrasi dengan angka terukur reels contoh ---
    # senja: sepia rose ala puisi visual (DclgKROutRB): bayangan merah bata, highlight krem-pink, hitam pudar
    "senja": ("colortemperature=temperature=5800,curves=r='0/0.06 0.5/0.55 1/0.96':g='0/0.04 0.5/0.48 1/0.91':b='0/0.05 0.5/0.42 1/0.84',"
              "colorbalance=rs=0.05:bs=-0.03:rh=0.03:bh=-0.04,eq=saturation=0.86:contrast=0.96,vignette=PI/6," + GRAIN),
    # malam: lampu amber + bayangan teal, highlight tidak pecah, sedikit pendar (Dc3ey6DN8hx, DebSubwhvCF)
    "malam": ("colortemperature=temperature=5600,colorbalance=rs=-0.06:gs=0.01:bs=0.07:rm=0.02:bm=-0.02:rh=0.08:bh=-0.08,"
              "curves=all='0/0 0.25/0.2 0.6/0.58 1/0.9',split[ml_a][ml_b];[ml_b]gblur=sigma=12[ml_c];"
              "[ml_a][ml_c]blend=all_mode=screen:all_opacity=0.15,eq=saturation=1.0:contrast=1.04,vignette=PI/5," + GRAIN),
    # terakota: satu warna hangat terracotta-emas di semua shot, seperti majalah (DcdqMmTt42B)
    "terakota": ("colortemperature=temperature=4300,colorbalance=rs=0.07:gs=-0.01:bs=-0.07:rm=0.06:bm=-0.06:rh=0.07:bh=-0.08,"
                 "curves=all='0/0.04 0.3/0.27 0.75/0.76 1/0.94',eq=saturation=1.1:contrast=1.03,vignette=PI/7," + GRAIN),
    # zaitun: hijau hutan + karamel, gelap dan tenang (DdlvnRuJEuy)
    "zaitun": ("curves=all='0/0.03 0.25/0.19 0.7/0.64 1/0.88',"
               "colorbalance=rs=0.01:gs=0.04:bs=-0.02:rm=0.04:gm=0.02:bm=-0.05:rh=0.04:bh=-0.05,"
               "eq=saturation=0.8,vignette=PI/4.5," + GRAIN),
    # matte: siang lembut dari jendela, krem gading, hitam sedikit pudar (DeZtNbvRd2v, DcbKuuORzyb)
    "matte": ("curves=r='0/0.04 0.5/0.53 1/0.98':g='0/0.035 0.5/0.5 1/0.96':b='0/0.045 0.5/0.46 1/0.91',"
              "colorbalance=rs=0.02:bs=-0.03:rh=0.04:bh=-0.05,eq=saturation=0.88:contrast=0.98,vignette=PI/7," + GRAIN),
    # emas: padang golden hour, kuning-zaitun cerah, hitam matte (DctT-NpsK78)
    "emas": ("colortemperature=temperature=6200,colorbalance=rs=0.05:gs=0.02:bs=-0.07:rm=0.04:bm=-0.04:rh=0.07:bh=-0.08,"
             "curves=all='0/0.05 0.3/0.28 0.8/0.82 1/0.96',eq=saturation=1.18:contrast=1.04,vignette=PI/7," + GRAIN),
}

# Font judul hook. (font, miring, tebal, skala ukuran). Kata besar di judul 2 baris memakai font ini.
JUDUL = {
    "serif": ("Georgia", 0, 0, 1.0),                 # "The beauty of / Color Grading"
    "miring": ("Bodoni MT", -1, 0, 1.05),            # "frames from / Monaco"
    "script": ("Edwardian Script ITC", 0, 0, 1.45),  # "See you in Cupertino", "Willowtree"
    "tebal": ("Segoe UI", 0, -1, 0.95),              # "The Power of / Colorgrading"
    "kartun": ("Kristen ITC", 0, 0, 1.0),            # paling mirip WoodFont ("Creative cute fonts")
    "retro": ("Cooper Black", 0, 0, 0.95),           # 70-an, cocok dengan warna retro70
}


# Pengaturan manual di atas preset warna, skala -100..100 (vignette/glow/tajam/grain: 0..100).
ATUR = ["eksposur", "kontras", "saturasi", "suhu", "tint", "bayangan", "sorotan",
        "vignette", "glow", "tajam", "grain"]


def atur_filter(atur):
    """Ubah pengaturan manual jadi filter ffmpeg. Nilai 0 = tidak diubah."""
    v = {k: float(atur.get(k, 0) or 0) for k in ATUR}
    f = []
    if v["eksposur"]:
        f.append(f"exposure=exposure={v['eksposur'] / 100:.3f}")  # +-1 stop
    if v["suhu"]:  # positif = lebih hangat (kelvin lebih rendah)
        f.append(f"colortemperature=temperature={6500 - v['suhu'] * 25:.0f}")
    if v["tint"]:  # positif = magenta, negatif = hijau
        f.append(f"colorbalance=gs={-v['tint'] / 400:.3f}:gm={-v['tint'] / 400:.3f}:gh={-v['tint'] / 400:.3f}")
    if v["bayangan"] or v["sorotan"]:
        b, so = v["bayangan"] / 100, v["sorotan"] / 100
        f.append("curves=all='0/{:.3f} 0.25/{:.3f} 0.75/{:.3f} 1/{:.3f}'".format(
            max(0.0, b * 0.08), 0.25 + b * 0.05, 0.75 + so * 0.06, min(1.0, 1 + min(0.0, so) * 0.08)))
    if v["kontras"] or v["saturasi"]:
        f.append(f"eq=contrast={1 + v['kontras'] / 200:.3f}:saturation={1 + v['saturasi'] / 100:.3f}")
    if v["glow"] > 0:
        f.append(f"split[gl_a][gl_b];[gl_b]gblur=sigma=12[gl_c];"
                 f"[gl_a][gl_c]blend=all_mode=screen:all_opacity={v['glow'] / 100 * 0.5:.3f}")
    if v["tajam"] > 0:
        f.append(f"unsharp=5:5:{v['tajam'] / 100 * 1.2:.2f}")
    if v["vignette"] > 0:
        f.append(f"vignette=angle={0.15 + v['vignette'] / 100 * 0.6:.3f}")
    if v["grain"] > 0:
        f.append(f"noise=alls={v['grain'] / 100 * 20:.0f}:allf=t")
    return ",".join(f)


PER_PIKSEL = {"curves", "colorbalance", "eq", "exposure", "colortemperature", "colorchannelmixer", "hue",
              "colorlevels", "lutrgb", "lutyuv", "lut3d", "selectivecolor", "colorcontrast", "colorcorrect",
              "huesaturation", "vibrance", "monochrome"}


CACHE_LUT = Path(tempfile.gettempdir()) / "hangat_lut"


def pisah_warna(rantai):
    """(warna per piksel, filter ruang). Warna per piksel boleh dikerjakan di gambar sumber yang masih kecil
    (sebelum diperbesar ke 1080x1920: jauh lebih sedikit piksel); filter ruang (vignette, grain, glow)
    bergantung pada posisi di layar, jadi tetap di gambar akhir."""
    piksel, ruang = [], []
    for f in _pisah_filter(rantai):
        nama = f.split("=", 1)[0].strip()
        (piksel if nama in PER_PIKSEL and "[" not in f else ruang).append(f)
    return ",".join(piksel), ",".join(ruang)


def _pisah_filter(rantai):
    """Pisah rantai filter di koma tingkat atas (koma di dalam '...' bukan pemisah)."""
    bagian, kini, kutip = [], "", False
    for c in rantai:
        if c == "'":
            kutip = not kutip
        if c == "," and not kutip:
            bagian.append(kini)
            kini = ""
        else:
            kini += c
    return bagian + [kini] if kini else bagian


def jadikan_lut(rantai, folder):
    """Filter warna yang hanya bergantung pada warna piksel itu sendiri (curves, eq, colorbalance, exposure, ...)
    dibakar sekali jadi satu LUT 3D, lalu di render cukup satu lut3d per frame. Hasil sama, jauh lebih cepat
    (6-8 filter berat di 1080x1920 jadi satu). Filter ruang (vignette, blur, grain, glow) tetap seperti biasa."""
    import numpy as np
    keluar, run = [], []

    def bakar():
        if not run:
            return
        if len(run) == 1 and run[0].startswith("lut3d="):
            keluar.append(run[0])
        else:
            n = len(list(Path(folder).glob("bakar*.cube")))
            berkas = Path(folder) / f"bakar{n}.cube"
            # LUT yang sama (preset + pengaturan sama) dipakai ulang antar export: tidak perlu dibakar lagi
            import hashlib
            simpan = CACHE_LUT / (hashlib.md5(",".join(run).encode()).hexdigest() + ".cube")
            if simpan.exists():
                berkas.write_bytes(simpan.read_bytes())
                keluar.append(f"lut3d={berkas.name}:interp=tetrahedral")
                run.clear()
                return
            r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "haldclutsrc=level=8", "-frames:v", "1",
                                "-vf", ",".join(run) + ",format=rgb48le", "-f", "rawvideo", "-"],
                               capture_output=True, creationflags=TANPA_JENDELA, cwd=folder)
            if r.returncode != 0 or len(r.stdout) != 512 * 512 * 6:
                keluar.extend(run)  # gagal membakar: pakai filter aslinya
            else:
                lut = np.frombuffer(r.stdout, "<u2").reshape(-1, 3) / 65535.0  # urutan hald: r tercepat = urutan .cube
                isi = "LUT_3D_SIZE 64\n" + "\n".join(f"{a:.5f} {b:.5f} {c:.5f}" for a, b, c in lut)
                berkas.write_text(isi, encoding="ascii")
                try:
                    CACHE_LUT.mkdir(parents=True, exist_ok=True)
                    simpan.write_text(isi, encoding="ascii")
                except OSError:
                    pass
                keluar.append(f"lut3d={berkas.name}:interp=tetrahedral")
        run.clear()

    for f in _pisah_filter(rantai):
        nama = f.split("=", 1)[0].strip()
        if nama in PER_PIKSEL and "[" not in f:
            run.append(f)
        else:
            bakar()
            if nama == "vignette" and "dither" not in f:  # dither vignette tidak terlihat setelah encode, tapi mahal
                f += ":dither=0" if "=" in f else "=dither=0"
            keluar.append(f)
    bakar()
    return ",".join(keluar)


def atur_otomatis(video, n=12, lebar=192):
    """Ukur video (n frame kecil merata) lalu kembalikan nilai ATUR yang mengoreksi eksposur, kontras,
    white balance, dan warna secara halus. Sengaja konservatif: hasilnya rapi dan natural, bukan stylized."""
    import numpy as np
    w, h, durasi = info_video(video)
    if foto(video):
        n, lebar = 1, 512  # satu gambar: ukur lebih detail
    tinggi = max(2, round(lebar * h / w))
    frame = []
    for i in range(n):  # seek per frame: jauh lebih cepat daripada men-decode seluruh video
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{durasi * (i + 0.5) / n:.2f}", "-i", str(video),
                            "-frames:v", "1", "-vf", f"scale={lebar}:{tinggi}", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], capture_output=True, creationflags=TANPA_JENDELA)
        if len(r.stdout) == lebar * tinggi * 3:
            f = np.frombuffer(r.stdout, np.uint8).reshape(tinggi, lebar, 3)
            # buang garis hitam letterbox di atas/bawah: itu bingkai, bukan bagian gambar
            gelap = f.mean(axis=(1, 2)) < 8
            a, b = 0, tinggi
            while a < b and gelap[a]:
                a += 1
            while b > a and gelap[b - 1]:
                b -= 1
            if b - a > tinggi * 0.3:
                frame.append(f[a:b].reshape(-1, 3))
    hasil = {k: 0 for k in ATUR}
    if not frame:
        return hasil
    rgb = np.concatenate(frame).astype(np.float32) / 255
    luma = np.array([0.2126, 0.7152, 0.0722], np.float32)
    y = rgb @ luma

    def batas(x, lo, hi):
        return int(round(max(lo, min(hi, x))))

    # Eksposur: mean luma ke ~0.45, 70% saja. Slider 100 ~ x1.9 (diukur), jadi stops*100 cukup dekat.
    # Naiknya dibatasi supaya highlight terang (lampu, langit) tidak ikut terbakar.
    p98 = float(np.percentile(y, 98))
    stops = 0.7 * np.log2(0.45 / max(float(y.mean()), 0.01))
    if stops > 0:
        stops = min(stops, np.log2(0.97 / max(p98, 0.05)))  # bagian paling terang tidak boleh terbakar
    hasil["eksposur"] = batas(stops * 100, -60, 60)
    # sisa langkah dihitung pada gambar yang sudah dikoreksi eksposurnya
    rgb = np.clip(rgb * 2 ** (hasil["eksposur"] / 100), 0, 1)
    y = rgb @ luma
    p2, p98, std = (float(np.percentile(y, 2)), float(np.percentile(y, 98)), float(y.std()))

    if p2 > 0.06:  # hitam pudar -> dalamkan
        hasil["bayangan"] = batas(-(p2 - 0.06) * 250, -40, 0)
    elif p2 < 0.02 and (y < 0.02).mean() > 0.05:  # hitam menggumpal -> angkat sedikit
        hasil["bayangan"] = batas(((y < 0.02).mean() - 0.05) * 150, 0, 30)
    if p98 > 0.97:  # highlight terbakar -> redam
        hasil["sorotan"] = batas(-(p98 - 0.97) * 1333, -40, 0)
    elif p98 < 0.85:  # highlight kusam -> angkat
        hasil["sorotan"] = batas((0.85 - p98) * 100, 0, 40)
    k = (0.20 - std) * 250  # zona mati 5 poin: selisih kecil tidak perlu dikoreksi
    hasil["kontras"] = batas(np.sign(k) * max(0.0, abs(k) - 5), -30, 30)

    # White balance gray-world pada nada tengah saja (hitam/putih tidak membawa info warna).
    # 1 poin slider ~ 0.0031 pada r dan g (diukur); koreksi separuh jalan. Target r sedikit hangat (+0.05)
    # dengan zona mati: kulit memang hangat dan grade hangat disengaja, jadi hanya cast yang jelas dikoreksi.
    def koreksi(selisih, mati):
        return np.sign(selisih) * max(0.0, abs(selisih) - mati) / 0.0031 * 0.5

    mid = (y > 0.15) & (y < 0.85)
    if mid.sum() > 500:
        r_, g_, b_ = rgb[mid].T
        hangat = float(((r_ - b_) / y[mid]).mean())
        hijau = float(((g_ - (r_ + b_) / 2) / y[mid]).mean())
        # pendinginan dibatasi -20: adegan sore/sunset memang hangat, didinginkan penuh jadi kusam keabuan
        hasil["suhu"] = batas(-koreksi(hangat - 0.05, 0.10), -20, 40)
        hasil["tint"] = batas(koreksi(hijau, 0.04), -30, 30)

    # saturasi: hanya ditarik kalau jelas pucat atau jelas terlalu pekat
    chroma = float((rgb.max(1) - rgb.min(1)).mean())
    hasil["saturasi"] = batas((0.12 - chroma) * 400 if chroma < 0.12 else -(chroma - 0.22) * 300
                              if chroma > 0.22 else 0, -20, 25)
    return hasil


def loncat(teks, seed=0):
    """Tinggi dan lebar huruf sedikit acak supaya terasa digambar tangan (ala WoodFont)."""
    r = random.Random(seed)
    return "".join(c if c == " " else
                   rf"{{\fscy{r.choice([88, 94, 100, 106, 112])}\fscx{r.choice([94, 100, 104])}}}{c}"
                   for c in teks) + r"{\fscx100\fscy100}"
HOOK_HANGAT = dict(font="Georgia", ukuran=80, warna=KREM, tebal=0, miring=-1)

# Posisi teks rata-bawah: di video vertikal 9:16, UI Instagram (caption, tombol) menutup bagian bawah,
# jadi margin_v gaya dipakai apa adanya (600 px di kanvas 1920). Di rasio lain teks turun ke 7% dari bawah.

# Semua versi hangat: teks di bawah, cukup besar untuk dibaca tanpa suara, maks 5 kata (1-2 baris), shadow lembut berlapis
# (glow coklat transparan + bayangan jatuh), kuning hangat seperti subtitle "My Creative Process".
_HANGAT = dict(warna_outline=COKLAT, outline=3, bayangan=2, align=2, margin_l=90, margin_r=90,
               margin_v=600, maks_kata=5, scale_x=100, hook=HOOK_HANGAT, grade=GRADE_HANGAT)

# Ukuran untuk kanvas 1080 px (sisi terpendek); diskalakan otomatis.
GAYA = {
    # krem jelas + satu kata penting serif miring kuning
    "hangat": dict(_HANGAT, font="Segoe UI", ukuran=72, warna=KREM, huruf="kecil", efek="aksen"),
    # seluruh teks kuning hangat, polos dan paling mirip subtitle referensi
    "hangat-kuning": dict(_HANGAT, font="Segoe UI", ukuran=74, warna=KUNING, huruf="asli", efek="glow"),
    # editorial: serif miring krem, kata penting kuning
    "hangat-serif": dict(_HANGAT, font="Georgia", ukuran=74, warna=KREM, miring=True, huruf="kecil",
                         efek="aksen", aksen_font="Georgia"),
    # paling mudah dibaca: teks krem di atas kotak gelap transparan bersudut lembut
    "hangat-kotak": dict(_HANGAT, font="Segoe UI", ukuran=62, warna=KREM, warna_outline="&H38141018",
                         outline=12, bayangan=0, kotak=True, huruf="asli", efek="aksen",
                         aksen_font="Segoe UI"),  # font sama supaya lebar kotak pas dengan teks
    # kartun (ref. WoodFont di "Creative cute fonts"): krem, huruf bulat yang tingginya loncat-loncat
    "kartun": dict(_HANGAT, font="Kristen ITC", ukuran=70, warna=KREM, huruf="asli", efek="loncat",
                   hook=dict(HOOK_HANGAT, font="Kristen ITC", miring=0)),
    # "do you understand the fire inside": teks tipis putih, huruf kecil, di samping wajah
    "sinematik": dict(
        font="Bahnschrift", ukuran=84, warna=PUTIH, outline=0, bayangan=1.5,
        align=4, margin_l=90, margin_r=470, margin_v=0, maks_kata=4,
        huruf="kecil", scale_x=88, efek="fade",
        grade="eq=contrast=1.06:saturation=0.88:gamma=0.97,"
              "colorbalance=rs=0.05:bs=-0.06:rh=0.03:bh=-0.04,"
              "vignette=PI/5",
    ),
    # "And I will always miss you" / "My Creative Process": subtitle kecil di bawah
    "minimal": dict(
        font="Consolas", ukuran=48, warna=PUTIH, outline=0, bayangan=1,
        align=2, margin_l=80, margin_r=80, margin_v=690, maks_kata=7,
        huruf="subtitle", scale_x=100, efek="fade",
        grade="eq=contrast=1.08:saturation=0.82:gamma=0.96,vignette=PI/4",
    ),
    # tutorial DaVinci "weather icon": kapital tebal, kata yang diucapkan disorot ungu
    "bold": dict(
        font="Arial Black", ukuran=68, warna=PUTIH, outline=0, bayangan=2,
        align=2, margin_l=60, margin_r=60, margin_v=700, maks_kata=4,
        huruf="kapital", scale_x=100, efek="sorot",
        grade="eq=contrast=1.05:saturation=1.08",
    ),
    # "Comment COLOR": kata besar hijau mint di tengah, muncul 1-2 kata
    "pop": dict(
        font="Segoe UI", ukuran=132, warna=MINT, outline=0, bayangan=2,
        align=5, margin_l=60, margin_r=60, margin_v=0, maks_kata=2,
        huruf="asli", scale_x=100, efek="pop", tebal=True,
        grade="eq=contrast=1.06:saturation=1.15,colorbalance=bs=0.04:rh=0.04",
    ),
}

# Deskripsi singkat untuk UI dan untuk Gemini saat memilih (tombol Magic).
INFO_GAYA = {
    "hangat-kotak": "teks krem di atas kotak gelap transparan, kata kunci miring kuning; paling mudah dibaca",
    "hangat-kuning": "seluruh teks kuning hangat dengan bayangan lembut, seperti subtitle film",
    "hangat-serif": "serif miring krem seperti judul majalah, kata kunci kuning; elegan",
    "hangat": "teks krem tanpa kotak, kata kunci serif miring kuning; estetik, tenang",
    "kartun": "huruf bulat krem yang loncat-loncat ala WoodFont; lucu, santai, playful",
    "sinematik": "teks tipis putih huruf kecil di samping wajah; puitis, sinematik",
    "minimal": "subtitle kecil monospace di bawah; arsip/diary, sangat kalem",
    "bold": "HURUF KAPITAL tebal, kata yang diucapkan disorot ungu; tutorial, energik",
    "pop": "1-2 kata besar hijau mint di tengah layar; cepat, punchy",
}
INFO_WARNA = {
    "monokrom": "hitam putih klasik, kontras dalam, kulit tetap terang",
    "monokrom-lembut": "hitam putih lembut, hitam pudar ala matte",
    "monokrom-hangat": "monokrom hangat ala sepia/selenium",
    "monokrom-dingin": "monokrom dingin kebiruan ala cyanotype",
    "monokrom-film": "hitam putih film: kontras kuat + grain halus",
    "hangat": "warm aesthetic halus, kulit hangat, bayangan bersih",
    "natural": "hampir seperti aslinya, hanya dirapikan",
    "golden": "sore keemasan, oranye-kuning, lebih berwarna",
    "film": "film pudar, hitam keabuan, warna kalem",
    "sinematik": "teal & orange ala film",
    "terang": "bright & airy, terang, lembut, sedikit pastel",
    "moody": "gelap dan dingin, warna diredam",
    "kaya": "film kaya warna, kontras dalam, langit teal, cahaya emas",
    "pastel": "cerah lembut, highlight krem, hijau segar",
    "arsip": "digital unfiltered, sedikit kontras dan tajam",
    "vhs": "camcorder 80-an, lembut/blur, pink-peach, noise",
    "riviera": "musim panas Mediterania, highlight peach, air/langit teal pekat",
    "mimpi": "dreamy, cahaya berpendar (halation), hijau-teal lembut",
    "vintage": "vintage krem pudar, putih kekuningan, hijau kalem",
    "retro70": "retro 70-an, langit cyan, matahari keemasan, bayangan teal pudar",
    "indie": "indie kalem, redup, warna diredam, vignette kuat",
    "y2k": "film Y2K cross-process, highlight oranye-merah, bayangan hijau-cyan",
    "senja": "sepia rose ala puisi visual: bayangan merah bata, highlight krem-pink, pudar lembut",
    "malam": "malam kota: lampu amber, bayangan teal, sedikit pendar",
    "terakota": "terracotta-emas seperti majalah travel, sangat hangat",
    "zaitun": "hijau hutan + karamel, gelap dan tenang",
    "matte": "siang lembut dari jendela, krem gading, hitam sedikit pudar; paling aman untuk vlog",
    "emas": "golden hour cerah, kuning-zaitun, hitam matte",
    "asli": "tanpa color grading",
}
INFO_JUDUL = {
    "serif": "serif klasik (The beauty of / Color Grading)",
    "miring": "serif miring elegan (frames from / Monaco)",
    "script": "tulisan sambung mewah (See you in Cupertino, Willowtree)",
    "tebal": "sans tebal modern (The Power of / Colorgrading)",
    "kartun": "huruf kartun loncat ala WoodFont",
    "retro": "Cooper Black ala 70-an",
}

# Template siap pakai untuk mode mudah: satu klik = gaya teks + warna + font judul + sentuhan atur.
# "atur" ditambahkan di atas koreksi otomatis (eksposur/white balance diukur dulu, lalu diberi gaya).
TEMPLATE = {
    # bawaan: video dibiarkan seperti aslinya (tanpa grade, tanpa koreksi otomatis), hanya teks
    "Asli": dict(gaya="hangat-kotak", warna="asli", judul="kartun", atur={}, tanpa_auto=True,
                 desk="Warna seperti video aslinya, tidak diubah. Hanya ditambah teks."),
    "Vlog Hangat": dict(gaya="hangat-kotak", warna="hangat", judul="kartun", atur={},
                        desk="Hangat, bersih, teks paling jelas. Cocok untuk hampir semua video."),
    # --- dari analisis 118 reels pilihanmu (REELS-ANALISIS.md) ---
    "Matte Jendela": dict(gaya="hangat-kotak", warna="matte", judul="serif", atur={},
                          desk="Siang lembut dari jendela, krem gading, grain halus. Paling aman untuk vlog."),
    "Senja Puisi": dict(gaya="hangat-serif", warna="senja", judul="miring", atur={},
                        desk="Sepia rose ala puisi visual: bayangan merah bata, highlight krem-pink."),
    "Malam Kota": dict(gaya="hangat-kuning", warna="malam", judul="script", atur={},
                       desk="Lampu amber + bayangan teal yang berpendar. Untuk malam dan jalan-jalan."),
    "Terakota": dict(gaya="hangat-serif", warna="terakota", judul="serif", atur={},
                     desk="Satu warna terracotta-emas seperti majalah travel."),
    "Hutan Zaitun": dict(gaya="minimal", warna="zaitun", judul="miring", atur={},
                         desk="Hijau hutan + karamel, gelap dan tenang; subtitle kecil."),
    "Padang Emas": dict(gaya="hangat", warna="emas", judul="serif", atur={},
                        desk="Golden hour cerah, kuning-zaitun, hitam matte."),
    "Golden Hour": dict(gaya="hangat-kuning", warna="golden", judul="serif", atur={"glow": 15, "vignette": 15},
                        desk="Cahaya sore keemasan yang berpendar lembut."),
    "Puisi Film": dict(gaya="hangat-serif", warna="film", judul="miring",
                       atur={"bayangan": 8, "saturasi": -8, "vignette": 20},
                       desk="Film pudar, kalem, teks serif miring. Untuk cerita dan b-roll puitis."),
    "Mimpi": dict(gaya="hangat", warna="mimpi", judul="script", atur={"glow": 10},
                  desk="Dreamy, cahaya berpendar, judul tulisan sambung."),
    "Natural": dict(gaya="hangat-kotak", warna="natural", judul="tebal", atur={},
                    desk="Hampir seperti aslinya, hanya dirapikan."),
    "Terang Lembut": dict(gaya="hangat", warna="terang", judul="serif", atur={},
                          desk="Bright & airy: terang, lembut, sedikit pastel."),
    "Riviera": dict(gaya="hangat-kuning", warna="riviera", judul="miring", atur={},
                    desk="Musim panas: kulit peach, langit dan air teal."),
    "Retro 70": dict(gaya="kartun", warna="retro70", judul="retro", atur={"vignette": 10},
                     desk="Retro 70-an yang playful, huruf loncat."),
    "Vintage": dict(gaya="kartun", warna="vintage", judul="kartun", atur={},
                    desk="Krem pudar ala foto lama, huruf kartun ala WoodFont."),
    "Moody": dict(gaya="hangat-serif", warna="moody", judul="miring", atur={},
                  desk="Gelap, dingin, tenang. Untuk malam atau suasana sendu."),
    "Monokrom": dict(gaya="minimal", warna="monokrom", judul="serif", atur={}, tanpa_auto=True,
                     desk="Hitam putih klasik yang tegas. Untuk cerita, potret, dan suasana tenang."),
    "Monokrom Film": dict(gaya="hangat-serif", warna="monokrom-film", judul="miring", atur={}, tanpa_auto=True,
                          desk="Hitam putih film dengan grain halus, judul serif miring."),
    "Sepia Hangat": dict(gaya="hangat-serif", warna="monokrom-hangat", judul="script", atur={}, tanpa_auto=True,
                         desk="Monokrom hangat seperti foto lama yang dicetak ulang."),
    "Tutorial": dict(gaya="bold", warna="terang", judul="tebal", atur={"tajam": 15},
                     desk="Jelas dan energik: kata yang diucapkan disorot."),
}

RASIO = {"asli": None, "9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}


def jalankan(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=TANPA_JENDELA, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"Gagal: {' '.join(map(str, cmd[:3]))} ...\n{r.stderr[-2000:]}")
    return r.stdout


def jalankan_progres(cmd, total, **kw):
    """Seperti jalankan(), tapi mencetak "[progres] NN" dari laporan ffmpeg supaya UI bisa menampilkan persen."""
    p = subprocess.Popen([cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                         creationflags=TANPA_JENDELA, **kw)
    galat = []
    threading.Thread(target=lambda: galat.extend(p.stderr), daemon=True).start()  # stderr tidak boleh macet
    terakhir = -1
    for baris in p.stdout:
        if baris.startswith("out_time_us=") and total > 0:
            try:
                persen = min(99, int(int(baris.split("=")[1]) / 1e6 / total * 100))
            except ValueError:
                continue
            if persen > terakhir:
                terakhir = persen
                print(f"[progres] {persen}", flush=True)
    if p.wait() != 0:
        raise RuntimeError(f"Gagal: {' '.join(map(str, cmd[:3]))} ...\n{''.join(galat)[-2000:]}")


_ENKODER = None


def enkoder(crf=18):
    """Encode video lewat GPU NVIDIA (NVENC) kalau ada: jauh lebih cepat, kualitas setara. Kalau tidak ada /
    gagal, pakai libx264 di CPU. Dicoba sekali per proses dengan encode kecil."""
    global _ENKODER
    if _ENKODER is None:
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.2",
                            "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, creationflags=TANPA_JENDELA)
        _ENKODER = "nvenc" if r.returncode == 0 and os.environ.get("HANGAT_CPU") != "1" else "cpu"
    if _ENKODER == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", str(crf + 1), "-b:v", "0",
                "-spatial-aq", "1", "-temporal-aq", "1", "-bf", "3", "-b_ref_mode", "middle"]
    # preset faster + crf 1 lebih rendah: kualitas sama (SSIM diukur) dengan medium, encode ~40% lebih cepat
    return ["-c:v", "libx264", "-preset", "faster", "-crf", str(crf - 1)]


FOTO = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic")


def foto(path):
    return Path(path).suffix.lower() in FOTO


def info_video(path):
    """Lebar, tinggi, durasi. Foto berdurasi 0."""
    out = jalankan(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                    "stream=width,height:stream_side_data=rotation:format=duration", "-of", "json",
                    str(path)])
    d = json.loads(out)
    s = d["streams"][0]
    w, h = s["width"], s["height"]
    # video HP vertikal sering disimpan landscape + tanda putar; ffmpeg memutarnya otomatis
    if any(abs(x.get("rotation", 0)) % 180 == 90 for x in s.get("side_data_list", [])):
        w, h = h, w
    return w, h, 0.0 if foto(path) else float(d["format"]["duration"])


def punya_audio(path):
    out = jalankan(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                    "-of", "csv=p=0", str(path)])
    return bool(out.strip())


def gabung(videos, keluar):
    """Sambung beberapa klip berurutan jadi satu mp4. Ukuran mengikuti klip pertama; klip lain dimuat utuh
    (tanpa distorsi) dengan bingkai hitam. Klip tanpa suara diberi hening supaya concat tidak gagal."""
    w, h, _ = info_video(videos[0])
    w, h = w // 2 * 2, h // 2 * 2
    masukan, rantai = [], []
    for i, v in enumerate(videos):
        masukan += ["-i", str(v)]
        durasi = info_video(v)[2]
        rantai.append(f"[{i}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                      f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30,format=yuv420p[v{i}]")
        # apad+atrim: panjang audio dipaksa sama dengan videonya supaya sambungan tidak bergeser
        sumber = (f"[{i}:a:0]aresample=48000,aformat=channel_layouts=stereo,apad" if punya_audio(v)
                  else "anullsrc=r=48000:cl=stereo")
        rantai.append(f"{sumber},atrim=0:{durasi:.3f},asetpts=PTS-STARTPTS[a{i}]")
    urut = "".join(f"[v{i}][a{i}]" for i in range(len(videos)))
    rantai.append(f"{urut}concat=n={len(videos)}:v=1:a=1[vo][ao]")
    jalankan(["ffmpeg", "-y", "-v", "error", *masukan, "-filter_complex", ";".join(rantai),
              "-map", "[vo]", "-map", "[ao]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
              "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(keluar)])


def baca_pcm(path, sr=8000, maks=180):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", str(maks), "-ac", "1", "-ar", str(sr),
                        "-f", "f32le", "-"], capture_output=True, creationflags=TANPA_JENDELA)
    return np.frombuffer(r.stdout, dtype=np.float32)


def siapkan_suara(video, audio, keluar, durasi):
    """Suara direkam terpisah (HP/mic lain): cari selisih waktunya terhadap suara bawaan video lewat
    korelasi silang, lalu buat file suara yang sudah sejajar dengan video. Kembalikan (geser_detik, yakin)."""
    import numpy as np
    sr, geser, yakin = 8000, 0.0, 0.0
    if punya_audio(video):
        a, b = baca_pcm(video, sr), baca_pcm(audio, sr)
        if len(a) and len(b):
            n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
            korelasi = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
            lag = int(np.argmax(korelasi))
            if lag > n // 2:
                lag -= n
            yakin = float(korelasi.max() / (np.abs(korelasi).mean() + 1e-9))
            # yakin rendah = suara video terlalu beda/tidak ada; lebih aman anggap mulai bersamaan
            geser = lag / sr if yakin > 8 else 0.0
    awal = (f"adelay={geser * 1000:.0f}:all=1" if geser >= 0
            else f"atrim=start={-geser:.3f},asetpts=PTS-STARTPTS")
    jalankan(["ffmpeg", "-y", "-v", "error", "-i", str(audio), "-af",
              f"{awal},apad,atrim=0:{durasi:.3f}", "-ar", "48000", "-ac", "2", str(keluar)])
    return geser, yakin


def transkrip(video, bahasa, cache):
    """Daftar kata [{w, s, e}] dengan waktu per kata. Disimpan di cache supaya tidak diulang."""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    # DLL CUDA dari pip (nvidia-cublas-cu12, nvidia-cudnn-cu12) supaya GPU bisa dipakai
    import site
    for sp in site.getsitepackages():
        for sub in ("cublas", "cudnn"):
            d = Path(sp) / "nvidia" / sub / "bin"
            if d.is_dir():
                os.environ["PATH"] = f"{d}{os.pathsep}{os.environ['PATH']}"
    from faster_whisper import WhisperModel

    model = None
    for dev, ct in (("cuda", "int8_float16"), ("cpu", "int8")):
        try:
            model = WhisperModel("large-v3-turbo", device=dev, compute_type=ct, download_root=MODEL_DIR)
            print(f"[transkrip] large-v3-turbo di {dev}", flush=True)
            segs, _ = model.transcribe(str(video), language=bahasa, vad_filter=True,
                                       word_timestamps=True, beam_size=5,
                                       condition_on_previous_text=False)
            kata = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)}
                    for seg in segs for w in seg.words if w.word.strip()]
            break
        except Exception as e:  # GPU gagal (driver/VRAM) -> coba CPU
            if dev == "cpu":
                raise
            print(f"[transkrip] GPU gagal ({str(e)[:120]}), pakai CPU", flush=True)
    cache.write_text(json.dumps(kata, ensure_ascii=False), encoding="utf-8")
    return kata


def bagian_dipakai(kata, durasi, jeda_maks=0.5, pad=0.12):
    """Rentang waktu yang ada suaranya; jeda hening lebih dari jeda_maks dibuang."""
    if not kata:
        return [(0.0, durasi)]
    bagian = []
    for k in kata:
        a, b = max(0.0, k["s"] - pad), min(durasi, k["e"] + pad)
        if bagian and a - bagian[-1][1] <= jeda_maks:
            bagian[-1][1] = max(bagian[-1][1], b)
        else:
            bagian.append([a, b])
    return [tuple(x) for x in bagian]


def geser_waktu(kata, bagian, kec=None):
    """Pindahkan waktu kata ke timeline setelah dipotong. Urutan bagian boleh bebas dan boleh berulang
    (cold open: potongan terbaik diputar duluan, lalu muncul lagi di tempatnya). kec: kecepatan per bagian."""
    hasil, total = [], 0.0
    for (a, b), c in zip(bagian, kec or [1.0] * len(bagian)):
        hasil += [{"w": k["w"], "s": (k["s"] - a) / c + total, "e": (min(k["e"], b) - a) / c + total}
                  for k in kata if a <= k["s"] <= b]
        total += (b - a) / c
    return hasil


def potong_kalimat(kata, maks):
    """Kelompokkan kata jadi potongan teks pendek; pecah di tanda baca atau jeda."""
    potongan, cur = [], []
    for i, k in enumerate(kata):
        cur.append(k)
        akhir_kalimat = re.search(r"[.,!?;:]$", k["w"])
        jeda = i + 1 < len(kata) and kata[i + 1]["s"] - k["e"] > 0.4
        if len(cur) >= maks or akhir_kalimat or jeda:
            potongan.append(cur)
            cur = []
    if cur:
        potongan.append(cur)
    return potongan


def ass_waktu(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def bersih(teks, huruf):
    teks = teks.replace("{", "(").replace("}", ")")
    if huruf != "subtitle":  # gaya referensi tidak pakai titik/koma di akhir
        teks = teks.rstrip(".,;:")
    if huruf == "kecil":
        return teks.lower()
    if huruf == "kapital":
        return teks.upper()
    return teks


def buat_ass(kata, gaya, w, h, hook, durasi_hook, judul=None, elemen=None, area=None):
    g = GAYA[gaya]
    s = min(w, h) / 1080
    sx = w / 1080
    tebal = -1 if g.get("tebal") else 0
    hk = dict(font="Georgia", ukuran=88, warna=MINT if gaya == "pop" else PUTIH, tebal=-1, miring=0)
    hk.update(g.get("hook", {}))
    vertikal = h / w >= 1.7
    # zona aman IG hanya berlaku di 9:16; di rasio lain teks bawah cukup 7% dari tepi
    margin_v = g["margin_v"] * s if vertikal or g["align"] != 2 else h * 0.07
    maks_kata = round(g["maks_kata"] * 1.75) if w > h else g["maks_kata"]  # layar lebar muat lebih
    border = 3 if g.get("kotak") else 1  # 3 = kotak di belakang teks
    miring = -1 if g.get("miring") else 0
    # layar HP vertikal dilihat dari jauh dengan teks yang relatif sempit: perbesar 15% supaya terbaca
    ukuran = g["ukuran"] * s * (1.15 if vertikal else 1)
    blur = 0 if g.get("kotak") else 6 * s  # blur pada kotak membuat teks di dalamnya ikut pudar
    baris = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Teks,{g['font']},{ukuran:.0f},{g['warna']},{g['warna']},"
        f"{g.get('warna_outline', HITAM)},&H80000000,"
        f"{tebal},{miring},0,0,{g['scale_x']},100,0,0,{border},{g['outline'] * s:.1f},{g['bayangan'] * s:.1f},"
        # letterbox: subtitle tepat di bawah gambar (di bingkai hitam), judul tepat di atas gambar
        f"{8 if area and g['align'] == 2 else g['align']},{g['margin_l'] * sx:.0f},{g['margin_r'] * sx:.0f},"
        f"{area[1] + 34 * s if area and g['align'] == 2 else margin_v:.0f},1",
        f"Style: Hook,{hk['font']},{hk['ukuran'] * s:.0f},{hk['warna']},{hk['warna']},"
        f"{COKLAT if g.get('kotak') else g.get('warna_outline', HITAM)},&H90000000,{hk['tebal']},{hk['miring']},"
        f"0,0,100,100,0,0,1,{min(g['outline'], 3) * s:.1f},{3 * s:.1f},{2 if area else 8},{80 * sx:.0f},"
        f"{80 * sx:.0f},{h - area[0] + 34 * s if area else h * (0.16 if vertikal else 0.08):.0f},1",
        # elemen: (nama, font, ukuran, warna, miring, spasi, align, margin kiri/kanan, margin atas)
        *[f"Style: {n},{f},{u * s:.0f},{c},{c},{COKLAT},&H90000000,0,{m},0,0,100,100,{sp * s:.1f},0,1,"
          f"{3 * s:.1f},{2 * s:.1f},{al},{ml * sx:.0f},{ml * sx:.0f},{mv:.0f},1"
          for n, f, u, c, m, sp, al, ml, mv in [
              ("Label", "Segoe UI Semibold", 40, KREM, 0, 4, 7, 70, h * (0.10 if vertikal else 0.07)),
              ("Kata", "Georgia", 130, KUNING, -1, 0, 5, 60, 0),
              ("Daftar", "Georgia", 62, KREM, 0, 0, 7, 80, h * (0.24 if vertikal else 0.12)),
              ("Kutipan", "Georgia", 66, KREM, -1, 0, 5, 120, 0),
              ("Tanggal", "Consolas", 40, "&H0040A8FF", 0, 2, 9, 70, h * (0.10 if vertikal else 0.07)),
              ("Penutup", hk["font"], hk["ukuran"], hk["warna"], hk["miring"], 0, 5, 80, 0)]],
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    def event(a, b, teks, style="Teks", layer=0):
        baris.append(f"Dialogue: {layer},{ass_waktu(a)},{ass_waktu(b)},{style},,0,0,0,,{teks}")

    glow = rf"\blur{4 * s:.0f}" if g["outline"] else ""  # blur tanpa outline = huruf kabur

    def isi_judul(teks):
        jf, jm, jb, js = JUDUL[judul] if judul else ("Georgia", 0, 0, 1.0)
        font_judul = rf"\fn{jf}\i{1 if jm else 0}\b{1 if jb else 0}"
        if "|" in teks:
            # judul 2 baris seperti di referensi: baris kecil + kata besar
            # ("The beauty of|Color Grading", "frames from|Monaco", "The Power of|Colorgrading")
            kecil, besar = (bersih(x.strip(), "asli") for x in teks.split("|", 1))
            if judul == "kartun":
                besar = loncat(besar)
            font_kecil = r"\fnBodoni MT\i1" if judul == "miring" else r"\fnSegoe UI\i0"
            return (rf"{{{font_kecil}\b0\fs{hk['ukuran'] * 0.7 * s:.0f}}}{kecil}\N"
                    rf"{{{font_judul}\fs{hk['ukuran'] * 1.45 * js * s:.0f}}}{besar}")
        if judul:
            t = bersih(teks, "asli")
            return rf"{{{font_judul}\fs{hk['ukuran'] * js * s:.0f}}}" + (loncat(t) if judul == "kartun" else t)
        return bersih(teks, "asli")

    if hook:
        event(0, durasi_hook, rf"{{\fad(250,300){glow}}}" + isi_judul(hook), "Hook")

    # Elemen ala Canva di atas video (waktu = timeline hasil). Semua di luar area subtitle bawah.
    # Gaya diambil dari reels referensi: label kecil berspasi lebar, serif miring untuk kutipan/kata,
    # stempel tanggal oranye ala kamera lama, nomor daftar "01".
    for el in elemen or []:
        a, b, t = el["mulai"], el["selesai"], str(el.get("teks", "")).replace("{", "(").replace("}", ")")
        if not t or b <= a:
            continue
        j = el.get("jenis", "label")
        if j == "judul":
            event(a, b, rf"{{\fad(250,300){glow}}}" + isi_judul(t), "Hook", layer=2)
        elif j == "label":
            event(a, b, r"{\fad(300,300)}" + rf"{{\c{KUNING}}}—  {{\c{KREM}}}" + t.upper(), "Label", layer=2)
        elif j == "kata":
            event(a, b, r"{\fad(80,200)\fscx70\fscy70\t(0,160,\fscx100\fscy100)}" + t, "Kata", layer=2)
        elif j == "daftar":
            nomor, _, isi_ = t.partition(" ") if t[:1].isdigit() else ("", "", t)
            depan = rf"{{\c{KUNING}}}{int(nomor.rstrip('.')):02d}  {{\r}}" if nomor else ""
            event(a, b, r"{\fad(250,250)}" + depan + isi_, "Daftar", layer=2)
        elif j == "kutipan":
            event(a, b, r"{\fad(400,400)}“" + t.strip(" \"'“”") + "”", "Kutipan", layer=2)  # tanda kutip tidak dobel
        elif j == "tanggal":
            event(a, b, r"{\fad(200,200)}" + t.upper(), "Tanggal", layer=2)
        elif j == "penutup":
            event(a, b, r"{\fad(500,0)}" + isi_judul(t), "Penutup", layer=2)

    kata = [k for k in kata if not PENGISI.match(k["w"])]
    potongan = potong_kalimat(kata, maks_kata)
    for i, p in enumerate(potongan):
        a = p[0]["s"]
        # waktu baca: maks 17 huruf/detik, tampil 5/6 s sampai 7 s (Netflix, subtitle bahasa Indonesia)
        huruf = sum(len(k["w"]) + 1 for k in p)
        b = min(max(p[-1]["e"], a + max(5 / 6, huruf / 17)), a + 7)
        if i + 1 < len(potongan):
            berikut = potongan[i + 1][0]["s"]
            if berikut - b < 0.3:
                b = berikut  # tempel ke potongan berikutnya, tidak berkedip
            b = min(b, berikut)
        teks = [bersih(k["w"], g["huruf"]) for k in p]

        if g["efek"] == "sorot":
            # satu event per kata: kata yang sedang diucapkan diberi latar ungu
            for j, k in enumerate(p):
                ka = a if j == 0 else k["s"]
                kb = b if j == len(p) - 1 else p[j + 1]["s"]
                isi = " ".join(
                    (rf"{{\3c{UNGU}\bord{10 * s:.0f}}}{t}{{\r}}" if n == j else t)
                    for n, t in enumerate(teks))
                event(ka, kb, isi)
        elif g["efek"] == "aksen":
            # satu kata kunci (terpanjang, min. 5 huruf) jadi serif miring kuning. Hanya satu dan tanpa
            # membesar: sorotan kata kunci membantu, tapi berlebihan malah mengganggu (Draxler dkk. 2023)
            panjang = max(range(len(teks)), key=lambda n: len(teks[n]))
            isi = [
                (rf"{{\fn{g.get('aksen_font', 'Georgia')}\i1\c{KUNING}}}{t}"
                 rf"{{\fn{g['font']}\i{1 if miring else 0}\c{g['warna']}}}"
                 if n == panjang and len(t) >= 5 else t)
                for n, t in enumerate(teks)]
            if g.get("kotak"):
                # kotak digambar utuh di lapisan bawah (teks polos transparan), teks beraksen di atasnya
                # tanpa kotak; kalau tidak, ganti font di kata aksen membuat kotaknya terbelah
                event(a, b, r"{\fad(180,160)\1a&HFF&}" + " ".join(teks))
                event(a, b, r"{\fad(180,160)\bord0\shad0}" + " ".join(isi), layer=1)
            else:
                event(a, b, rf"{{\fad(180,160)\blur{blur:.0f}}}" + " ".join(isi))
        elif g["efek"] == "glow":
            event(a, b, rf"{{\fad(180,160)\blur{blur:.0f}}}" + " ".join(teks))
        elif g["efek"] == "loncat":
            event(a, b, rf"{{\fad(180,160)\blur{blur:.0f}}}" + loncat(" ".join(teks), seed=i))
        elif g["efek"] == "pop":
            event(a, b, r"{\fscx80\fscy80\t(0,90,\fscx100\fscy100)}" + " ".join(teks))
        else:
            event(a, b, r"{\fad(120,120)}" + " ".join(teks))
    return "\n".join(baris) + "\n"


def pilih_hook(hook):
    if hook != "auto":
        return hook
    daftar = [l.strip() for l in (HERE / "hooks.txt").read_text(encoding="utf-8").splitlines()
              if l.strip() and not l.startswith("#")]
    return random.choice(daftar)


def posisi_wajah(video, bagian, src_w, src_h):
    """Titik tengah subjek (wajah terbesar) per potongan, sebagai pecahan 0..1 dari lebar/tinggi.
    Dipakai supaya crop ke rasio lain (16:9 -> 9:16) mengikuti orangnya, bukan selalu tengah.
    Tanpa OpenCV atau tanpa wajah: tengah (0.5, 0.45)."""
    tengah = (0.5, 0.45)
    try:
        import cv2
        import numpy as np
    except ImportError:
        return [tengah] * len(bagian)
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    lebar = 480
    tinggi = max(2, round(lebar * src_h / src_w / 2) * 2)
    hasil = []
    for a, b in bagian:
        titik = []
        for t in (a + (b - a) * f for f in (0.2, 0.5, 0.8)):
            ss = [] if foto(video) else ["-ss", f"{t:.2f}"]  # foto tidak bisa di-seek
            r = subprocess.run(["ffmpeg", "-v", "error", *ss, "-i", str(video), "-frames:v", "1",
                                "-vf", f"scale={lebar}:{tinggi}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                               capture_output=True, creationflags=TANPA_JENDELA)
            if len(r.stdout) != lebar * tinggi:
                continue
            g = np.frombuffer(r.stdout, np.uint8).reshape(tinggi, lebar)
            wajah = det.detectMultiScale(g, 1.1, 6, minSize=(lebar // 20, lebar // 20))
            if len(wajah):
                x, y, fw, fh = max(wajah, key=lambda f: f[2] * f[3])
                titik.append(((x + fw / 2) / lebar, (y + fh / 2) / tinggi))
        hasil.append(tuple(float(np.median([p[i] for p in titik])) for i in (0, 1)) if titik else None)
    # potongan tanpa wajah ikut potongan terdekat yang ada wajahnya (orangnya biasanya tidak pindah)
    ada = [p for p in hasil if p]
    return [p or (ada[0] if ada else tengah) for p in hasil]


def crop_ikut(w, h, fx, fy, bingkai="isi", warna="", warna_dulu=False):
    """Filter ke ukuran hasil w x h.
    isi: potong bentuk w:h dari sumber dengan subjek (fx, fy) di tengah, lalu perbesar. Dipotong DULU baru
    diperbesar: 16:9 -> 9:16 hanya membesarkan bagian yang dipakai (sebelumnya seluruh gambar, 3x lebih banyak).
    letterbox: gambar utuh selebar layar dengan bingkai hitam atas-bawah (gaya film di banyak reels estetik).
    warna: filter warna per piksel; warna_dulu = dikerjakan sebelum diperbesar (lebih sedikit piksel)."""
    awal, akhir = (f",{warna}", "") if warna and warna_dulu else ("", f",{warna}" if warna else "")
    if bingkai == "letterbox":  # bingkai hitam ditambah SETELAH grading (pad_bingkai) supaya tetap hitam pekat
        return f"null{awal},scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1{akhir}"
    r = w / h
    return (f"crop='trunc(min(iw,ih*{r:.5f})/2)*2':'trunc(min(ih,iw/{r:.5f})/2)*2':"
            f"'min(max(iw*{fx:.3f}-ow/2,0),iw-ow)':'min(max(ih*{fy:.3f}-oh*0.42,0),ih-oh)'"
            f"{awal},scale={w}:{h},setsar=1{akhir}")


def pad_bingkai(w, h, bingkai):
    return f",pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black" if bingkai == "letterbox" else ""


def area_gambar(src_w, src_h, w, h, bingkai):
    """(atas, bawah) bagian layar yang berisi gambar; dipakai untuk menaruh teks di bingkai hitam."""
    if bingkai != "letterbox":
        return None
    tinggi = min(h, round(w * src_h / src_w))
    return ((h - tinggi) / 2, (h + tinggi) / 2) if tinggi < h - 40 else None


SUARA_HALUS = ("highpass=f=70,afftdn=nr=8:nf=-40:tn=1,"
               "acompressor=threshold=-18dB:ratio=2:attack=10:release=200:makeup=1")


def loudnorm_linear(sumber, proses, target=-14):
    """Tahap 1: ukur kerasnya suara (setelah dibersihkan). Tahap 2 (dipakai di render): satu penguatan
    tetap ke target. Kalau pengukuran gagal, pakai loudnorm biasa."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(sumber), "-vn", "-af",
                        f"{proses},loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=TANPA_JENDELA)
    try:
        j = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
        return (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:"
                f"measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:"
                f"offset={j['target_offset']}:linear=true")
    except (ValueError, KeyError):
        return f"loudnorm=I={target}:TP=-1.5:LRA=11"


# efek per potongan, dipasang setelah gambar dijadikan ukuran hasil (getar: sebelumnya, karena memotong tepi)
EFEK = {
    "blur": "gblur=sigma=14",
    "hitamputih": "hue=s=0,eq=contrast=1.08",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "vhs": "rgbashift=rh=-4:bh=4,noise=alls=16:allf=t,eq=saturation=0.8:contrast=1.05",
    "glow": "split[ga][gb];[gb]gblur=sigma=18[gc];[ga][gc]blend=all_mode=lighten:all_opacity=0.45",
    "cermin": "hflip",
    "getar": "crop=trunc(iw*0.94/2)*2:trunc(ih*0.94/2)*2:'(iw-ow)/2*(1+sin(t*31))':'(ih-oh)/2*(1+sin(t*23))'",
}
NAMA_EFEK = {"": "Tanpa efek", "blur": "Blur", "hitamputih": "Monokrom", "sepia": "Sepia", "vhs": "VHS", "glow": "Glow",
             "cermin": "Cermin", "getar": "Getar"}
# transisi di sambungan, tanpa mengubah panjang video: gambar meredup ke hitam/putih, atau buram sebentar
NAMA_TRANSISI = {"potong": "Potong langsung", "fade": "Pudar hitam", "flash": "Kilat putih", "blur": "Blur"}


def atempo(k):
    """atempo hanya menerima 0.5..2 per tahap: kecepatan lain dirangkai."""
    tahap = []
    while k > 2:
        tahap.append("atempo=2")
        k /= 2
    while k < 0.5:
        tahap.append("atempo=0.5")
        k /= 0.5
    return ",".join(tahap + [f"atempo={k:.4f}"])


def transisi_filter(jenis, sisi, panjang):
    """Filter transisi untuk awal ("masuk") atau akhir ("keluar") potongan sepanjang `panjang` detik."""
    d = 0.25
    st = 0.0 if sisi == "masuk" else max(0.0, panjang - d)
    if jenis in ("fade", "flash"):
        warna = ":c=white" if jenis == "flash" else ""
        return f",fade=t={'in' if sisi == 'masuk' else 'out'}:st={st:.4f}:d={d if jenis == 'fade' else 0.15}{warna}"
    if jenis == "blur":  # dua tingkat blur (paling buram tepat di sambungan) supaya terasa memudar
        if sisi == "masuk":
            dekat, jauh = "lt(t,0.12)", f"lt(t,{d})"
        else:
            dekat, jauh = f"gte(t,{panjang - 0.12:.4f})", f"gte(t,{st:.4f})"
        return f",gblur=sigma=24:enable='{dekat}',gblur=sigma=9:enable='{jauh}'"
    return ""


def render(video, keluar, bagian, ass_path, gaya, w, h, lut, potong, src_w, src_h, musik=None, grade=None,
           atur=None, suara=None, zoom=None, bingkai="isi", transisi=None, stabil=True, kata=None,
           kec=None, efek=None, vol_suara=1.0, vol_musik=1.0):
    g = GAYA[gaya]
    if stabil:  # hanya video yang benar-benar goyang yang diganti versi stabil; suara tetap dari aslinya
        try:
            video = peningkat.stabilkan(video, log=lambda s: print(s, flush=True))
        except (subprocess.CalledProcessError, ImportError, OSError) as e:
            print(f"[stabil] dilewati: {e}", flush=True)
    masukan, rantai = [], []
    kec = kec or [1.0] * len(bagian)
    efek = efek or [""] * len(bagian)
    # panjang tiap potongan di hasil (kecepatan diubah = lebih pendek/panjang), dibulatkan ke kisi 30 fps
    panjang = [round((b - a) / k * 30) / 30 if abs(k - 1) > 1e-3 else b - a for (a, b), k in zip(bagian, kec)]
    # crop mengikuti wajah hanya perlu kalau bentuk berubah cukup banyak (mis. 16:9 -> 9:16)
    ubah_bentuk = abs(src_w / src_h - w / h) > 0.15 and bingkai != "letterbox"
    wajah = posisi_wajah(video, bagian, src_w, src_h) if ubah_bentuk else [(0.5, 0.5)] * len(bagian)

    # Warna: bagian per piksel dibakar jadi satu LUT dan dikerjakan di tiap potongan; kalau potongan sumbernya
    # lebih kecil dari hasil (mis. 16:9 -> 9:16), dikerjakan sebelum diperbesar. Vignette/grain/glow di akhir.
    if lut:  # salin ke folder kerja supaya path Windows tidak perlu di-escape
        (ass_path.parent / "warna.cube").write_bytes(Path(lut).read_bytes())
    warna = "lut3d=warna.cube" if lut else WARNA[grade] if grade else g["grade"]
    tambahan = atur_filter(atur or {})
    if tambahan:
        warna = f"{warna},{tambahan}"
    piksel, ruang = pisah_warna(warna)
    piksel = jadikan_lut(piksel, ass_path.parent) if piksel else ""
    ruang = jadikan_lut(ruang, ass_path.parent) if ruang else ""
    luas = min(src_w, src_h * w / h) * min(src_h, src_w * h / w) if bingkai != "letterbox" else src_w * src_h

    def potong_bentuk(fx, fy, k=1.0):
        return crop_ikut(w, h, fx, fy, bingkai, piksel, luas / (k * k) < w * h)

    if potong:
        # Potongan boleh tidak urut (cold open). Potongan yang maju berurutan dibaca dari satu input;
        # tiap kali waktunya mundur dibuka input baru dengan -ss, supaya ffmpeg tidak menyimpan
        # banyak frame di memori.
        runtun = []
        for i, (a, b) in enumerate(bagian):
            if runtun and a >= runtun[-1][-1][2] - 1e-3:
                runtun[-1].append((i, a, b))
            else:
                runtun.append([(i, a, b)])
        for r in runtun:
            mulai = r[0][1]
            vi = masukan.count("-i")
            masukan += ["-ss", f"{mulai:.3f}", "-i", str(video)]
            ai = vi
            if suara:  # suara dari rekaman terpisah yang sudah disejajarkan
                ai = vi + 1
                masukan += ["-ss", f"{mulai:.3f}", "-i", str(suara)]
            for i, a, b in r:
                # zoom: dari rencana edit, atau bawaannya potongan ganjil 8% (punch-in) supaya jump cut
                # terasa seperti ganti angle. setsar=1: concat menolak segmen yang SAR-nya beda.
                k = zoom[i] if zoom else (1.08 if i % 2 else 1.0)
                fx, fy = wajah[i]
                # zoom ke arah wajah (bukan selalu tengah), lalu crop ke bentuk hasil mengikuti wajah
                z = (f",crop=trunc(iw/{k:.3f}/2)*2:trunc(ih/{k:.3f}/2)*2:"
                     f"'min(max(iw*{fx:.3f}-ow/2,0),iw-ow)':'min(max(ih*{fy:.3f}-oh/2,0),ih-oh)'"
                     if k > 1.001 else "")
                if efek[i] == "getar":
                    z += "," + EFEK["getar"]
                z += "," + potong_bentuk(fx, fy, k)
                # Batas potong dibulatkan ke kisi frame 30 fps, dan video dijadikan 30 fps dulu: panjang
                # potongan video dan audio jadi persis sama. Kalau tidak, tiap sambungan menggeser suara
                # beberapa ms dan setelah banyak potongan bibir tidak lagi pas dengan suara.
                x, y = round((a - mulai) * 30) / 30, round((b - mulai) * 30) / 30
                L, k = panjang[i], kec[i]
                cepat, cepat_a = "", ""
                if abs(k - 1) > 1e-3:  # video dan suara dipercepat/diperlambat bersama, panjangnya dikunci ke L
                    cepat = f",setpts=PTS/{k:.4f},fps=30,trim=duration={L:.4f}"
                    cepat_a = f",{atempo(k)},apad,atrim=duration={L:.4f}"
                fx_ = EFEK.get(efek[i]) if efek[i] != "getar" else None
                if fx_ and ";" in fx_:  # efek dengan cabang (glow): label dibuat unik per potongan
                    fx_ = (f"[p{i}];[p{i}]format=gbrp,{fx_.replace('[g', f'[g{i}')},format=yuv420p[q{i}];[q{i}]null")
                    z += fx_
                elif fx_:
                    z += "," + fx_
                # transisi di sambungan: potongan sebelumnya keluar, potongan ini masuk (durasi tidak berubah)
                if transisi and i > 0:
                    z += transisi_filter(transisi[i], "masuk", L)
                if transisi and i + 1 < len(bagian):
                    z += transisi_filter(transisi[i + 1], "keluar", L)
                # fade audio 30 ms di ujung yang benar-benar dipotong supaya tidak berbunyi "klik". Potongan yang
                # bersambung langsung (hanya ganti bingkai) tidak di-fade: suaranya harus mengalir tanpa dip.
                nyambung = lambda j: (0 < j < len(bagian) and abs(bagian[j][0] - bagian[j - 1][1]) < 1e-3
                                      and abs(kec[j] - 1) < 1e-3 and abs(kec[j - 1] - 1) < 1e-3)
                fade_a = ("" if nyambung(i) else ",afade=t=in:d=0.03") + \
                         ("" if nyambung(i + 1) else f",afade=t=out:st={max(0.0, L - 0.03):.4f}:d=0.03")
                rantai.append(f"[{vi}:v]fps=30,trim={x:.4f}:{y:.4f},setpts=PTS-STARTPTS{cepat}{z}[v{i}];"
                              f"[{ai}:a]atrim={x:.4f}:{y:.4f},asetpts=PTS-STARTPTS{cepat_a}{fade_a}[a{i}]")
        urut = "".join(f"[v{i}][a{i}]" for i in range(len(bagian)))
        rantai.append(f"{urut}concat=n={len(bagian)}:v=1:a=1[vc][ac]")
        sumber_v, sumber_a = "[vc]", "[ac]"
    else:
        masukan = ["-ss", "0", "-i", str(video)] + (["-ss", "0", "-i", str(suara)] if suara else [])
        rantai.append(f"[0:v]{potong_bentuk(*wajah[0])}[vk]")
        sumber_v, sumber_a = "[vk]", "[1:a]" if suara else "[0:a]"

    fonts = FONTS_DIR.replace(":", "\\:")
    ukur_ulang = (f"scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2"
                  if bingkai == "letterbox" else
                  f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}")
    # akhir video memudar ke hitam 0.6 s (teks penutup tetap terlihat di atasnya), suara ikut mengecil
    total = sum(panjang)
    pudar = f",fade=t=out:st={max(0.0, total - 0.6):.3f}:d=0.6" if total > 3 else ""
    rantai.append(
        f"{sumber_v}{ukur_ulang},setsar=1,fps=30{',' + ruang if ruang else ''}"
        f"{pad_bingkai(w, h, bingkai)}{pudar},subtitles={ass_path.name}:fontsdir='{fonts}'[vo]")
    # Audio jelek membuat isi yang sama dinilai kurang kredibel (Newman & Schwarz 2018):
    # buang dengung rendah, kurangi desis, ratakan volume suara. Sengaja halus: penghilang desis yang kuat
    # dan kompresor/normalisasi dinamis membuat suara terdengar "kaleng" dan naik-turun.
    # kekuatan pembersih diukur dari rekamannya (peningkat.py); gagal ukur -> setelan halus bawaan
    try:
        proses, ukur = peningkat.rantai_suara(suara or video, kata)
        print(f"[suara] {ukur}", flush=True)
    except Exception:
        proses = SUARA_HALUS
    bersihkan = f"{sumber_a}{proses}"
    # volume -14 LUFS dengan satu penguatan tetap (loudnorm 2 tahap, linear) lalu limiter: tidak ada
    # efek "memompa", dan puncak tidak lewat -1.5 dB (tidak pecah)
    # afftdn menunda suara 25 ms dan alimiter 5 ms (diukur): 30 ms pertama dibuang supaya bibir tetap pas
    akhir = (f"{loudnorm_linear(suara or video, proses)},volume={vol_suara:.2f},alimiter=limit=0.84:level=false,"
             f"atrim=start=0.030,asetpts=PTS-STARTPTS,apad=pad_dur=0.030"
             + (f",afade=t=out:st={max(0.0, total - 0.6):.3f}:d=0.6" if pudar else "") + ",aresample=48000[ao]")
    if musik:
        # musik ~14 LU di bawah suara (riset: minimal ~10 LU) dan mengecil lagi saat kamu bicara
        idx_musik = masukan.count("-i")
        masukan += ["-stream_loop", "-1", "-i", str(Path(musik).resolve())]
        rantai.append(bersihkan + ",asplit=2[sv][sk]")
        # ada ucapan: musik jauh di bawah suara; tanpa ucapan (b-roll/montage): musik jadi suara utama
        bicara = len(kata or []) > 10
        rantai.append(f"[{idx_musik}:a]loudnorm=I={-30 if bicara else -17},volume={vol_musik:.2f},afade=t=in:d=1.5,"
                      f"afade=t=out:st={max(0.0, total - 2):.2f}:d=2[m]")
        rantai.append("[m][sk]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[md]")
        rantai.append(f"[sv][md]amix=inputs=2:duration=first:normalize=0,{akhir}")
    else:
        rantai.append(f"{bersihkan},{akhir}")

    skrip = ass_path.with_suffix(".filter")
    skrip.write_text(";\n".join(rantai), encoding="utf-8")
    print("[render] menyusun video akhir", flush=True)
    jalankan_progres(["ffmpeg", "-y", "-v", "error", *masukan, "-/filter_complex", skrip.name,
              "-map", "[vo]", "-map", "[ao]", *enkoder(18), "-maxrate", "12M", "-bufsize", "24M",
              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
              str(keluar)], total, cwd=ass_path.parent)


def ukuran_keluar(src_w, src_h, rasio):
    if rasio == "asli":  # sisi pendek jadi 1080, bentuk video tidak diubah
        k = 1080 / min(src_w, src_h)
        return round(src_w * k / 2) * 2, round(src_h * k / 2) * 2
    return RASIO[rasio]


def pratinjau(video, keluar, t, gaya, warna, judul, hook, atur, w, h, cache, kualitas=3, bingkai="isi"):
    """Satu gambar preview di detik t: tanpa potong hening; transkrip dipakai kalau sudah ada di cache.
    Untuk foto ini sekaligus hasil akhirnya: hook jadi judul yang menempel di foto."""
    kata = json.loads(Path(cache).read_text(encoding="utf-8")) if cache and Path(cache).exists() else []
    gambar = foto(video)
    if gambar:
        t = 1.0  # hook tampil 0-3 s dengan fade masuk; di detik 1 sudah penuh
    grade = WARNA[warna] if warna else GAYA[gaya]["grade"]
    tambahan = atur_filter(atur)
    sw, sh, _ = info_video(video)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "teks.ass").write_text(
            buat_ass(kata, gaya, w, h, hook, 3.0, judul, area=area_gambar(sw, sh, w, h, bingkai)), encoding="utf-8")
        fonts = FONTS_DIR.replace(":", "\\:")
        fx, fy = (posisi_wajah(video, [(t, t + 0.1)], sw, sh)[0]
                  if abs(sw / sh - w / h) > 0.15 and bingkai != "letterbox"
                  else (0.5, 0.5))  # sama dengan render: crop mengikuti wajah
        vf = (f"{crop_ikut(w, h, fx, fy, bingkai)},{grade},"
              + (f"{tambahan}," if tambahan else "")
              + f"setpts=PTS+{t}/TB{pad_bingkai(w, h, bingkai)},subtitles=teks.ass:fontsdir='{fonts}'")
        jalankan(["ffmpeg", "-y", "-v", "error", *([] if gambar else ["-ss", str(t)]), "-i", str(video),
                  "-vf", vf, "-frames:v", "1", "-update", "1", "-q:v", str(kualitas), str(keluar)], cwd=tmp)


def edit_foto(path, a, daftar_gaya, daftar_warna, hook):
    """Foto: grade + koreksi + judul (hook), satu JPG per kombinasi gaya x warna."""
    src_w, src_h, _ = info_video(path)
    w, h = ukuran_keluar(src_w, src_h, a.rasio)
    atur = atur_otomatis(path) if a.atur == "auto" else json.loads(a.atur)
    kombinasi = [(g, wr) for g in daftar_gaya for wr in daftar_warna]
    for gaya, warna in kombinasi:
        nama = f"{gaya}_{warna}" if warna else gaya
        keluar = (a.keluar if a.keluar and len(kombinasi) == 1
                  else path.with_name(f"{path.stem}_edit_{nama}.jpg")).resolve()
        pratinjau(path, keluar, 0, gaya, warna or None, a.judul, hook, atur, w, h, "", kualitas=1)
        print(f"[selesai] {keluar}", flush=True)


def siapkan_video(klip):
    """Satu klip dipakai apa adanya; beberapa klip digabung dulu (hasil gabungan dipakai ulang)."""
    video = klip[0]
    if len(klip) > 1:
        # nama memuat hash urutan + waktu ubah klip: urutan/isi berubah = file gabungan baru,
        # urutan sama = pakai ulang (render ulang gabungan itu lambat)
        import hashlib
        kunci = "|".join(f"{k}:{k.stat().st_mtime_ns}" for k in klip)
        video = klip[0].with_name(f"{klip[0].stem}_gabungan_{hashlib.md5(kunci.encode()).hexdigest()[:8]}.mp4")
        if not video.exists():
            gabung(klip, video)
        print(f"[gabung] {len(klip)} klip -> {video}", flush=True)
    return video


def render_proyek(p, keluar):
    """Render dari file proyek (rencana edit). Bisa dibuat Gemini (sutradara.py), UI, atau diedit tangan.
    Kunci: sumber, audio, musik, rasio, bahasa, gaya, warna, judul, hook, durasi_hook, atur ("auto" boleh),
    subtitle, potongan [{mulai, selesai, zoom}] (kosong = buang hening otomatis), elemen [{jenis, teks,
    mulai, selesai}] dengan waktu di timeline hasil, lut."""
    video = siapkan_video([Path(x).resolve() for x in p["sumber"]])
    src_w, src_h, durasi = info_video(video)
    w, h = ukuran_keluar(src_w, src_h, p.get("rasio", "asli"))
    audio = Path(p["audio"]).resolve() if p.get("audio") else None
    cache = video.with_name(video.stem + (f".{audio.stem}" if audio else "") + ".kata.json")
    suara = None
    if audio:
        suara = video.with_name(f"{video.stem}.{audio.stem}.sinkron.wav")
        if not suara.exists():
            siapkan_suara(video, audio, suara, durasi)
    kata = transkrip(suara or video, p.get("bahasa"), cache)

    pot = [x for x in p.get("potongan") or [] if min(durasi, x["selesai"]) - max(0.0, x["mulai"]) > 0.05]
    zoom = transisi = kec = efek = None
    if pot:
        bagian = [(max(0.0, x["mulai"]), min(durasi, x["selesai"])) for x in pot]
        zoom = [float(x.get("zoom", 1.0)) for x in pot]
        transisi = [x.get("transisi", "potong") for x in pot]
        kec = [min(4.0, max(0.25, float(x.get("kecepatan", 1.0)))) for x in pot]
        efek = [x.get("efek", "") if x.get("efek", "") in EFEK else "" for x in pot]
    elif p.get("potong_hening", True) and kata:
        bagian = bagian_dipakai(kata, durasi)
    else:
        bagian = [(0.0, durasi)]
    # efek/kecepatan hanya bisa dipasang lewat jalur potongan
    potong = bagian != [(0.0, durasi)] or any(abs(k - 1) > 1e-3 for k in kec or []) or any(efek or [])
    kata_sumber = kata  # waktu asli: jeda antar kata dipakai untuk mengukur bising
    kata = geser_waktu(kata, bagian, kec) if p.get("subtitle", True) else []
    print(f"[potong] {durasi:.1f}s -> {sum((b - a) / k for (a, b), k in zip(bagian, kec or [1.0] * len(bagian))):.1f}s"
          f" ({len(bagian)} bagian)", flush=True)

    atur = atur_otomatis(video) if p.get("atur") == "auto" else p.get("atur") or {}
    musik_ = p.get("musik")
    if musik_ == "auto":  # pilih dari folder musik/: video bicara -> lagu tenang, tanpa bicara -> lebih ceria
        import musik
        musik_ = musik.pilih("tenang" if len(kata_sumber) > 10 else "ceria")
        print(f"[musik] {Path(musik_).name if musik_ else 'tidak ada lagu'}", flush=True)
    gaya = p.get("gaya", "hangat-kotak")
    bingkai = p.get("bingkai", "isi")  # "letterbox" = gambar utuh + bingkai hitam, teks di bingkai
    with tempfile.TemporaryDirectory() as tmp:
        ass_path = Path(tmp) / "teks.ass"
        ass_path.write_text(buat_ass(kata, gaya, w, h, p.get("hook", ""), p.get("durasi_hook", 3.0),
                                     p.get("judul"), p.get("elemen"), area_gambar(src_w, src_h, w, h, bingkai)),
                            encoding="utf-8")
        print("[render] ...", flush=True)
        render(video, keluar, bagian, ass_path, gaya, w, h, p.get("lut"), potong, src_w, src_h, musik_,
               p.get("warna") or None, atur, suara, zoom, bingkai, transisi, p.get("stabil", True), kata_sumber,
               kec, efek, float(p.get("volume_suara", 1.0)), float(p.get("volume_musik", 1.0)))
    print(f"[selesai] {keluar}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Edit video otomatis untuk IG.")
    ap.add_argument("video", type=Path, nargs="*",
                    help="satu atau beberapa video (digabung berurutan), atau foto (tiap foto diedit sendiri)")
    ap.add_argument("--proyek", type=Path, help="render dari file proyek .json (rencana edit Gemini/UI)")
    ap.add_argument("--gaya", default="hangat-kotak",
                    help=f"{', '.join(GAYA)}; bisa beberapa dipisah koma, 'versi-hangat', atau 'semua'")
    ap.add_argument("--hook", default="", help='teks hook di 3 detik pertama; "auto" = ambil acak dari hooks.txt')
    ap.add_argument("--rasio", choices=RASIO, default="asli", help="asli = bentuk video tidak diubah")
    ap.add_argument("--bahasa", default=None, help="kode bahasa, misal id / en (kosong = deteksi otomatis)")
    ap.add_argument("--tanpa-potong", action="store_true", help="jangan buang bagian hening")
    ap.add_argument("--warna", default="",
                    help=f"color grading: {', '.join(WARNA)}; bisa beberapa dipisah koma, atau 'semua' "
                         "(kosong = grade bawaan gaya)")
    ap.add_argument("--lut", help="file .cube untuk color grade (mengganti grade bawaan gaya)")
    ap.add_argument("--musik", help="file musik latar (mp3/wav) atau 'auto' (pilih dari folder musik/); "
                                    "otomatis pelan dan mengecil saat bicara")
    ap.add_argument("--judul", choices=JUDUL, help="font judul hook: " + ", ".join(JUDUL))
    ap.add_argument("--atur", default="{}",
                    help="pengaturan manual sebagai JSON, misal '{\"eksposur\": 10, \"suhu\": 20}', atau 'auto' "
                         "(diukur dari videonya). Kunci: " + ", ".join(ATUR))
    ap.add_argument("--audio", type=Path, help="suara yang direkam terpisah; disinkronkan otomatis ke video")
    ap.add_argument("--pratinjau", type=float, help="hanya buat 1 gambar preview di detik ini (untuk UI)")
    ap.add_argument("--keluar", type=Path)
    a = ap.parse_args()
    if a.proyek:
        keluar = (a.keluar or a.proyek.with_name(a.proyek.stem.replace(".proyek", "") + "_edit.mp4")).resolve()
        render_proyek(json.loads(a.proyek.read_text(encoding="utf-8-sig")), keluar)  # -sig: file dari Notepad
        return
    if not a.video:
        ap.error("butuh video/foto, atau --proyek")
    atur = {} if a.atur == "auto" else json.loads(a.atur)

    if a.gaya == "semua":
        daftar_gaya = list(GAYA)
    elif a.gaya == "versi-hangat":
        daftar_gaya = [g for g in GAYA if g.startswith("hangat")]
    else:
        daftar_gaya = a.gaya.split(",")
    salah = [g for g in daftar_gaya if g not in GAYA]
    if salah:
        ap.error(f"gaya tidak dikenal: {', '.join(salah)}. Pilihan: {', '.join(GAYA)}, versi-hangat, semua")
    daftar_warna = list(WARNA) if a.warna == "semua" else a.warna.split(",")  # [""] = grade bawaan gaya
    salah = [wr for wr in daftar_warna if wr and wr not in WARNA]
    if salah:
        ap.error(f"warna tidak dikenal: {', '.join(salah)}. Pilihan: {', '.join(WARNA)}, semua")

    klip = [v.resolve() for v in a.video]
    if any(foto(k) for k in klip):
        if not all(foto(k) for k in klip):
            ap.error("jangan campur foto dan video dalam satu perintah")
        hook = pilih_hook(a.hook) if a.hook else ""
        for k in klip:  # tiap foto diedit sendiri-sendiri
            edit_foto(k, a, daftar_gaya, daftar_warna, hook)
        return
    video = siapkan_video(klip)
    src_w, src_h, durasi = info_video(video)
    w, h = ukuran_keluar(src_w, src_h, a.rasio)

    if a.atur == "auto":
        atur = atur_otomatis(video)
        print(f"[atur] otomatis: {atur}", flush=True)

    hook = pilih_hook(a.hook) if a.hook else ""
    nama_cache = video.stem + (f".{a.audio.stem}" if a.audio else "") + ".kata.json"
    cache = video.with_name(nama_cache)

    if a.pratinjau is not None:
        keluar = (a.keluar or video.with_name(f"{video.stem}_pratinjau.jpg")).resolve()
        pratinjau(video, keluar, a.pratinjau, daftar_gaya[0], daftar_warna[0] or None, a.judul, hook, atur,
                  w, h, cache)
        print(f"[selesai] {keluar}", flush=True)
        return

    suara = None
    if a.audio:
        suara = video.with_name(f"{video.stem}.{a.audio.stem}.sinkron.wav")
        geser, yakin = siapkan_suara(video, a.audio.resolve(), suara, durasi)
        if yakin:
            print(f"[audio] disinkronkan, geser {geser:+.2f}s (keyakinan {yakin:.0f})", flush=True)
        else:
            print("[audio] video tanpa suara bawaan, audio dianggap mulai bersamaan", flush=True)

    kata = transkrip(suara or video, a.bahasa, cache)
    print(f"[transkrip] {len(kata)} kata", flush=True)
    if a.musik == "auto":
        import musik
        a.musik = musik.pilih("tenang" if len(kata) > 10 else "ceria")
        print(f"[musik] {Path(a.musik).name if a.musik else 'tidak ada lagu'}", flush=True)

    potong = not a.tanpa_potong and bool(kata)
    bagian = bagian_dipakai(kata, durasi) if potong else [(0.0, durasi)]
    kata_sumber = kata
    kata = geser_waktu(kata, bagian)
    if potong:
        sisa = sum(b - x for x, b in bagian)
        print(f"[potong] {durasi:.1f}s -> {sisa:.1f}s ({len(bagian)} bagian)", flush=True)

    if hook:
        print(f"[hook] {hook}", flush=True)

    kombinasi = [(g, wr) for g in daftar_gaya for wr in daftar_warna]
    for gaya, warna in kombinasi:
        nama = f"{gaya}_{warna}" if warna else gaya
        keluar = (a.keluar if a.keluar and len(kombinasi) == 1
                  else video.with_name(f"{video.stem}_edit_{nama}.mp4")).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            ass_path = Path(tmp) / "teks.ass"
            ass_path.write_text(buat_ass(kata, gaya, w, h, hook, 3.0, a.judul), encoding="utf-8")
            print(f"[render] {nama} ...", flush=True)
            render(video, keluar, bagian, ass_path, gaya, w, h, a.lut, potong, src_w, src_h, a.musik,
                   warna or None, atur, suara, kata=kata_sumber)
        print(f"[selesai] {keluar}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(str(e))
