"""Desain dari foto/video: Koran, Tiket, Polaroid, Majalah, dan Carousel IG.
Foto -> JPG, video -> MP4 (video bergerak di dalam kotaknya, sisanya kertas diam + kamera mendorong pelan).

    python desain.py foto.jpg --gaya koran --judul "Sore yang pelan." --sub "Jalan kaki sampai lampu kota menyala."
    python desain.py video.mp4 --gaya polaroid --teks "sunday walk" --mulai 3 --durasi 6
    python desain.py a.jpg b.jpg c.jpg --gaya carousel --judul "Bandung, 3 hari"

Tiap gaya = satu fungsi tata_<gaya>(data, w, h, gambar_kecil) yang mengembalikan "spec":
latar (RGB), kartu (RGBA, belum diputar), kotak (x, y, w, h) tempat foto di dalam kartu, sudut (derajat,
searah jarum jam), pusat (titik tengah kartu di kanvas), depan (RGBA di atas segalanya, boleh None).
Mau gaya baru: tambah satu fungsi tata_ dan daftarkan di GAYA.
"""
import argparse
import datetime
import hashlib
import json
import math
import random
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import autoedit as ae
import bahan
import poster

F = r"C:\Windows\Fonts"
HURUF = {
    "gotik": f"{F}\\OLDENGL.TTF", "serif": f"{F}\\georgia.ttf", "serif_tebal": f"{F}\\georgiab.ttf",
    "serif_miring": f"{F}\\georgiai.ttf", "koran": f"{F}\\times.ttf", "bodoni": f"{F}\\BOD_B.TTF",
    "bodoni_miring": f"{F}\\BOD_I.TTF", "bodoni_biasa": f"{F}\\BOD_R.TTF", "tangan": f"{F}\\Inkfree.ttf",
    "mesin": f"{F}\\cour.ttf", "mesin_tebal": f"{F}\\courbd.ttf",
}
UKURAN = {"16:9": (1920, 1080), "9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080)}
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
         "November", "Desember"]
ISI_KORAN = Path(__file__).with_name("koran_isi.json")  # isi bawaan potongan koran samping (bisa diedit)


def isi_koran_bawaan():
    try:
        return json.loads(ISI_KORAN.read_text(encoding="utf-8-sig"))["potongan"][:4]
    except (OSError, ValueError, KeyError):
        return [{"judul": "", "isi": ""}] * 4
WARNA_SERASI = {"koran": "matte", "tiket": "vintage", "polaroid": "vintage", "majalah": "film", "carousel": "matte"}


def huruf(nama, ukuran):
    return ImageFont.truetype(HURUF[nama], max(6, round(ukuran)))


def bungkus(d, teks, f, lebar):
    """Pecah teks jadi baris yang muat di lebar (per kata)."""
    baris = []
    for paragraf in str(teks).split("\n"):
        b = ""
        for k in paragraf.split():
            coba = f"{b} {k}".strip()
            if d.textlength(coba, font=f) <= lebar or not b:
                b = coba
            else:
                baris.append(b)
                b = k
        baris.append(b)
    return baris


def tulis_rata(d, x, y, teks, f, lebar, tinggi_baris, warna, maks_y=None):
    """Kolom rata kiri-kanan seperti koran (baris terakhir paragraf rata kiri). Kembalikan y akhir."""
    baris = bungkus(d, teks, f, lebar)
    for i, b in enumerate(baris):
        if maks_y and y + tinggi_baris > maks_y:
            break
        kata = b.split()
        if len(kata) > 1 and i < len(baris) - 1 and d.textlength(b, font=f) > lebar * 0.75:
            sisa = (lebar - sum(d.textlength(k, font=f) for k in kata)) / (len(kata) - 1)
            xx = x
            for k in kata:
                d.text((xx, y), k, font=f, fill=warna)
                xx += d.textlength(k, font=f) + sisa
        else:
            d.text((x, y), b, font=f, fill=warna)
        y += tinggi_baris
    return y


def judul_pas(d, teks, nama_huruf, lebar, ukuran, maks_baris, kecil=0.5):
    """Ukuran huruf terbesar (<= ukuran) supaya teks muat dalam maks_baris."""
    u = ukuran
    while u > ukuran * kecil:
        f = huruf(nama_huruf, u)
        baris = bungkus(d, teks, f, lebar)
        if len(baris) <= maks_baris and all(d.textlength(b, font=f) <= lebar for b in baris):
            return f, baris
        u -= 2
    f = huruf(nama_huruf, u)
    return f, bungkus(d, teks, f, lebar)


def tekstur(img, kuat=6, seed=1):
    """Serat kertas: noise halus yang diam."""
    import numpy as np
    rng = np.random.default_rng(seed)
    a = np.asarray(img).astype(np.int16)
    n = rng.normal(0, kuat, a.shape[:2])[..., None]
    a[..., :3] = np.clip(a[..., :3] + n, 0, 255)
    return Image.fromarray(a.astype(np.uint8), img.mode)


def kertas_sobek(w, h, warna, seed, sobek=(1, 1, 1, 1)):
    """Lembar kertas RGBA dengan tepi bergerigi (sobekan) di sisi yang dipilih (atas, kanan, bawah, kiri)."""
    rnd = random.Random(seed)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    amp = max(3, round(min(w, h) * 0.008))

    def tepi(n, kasar):
        return [(rnd.uniform(0, amp * 2) if kasar else 0) for _ in range(n)]

    langkah = max(4, amp)
    titik = []
    for i, dy in enumerate(tepi(w // langkah + 1, sobek[0])):
        titik.append((i * langkah, dy))
    for i, dx in enumerate(tepi(h // langkah + 1, sobek[1])):
        titik.append((w - 1 - dx, i * langkah))
    for i, dy in enumerate(tepi(w // langkah + 1, sobek[2])):
        titik.append((w - 1 - i * langkah, h - 1 - dy))
    for i, dx in enumerate(tepi(h // langkah + 1, sobek[3])):
        titik.append((dx, h - 1 - i * langkah))
    ImageDraw.Draw(img).polygon(titik, fill=warna)
    return tekstur(img, 5, seed)


def tempel(latar, lembar, cx, cy, sudut, bayangan=0.35, jarak=None):
    """Tempel lembar RGBA (diputar sudut derajat searah jarum jam) dengan bayangan lembut, berpusat di (cx, cy)."""
    putar = lembar.rotate(-sudut, resample=Image.BICUBIC, expand=True)
    x, y = round(cx - putar.width / 2), round(cy - putar.height / 2)
    if bayangan:
        jarak = jarak or max(4, round(min(lembar.size) * 0.012))
        a = putar.split()[3].point(lambda v: round(v * bayangan))
        hitam = Image.new("RGBA", putar.size, (20, 16, 12, 0))
        hitam.putalpha(a)
        hitam = hitam.filter(ImageFilter.GaussianBlur(jarak * 1.6))
        _tempel_bebas(latar, hitam, x + jarak, y + round(jarak * 1.4))
    _tempel_bebas(latar, putar, x, y)


def _tempel_bebas(latar, img, x, y):
    """alpha_composite yang boleh keluar kanvas (sebagian lembar terpotong tepi, seperti foto kolase)."""
    kotak = (max(0, x), max(0, y), min(latar.width, x + img.width), min(latar.height, y + img.height))
    if kotak[0] >= kotak[2] or kotak[1] >= kotak[3]:
        return
    potong = img.crop((kotak[0] - x, kotak[1] - y, kotak[2] - x, kotak[3] - y))
    latar.alpha_composite(potong, (kotak[0], kotak[1]))


def tanggal_hari_ini():
    t = datetime.date.today()
    return f"{BULAN[t.month - 1]} {t.year}"


# ----------------------------------------------------------------------------------------------- KORAN
def halaman_kolom(w, h, judul, isi, seed, gambar=None):
    """Potongan koran di samping: judul + 2-3 kolom teks (opsional gambar halftone)."""
    pg = kertas_sobek(w, h, (236, 233, 227, 255), seed)
    d = ImageDraw.Draw(pg)
    m = round(w * 0.06)
    y = m
    if judul:
        fj, bj = judul_pas(d, judul, "serif_tebal", w - 2 * m, w * 0.11, 2)
        for b in bj:
            d.text((m, y), b, font=fj, fill=(22, 20, 18))
            y += round(fj.size * 1.08)
        d.line((m, y + 6, w - m, y + 6), fill=(30, 28, 26), width=3)
        y += 22
    if gambar is not None:
        gh = round(h * 0.42)
        g = ImageOps.fit(gambar, (w - 2 * m, gh)).convert("L")
        g = ImageOps.autocontrast(g, cutoff=2).convert("1", dither=Image.FLOYDSTEINBERG).convert("L")
        g = Image.merge("RGBA", (g, g, g, Image.new("L", g.size, 255)))
        g = Image.blend(g, Image.new("RGBA", g.size, (236, 233, 227, 255)), 0.35)
        pg.alpha_composite(g, (m, y))
        d.rectangle((m, y, w - m, y + gh), outline=(40, 38, 36), width=2)
        y += gh + 18
    if not isi.strip():
        return pg
    kolom = 3 if w > 420 else 2
    jarak = round(w * 0.035)
    lk = (w - 2 * m - jarak * (kolom - 1)) / kolom
    f = huruf("koran", max(13, w * 0.032))
    tb = round(f.size * 1.22)
    # teks mengalir dari kolom ke kolom seperti koran sungguhan; kolom terakhir boleh menembus tepi bawah
    # (terpotong sobekan kertas, jadi terlihat seperti guntingan asli)
    baris = []
    for p in isi.split("\n"):
        bp = bungkus(d, p, f, lk)
        baris += [(b, i == len(bp) - 1) for i, b in enumerate(bp)]
    muat = max(1, (h - y) // tb)
    asli = list(baris)
    while len(baris) < muat * kolom + 2:  # teks pendek: ulangi supaya kolom penuh sampai terpotong tepi
        baris += asli
    alpha = pg.split()[3]
    for k in range(kolom):
        isi_kolom = baris[k * muat:(k + 1) * muat + (2 if k == kolom - 1 else 0)]
        if not isi_kolom:
            break
        x = m + k * (lk + jarak)
        yy = y
        for b, akhir in isi_kolom:
            kata = b.split()
            if len(kata) > 1 and not akhir:
                sisa = (lk - sum(d.textlength(t, font=f) for t in kata)) / (len(kata) - 1)
                xx = x
                for t in kata:
                    d.text((xx, yy), t, font=f, fill=(34, 32, 30))
                    xx += d.textlength(t, font=f) + sisa
            else:
                d.text((x, yy), b, font=f, fill=(34, 32, 30))
            yy += tb
        if k:
            d.line((x - jarak / 2, y, x - jarak / 2, yy), fill=(150, 146, 140), width=1)
    pg.putalpha(alpha)  # tulisan yang melewati sobekan ikut terpotong
    return pg


def halaman_utama(data, pw, ph, rasio_kotak):
    """Halaman tengah: nama koran (huruf gotik), tempat-tanggal, judul besar, sub miring, kotak foto, keterangan."""
    pg = kertas_sobek(pw, ph, (233, 231, 226, 255), 7, sobek=(1, 1, 0, 1))
    d = ImageDraw.Draw(pg)
    m = round(pw * 0.08)
    lebar = pw - 2 * m
    tinta = (20, 18, 16)
    y = round(pw * 0.06)
    nama = data.get("nama") or "The Quiet Daily"
    fn, _ = judul_pas(d, nama, "gotik", lebar, pw * 0.13, 1)
    d.text((pw / 2, y), nama, font=fn, fill=tinta, anchor="mt")
    y += round(fn.size * 1.12)
    d.line((m, y, pw - m, y), fill=tinta, width=max(2, round(pw * 0.004)))
    fd = huruf("serif_miring", pw * 0.026)
    y += round(pw * 0.012)
    tgl = data.get("tanggal") or datetime.date.today().strftime("%B %Y")
    tempat = data.get("tempat") or ""
    d.text((pw / 2, y), f"{tempat} · {tgl}" if tempat else tgl, font=fd, fill=tinta, anchor="mt")
    y += round(fd.size * 1.5)
    d.line((m, y, pw - m, y), fill=tinta, width=1)
    y += round(pw * 0.04)
    judul = data.get("judul") or "Hari ini layak dicatat."
    fj, bj = judul_pas(d, judul, "serif_tebal", lebar, pw * 0.085, 3)
    for b in bj:
        d.text((m, y), b, font=fj, fill=tinta)
        y += round(fj.size * 1.12)
    sub = data.get("sub") or ""
    if sub:
        y += round(pw * 0.01)
        fs, bs = judul_pas(d, sub, "serif_miring", lebar, pw * 0.036, 2)
        for b in bs:
            d.text((m, y), b, font=fs, fill=(40, 38, 36))
            y += round(fs.size * 1.25)
    y += round(pw * 0.03)
    ket = data.get("keterangan") or ""
    sisa = ph - y - round(pw * (0.12 if ket else 0.07))
    kw = lebar
    kh = min(sisa, round(kw / rasio_kotak)) if rasio_kotak else sisa
    kotak = (m, y, kw, max(40, kh))
    d.rectangle((m - 3, y - 3, m + kw + 2, y + kh + 2), outline=(60, 58, 55), width=2)
    if ket:
        fk = huruf("serif_miring", pw * 0.028)
        d.text((pw / 2, y + kh + round(pw * 0.03)), ket, font=fk, fill=(40, 38, 36), anchor="mt")
    return pg, kotak


def tata_koran(data, w, h, gambar_kecil):
    rnd = random.Random(3)
    latar = bahan.buat("beton", w, h, 2, warna=(204, 201, 196))
    # isi potongan samping: dari data["potongan"] (diedit di aplikasi), kosong -> koran_isi.json
    bawaan = isi_koran_bawaan()
    pot = list(data.get("potongan") or [])
    pot = [{**bawaan[i], **{k: v for k, v in (pot[i] if i < len(pot) else {}).items() if v is not None}}
           for i in range(4)]
    # posisi tiap potongan: (lebar, tinggi, x, y, sudut) relatif kanvas; sebagian sengaja keluar tepi
    if h <= w:
        letak = [(0.30, 0.78, 0.11, 0.38, -1.5), (0.27, 0.30, 0.13, 0.93, -4),
                 (0.27, 0.42, 0.86, 0.10, 3), (0.27, 0.62, 0.87, 0.55, 2)]
        pw, ph = round(w * 0.45), round(h * 1.0)
        pusat, sudut = (w * 0.5, h * 0.54), -0.8
    else:
        letak = [(0.62, 0.22, 0.22, 0.04, -3), (0.60, 0.20, 0.84, 0.97, -3),
                 (0.60, 0.20, 0.82, 0.07, 4), (0.66, 0.20, 0.25, 0.95, 3)]
        pw, ph = round(w * 0.86), round(h * 0.80)
        pusat, sudut = (w * 0.5, h * 0.53), 0.8
    for i, (p, (lw, lh, fx, fy, sd)) in enumerate(zip(pot, letak)):
        g = gambar_kecil if p.get("gambar") else None
        lembar = halaman_kolom(round(w * lw), round(h * lh), p.get("judul", ""), p.get("isi", ""), 11 + i, g)
        tempel(latar, lembar, w * fx, h * fy, sd + rnd.uniform(-0.5, 0.5), 0.3)
    data = {**data, "judul": data.get("judul") or "Some days are worth the front page."}
    kartu, kotak = halaman_utama(data, pw, ph, None)
    return {"latar": latar, "kartu": kartu, "kotak": kotak, "sudut": sudut, "pusat": pusat, "depan": None,
            "dorong": True}


# ----------------------------------------------------------------------------------------------- TIKET
def tata_tiket(data, w, h, gambar_kecil):
    latar = bahan.buat("kayu", w, h, 4, gelap=(46, 32, 24), terang=(92, 64, 46))
    tw = round(min(w * 0.80, h * 0.48))
    th = round(tw * 1.85)
    if th > h * 0.9:
        th = round(h * 0.9)
        tw = round(th / 1.85)
    krem, tinta, aksen = (242, 234, 218, 255), (43, 37, 33), (176, 82, 58)
    kartu = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(kartu)
    r = round(tw * 0.04)
    d.rounded_rectangle((0, 0, tw - 1, th - 1), r, fill=krem)
    m = round(tw * 0.07)
    # kotak foto di atas
    kotak = (m, m, tw - 2 * m, round(th * 0.43))
    y = kotak[1] + kotak[3] + round(tw * 0.05)
    fl = huruf("mesin_tebal", tw * 0.034)
    d.text((m, y), (data.get("label") or "ADMIT ONE").upper(), font=fl, fill=aksen)
    d.text((tw - m, y), f"No. {int(hashlib.md5(str(data).encode()).hexdigest()[:6], 16) % 99999:05d}",
           font=fl, fill=tinta, anchor="ra")
    y += round(fl.size * 1.9)
    u = tw * 0.14  # judul huruf condensed tebal, sebesar mungkin dalam 2 baris
    while True:
        fj = poster.font(round(u), "Bold Condensed")
        bj = bungkus(d, (data.get("judul") or "Hari Baik").upper(), fj, tw - 2 * m)
        if len(bj) <= 2 or u < tw * 0.06:
            break
        u -= 3
    for b in bj:
        d.text((m - 2, y), b, font=fj, fill=tinta)
        y += round(fj.size * 0.98)
    y += round(tw * 0.03)
    # kisi info: label kecil di atas, isi di bawah (2 kolom)
    info = [("TANGGAL", data.get("tanggal") or datetime.date.today().strftime("%d.%m.%Y")),
            ("JAM", data.get("jam") or "19:30"), ("TEMPAT", data.get("tempat") or "—"),
            ("KURSI", data.get("kursi") or "A 12")]
    flb, fis = huruf("mesin", tw * 0.028), poster.font(round(tw * 0.052), "SemiCondensed")
    kol = (tw - 2 * m) / 2
    for i, (lb, isi) in enumerate(info):
        x = m + (i % 2) * kol
        yy = y + (i // 2) * round(tw * 0.13)
        d.text((x, yy), lb, font=flb, fill=(120, 108, 96))
        d.text((x, yy + flb.size * 1.3), str(isi).upper(), font=fis, fill=tinta)
    # garis sobek (perforasi) dengan takik setengah lingkaran di kiri-kanan, lalu sobekan bawah
    yp = round(th * 0.80)
    rr = round(tw * 0.045)
    for cx in (0, tw):
        d.ellipse((cx - rr, yp - rr, cx + rr, yp + rr), fill=(0, 0, 0, 0))
    for x in range(rr + 6, tw - rr - 6, 16):
        d.line((x, yp, x + 8, yp), fill=(150, 138, 124), width=2)
    fs = huruf("mesin_tebal", tw * 0.04)
    d.text((m, yp + rr + round(tw * 0.02)), (data.get("label") or "ADMIT ONE").upper(), font=fs, fill=tinta)
    # "barcode" dari judul (selalu sama untuk judul yang sama)
    bit = bin(int(hashlib.sha1((data.get("judul") or "").encode()).hexdigest(), 16))[2:]
    x, yb, hb = m, yp + rr + round(tw * 0.085), round(th * 0.07)
    for i, c in enumerate(bit):
        if x > tw - m:
            break
        lebar = 3 if c == "1" else 1
        d.rectangle((x, yb, x + lebar, yb + hb), fill=tinta)
        x += lebar + 2
    kartu = tekstur(kartu, 4, 9)
    return {"latar": latar, "kartu": kartu, "kotak": kotak, "sudut": -3.0, "pusat": (w / 2, h / 2), "depan": None,
            "dorong": False}


# -------------------------------------------------------------------------------------------- POLAROID
def selotip(w, h, seed):
    return kertas_sobek(w, h, (232, 222, 196, 165), seed, sobek=(0, 1, 0, 1))


def tata_polaroid(data, w, h, gambar_kecil):
    latar = bahan.buat("linen", w, h, 5, warna=(206, 194, 176))
    pw = round(min(w * 0.78, h * 0.56))
    tepi = round(pw * 0.06)
    kw = pw - 2 * tepi
    kh = kw  # foto persegi seperti film instan
    ph = tepi + kh + round(pw * 0.26)
    kartu = tekstur(Image.new("RGBA", (pw, ph), (247, 245, 239, 255)), 3, 6)
    d = ImageDraw.Draw(kartu)
    teks = data.get("teks") or data.get("judul") or ""
    if teks:
        ft, bt = judul_pas(d, teks, "tangan", pw - 2 * tepi, pw * 0.085, 2)
        y = tepi + kh + round((ph - tepi - kh - len(bt) * ft.size * 1.1) / 2)
        for b in bt:
            d.text((pw / 2, y), b, font=ft, fill=(48, 44, 52), anchor="mt")
            y += round(ft.size * 1.1)
    if data.get("tanggal"):
        fk = huruf("tangan", pw * 0.04)
        d.text((pw - tepi, ph - tepi * 0.6), data["tanggal"], font=fk, fill=(110, 100, 96), anchor="rb")
    sudut = 2.5
    depan = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tempel(depan, selotip(round(pw * 0.36), round(pw * 0.09), 3), w / 2, h / 2 - ph / 2 + pw * 0.01, -4, 0)
    return {"latar": latar, "kartu": kartu, "kotak": (tepi, tepi, kw, kh), "sudut": sudut, "pusat": (w / 2, h / 2),
            "depan": depan, "dorong": False}


# --------------------------------------------------------------------------------------------- MAJALAH
def tata_majalah(data, w, h, gambar_kecil):
    import numpy as np
    kartu = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    depan = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # gradasi tipis atas & bawah supaya tulisan selalu terbaca
    a = np.zeros((h, 1), np.float32)
    t = np.linspace(0, 1, h)[:, None]
    a += np.clip(1 - t / 0.28, 0, 1) ** 1.6 * 110 + np.clip((t - 0.62) / 0.38, 0, 1) ** 1.6 * 150
    depan.putalpha(Image.fromarray(np.repeat(a, w, 1).astype(np.uint8)))
    depan = Image.alpha_composite(Image.new("RGBA", (w, h), (0, 0, 0, 0)),
                                  Image.merge("RGBA", (*Image.new("RGB", (w, h), (18, 14, 12)).split(),
                                                       depan.split()[3])))
    d = ImageDraw.Draw(depan)
    putih, krem = (250, 247, 240), (240, 214, 160)
    m = round(w * 0.06)
    nama = (data.get("nama") or "HANGAT").upper()
    fn, _ = judul_pas(d, nama, "bodoni", w - 2 * m, w * 0.24, 1, 0.3)
    d.text((w / 2, m * 0.7), nama, font=fn, fill=putih, anchor="mt")
    ft = huruf("bodoni_biasa", w * 0.024)
    edisi = f"EDISI {(data.get('tanggal') or tanggal_hari_ini()).upper()}"
    y_bawah_nama = m * 0.7 + fn.getbbox(nama)[3] + w * 0.012
    d.text((w / 2, y_bawah_nama), edisi, font=ft, fill=putih, anchor="mt")
    # baris sampul di kiri (judul utama besar + cerita kecil), kutipan miring di bawah
    y = h * 0.62
    judul = data.get("judul") or "Hari yang pelan"
    fj, bj = judul_pas(d, judul, "bodoni", w * 0.62, w * 0.1, 3)
    for b in bj:
        d.text((m, y), b, font=fj, fill=putih)
        y += round(fj.size * 1.02)
    y += w * 0.02
    fc = huruf("bodoni_biasa", w * 0.032)
    for baris in [x for x in str(data.get("cerita") or data.get("sub") or "").split("|") if x.strip()][:3]:
        d.text((m, y), "— " + baris.strip(), font=fc, fill=krem)
        y += round(fc.size * 1.45)
    if data.get("kutipan"):
        fk = huruf("bodoni_miring", w * 0.04)
        bk = bungkus(d, f"“{data['kutipan']}”", fk, w * 0.42)
        yk = h - m - len(bk) * fk.size * 1.2
        for b in bk:
            d.text((w - m, yk), b, font=fk, fill=putih, anchor="ra")
            yk += round(fk.size * 1.2)
    latar = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    return {"latar": latar, "kartu": kartu, "kotak": (0, 0, w, h), "sudut": 0.0, "pusat": (w / 2, h / 2),
            "depan": depan, "dorong": True}


GAYA = {"koran": tata_koran, "tiket": tata_tiket, "polaroid": tata_polaroid, "majalah": tata_majalah}
RASIO_BAWAAN = {"koran": "16:9", "tiket": "9:16", "polaroid": "4:5", "majalah": "4:5"}


# ---------------------------------------------------------------------------------------- PERAKITAN
def filter_media(media, kw, kh, crop, waktu, sw, sh, grade, atur):
    """Sama dengan poster: buang bingkai hitam, isi kotak, potong di titik pilihan (wajah/otomatis), grade."""
    if "x" not in crop or "y" not in crop:
        crop = {**poster.titik_otomatis(media, waktu, sw, sh, kw / kh), **crop}
    z = max(1.0, min(3.0, float(crop.get("zoom", 1.0))))
    tambahan = ae.atur_filter(atur or {})
    return (poster.tanpa_bingkai(media, waktu, sw, sh) +
            f"scale={kw}*{z:.3f}:{kh}*{z:.3f}:force_original_aspect_ratio=increase,"
            f"crop={kw}:{kh}:'min(max(iw*{crop['x']:.3f}-{kw}/2,0),iw-{kw})':"
            f"'min(max(ih*{crop['y']:.3f}-{kh}/2,0),ih-{kh})',setsar=1,{grade}" + (f",{tambahan}" if tambahan else ""))


def ambil_gambar(media, t, vf=None, lebar=None):
    """Satu frame (atau foto) sebagai PIL RGB, opsional lewat filter vf."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "f.png"
        f = vf or (f"scale={lebar}:-2" if lebar else "null")
        ae.jalankan(["ffmpeg", "-y", "-v", "error", *([] if ae.foto(media) else ["-ss", f"{t:.3f}"]),
                     "-i", str(media), "-vf", f, "-frames:v", "1", str(out)])
        return Image.open(out).convert("RGB")


def buat_desain(media, keluar, data, gaya="koran", rasio=None, mulai=0.0, durasi=None, warna="serasi",
                atur=None, crop=None, pratinjau=False):
    media, keluar = Path(media), Path(keluar)
    w, h = UKURAN[rasio or RASIO_BAWAAN[gaya]]
    sw, sh, total = ae.info_video(media)
    gambar = ae.foto(media)
    if not gambar:
        durasi = min(durasi or total - mulai, total - mulai)
    waktu = [0] if gambar else [mulai + durasi * f for f in (0.2, 0.5, 0.8)]
    if warna == "serasi":
        grade = ae.WARNA[WARNA_SERASI[gaya]]
        atur = atur or ae.atur_otomatis(media)
    else:
        grade = ae.WARNA.get(warna or "asli", "null")
    kecil = ambil_gambar(media, waktu[len(waktu) // 2], lebar=480)
    spec = GAYA[gaya](data, w, h, kecil)
    # satu kotak foto, atau beberapa (strip photobooth, film, dll): video -> tiap kotak momen berbeda,
    # foto -> tiap kotak potongan/zoom berbeda. spec["efek"][j] = filter tambahan per kotak (mis. hitam-putih).
    kotak = spec["kotak"] if isinstance(spec["kotak"], list) else [spec["kotak"]]
    efek = spec.get("efek") or [None] * len(kotak)
    n = len(kotak)
    titik = crop or {}
    if "x" not in titik or "y" not in titik:
        titik = {**poster.titik_otomatis(media, waktu, sw, sh, kotak[0][2] / kotak[0][3]), **titik}
    vf, awal = [], []
    for j, (kx, ky, kw, kh) in enumerate(kotak):
        c = dict(titik)
        if gambar and n > 1:  # satu foto di banyak kotak: tiap kotak sedikit lebih dekat
            c["zoom"] = float(titik.get("zoom", 1.0)) * (1 + 0.14 * j)
        f = filter_media(media, kw // 2 * 2, kh // 2 * 2, c, waktu, sw, sh, grade, atur)
        vf.append(f + (f",{efek[j]}" if efek[j] else ""))
        awal.append(mulai if gambar else mulai + (durasi * j / n if n > 1 else 0))
    kartu = spec["kartu"]
    cx, cy = spec["pusat"]
    sudut = spec["sudut"]
    bayangan = spec.get("bayangan", 0.4 if gaya != "majalah" else 0)

    if gambar or pratinjau:
        k = kartu.copy()
        for j, (kx, ky, _, _) in enumerate(kotak):
            t = awal[j] + (0 if gambar else min(durasi / n, durasi) / 2)
            k.alpha_composite(ambil_gambar(media, t, vf[j]).convert("RGBA"), (kx, ky))
        if spec.get("atas") is not None:
            k.alpha_composite(spec["atas"])
        kanvas = spec["latar"].copy()
        tempel(kanvas, k, cx, cy, sudut, bayangan)
        if spec["depan"] is not None:
            kanvas.alpha_composite(spec["depan"])
        kanvas.convert("RGB").save(keluar, quality=95)
        return keluar

    return rakit_video(spec["latar"], kartu, [(x, y) for x, y, _, _ in kotak], sudut, (cx, cy), spec["depan"],
                       media, vf, awal, durasi, keluar, spec["dorong"], bayangan, spec.get("atas"))


def rakit_video(latar, kartu, posisi, sudut, pusat, depan, media, vf, mulai, durasi, keluar, dorong=False,
                bayangan=0.4, atas=None):
    """Video di dalam kartu: latar (diam, termasuk bayangan kartu) + kartu yang diputar berisi video + lapisan depan.
    posisi/vf/mulai boleh daftar (beberapa kotak, tiap kotak mulai di detik berbeda); atas = lapisan di atas video
    tapi masih bagian kartu (ikut diputar). Kamera mendorong pelan (5%) kalau dorong=True. Suara dari kotak pertama."""
    w, h = latar.size
    if not isinstance(posisi, list):
        posisi, vf, mulai = [posisi], [vf], [mulai]
    cx, cy = pusat
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        latar = latar.copy()
        # hanya bayangan kartu yang masuk latar; kartunya digambar ffmpeg di atas (dengan video di dalamnya)
        bayang = Image.new("RGBA", latar.size, (0, 0, 0, 0))
        tempel(bayang, kartu, cx, cy, sudut, bayangan)
        latar.alpha_composite(bayang)
        latar.convert("RGB").save(tmp / "latar.png")
        kartu.save(tmp / "kartu.png")
        (depan or Image.new("RGBA", (w, h), (0, 0, 0, 0))).save(tmp / "depan.png")
        (atas or Image.new("RGBA", kartu.size, (0, 0, 0, 0))).save(tmp / "atas.png")
        a = sudut * math.pi / 180
        dorong = (f",scale=w='trunc({w}*(1+0.05*t/{durasi:.3f})/2)*2':h=-2:eval=frame:flags=bicubic,"
                  f"crop={w}:{h}" if dorong else "")
        n = len(posisi)
        i_latar, i_kartu, i_depan, i_atas = n, n + 1, n + 2, n + 3
        rantai = [f"[{j}:v]{vf[j]},fps=30,format=rgba[m{j}]" for j in range(n)]
        rantai.append(f"[{i_kartu}:v]format=rgba[k0]")
        for j, (kx, ky) in enumerate(posisi):
            rantai.append(f"[k{j}][m{j}]overlay={kx}:{ky}:shortest=1[k{j + 1}]")
        rantai.append(f"[k{n}][{i_atas}:v]overlay=0:0,"
                      f"rotate={a:.5f}:ow=rotw({a:.5f}):oh=roth({a:.5f}):c=none[k]")
        rantai.append(f"[{i_latar}:v][k]overlay=x={cx:.1f}-w/2:y={cy:.1f}-h/2[l]")
        rantai.append(f"[l][{i_depan}:v]overlay=0:0{dorong},format=yuv420p[v]")
        masuk = []
        for j in range(n):  # kotak yang mulai lebih akhir diulang dari awal kalau videonya habis
            masuk += ["-stream_loop", "-1", "-ss", f"{mulai[j]:.3f}", "-t", f"{durasi:.3f}", "-i", str(media)]
        for nama in ("latar", "kartu", "depan", "atas"):
            masuk += ["-loop", "1", "-framerate", "30", "-i", str(tmp / f"{nama}.png")]
        skrip = tmp / "rantai.txt"
        skrip.write_text(";\n".join(rantai), encoding="utf-8")
        ae.jalankan(["ffmpeg", "-y", "-v", "error", *masuk, "-/filter_complex", str(skrip), "-map", "[v]",
                     "-map", "0:a?", "-af", f"afade=t=in:d=0.4,afade=t=out:st={max(0, durasi - 0.8):.2f}:d=0.8",
                     "-c:a", "aac", "-b:a", "192k", "-t", f"{durasi:.3f}", "-c:v", "libx264", "-preset", "medium",
                     "-crf", "18", "-movflags", "+faststart", str(keluar)])
    return keluar


# -------------------------------------------------------------------------------------------- CAROUSEL
def catatan_tempel(teks, lebar, seed):
    """Kertas catatan kecil (kuning pucat / krem / garis) dengan tulisan tangan."""
    rnd = random.Random(seed)
    warna = rnd.choice([(246, 232, 170, 255), (242, 236, 222, 255), (233, 220, 230, 255), (226, 234, 222, 255)])
    d0 = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f = huruf("tangan", lebar * 0.11)
    baris = bungkus(d0, teks, f, lebar * 0.82)[:5]
    tinggi = round(max(lebar * 0.7, lebar * 0.2 + len(baris) * f.size * 1.25))
    c = kertas_sobek(lebar, tinggi, warna, seed, sobek=(1, 0, 0, 0))
    d = ImageDraw.Draw(c)
    for k in range(1, 8):  # garis buku tipis
        yy = round(lebar * 0.12 + k * f.size * 1.25)
        if yy < tinggi - 6:
            d.line((lebar * 0.06, yy, lebar * 0.94, yy), fill=(150, 170, 200, 70), width=1)
    y = lebar * 0.12 + f.size * 0.2
    for b in baris:
        d.text((lebar * 0.09, y), b, font=f, fill=(56, 48, 60))
        y += f.size * 1.25
    return c


def stempel(teks, d, seed):
    """Cap bulat bertinta (tanggal/tempat), sedikit pudar."""
    img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    tinta = (166, 74, 58, 170)
    g.ellipse((3, 3, d - 4, d - 4), outline=tinta, width=max(3, d // 40))
    g.ellipse((d * 0.1, d * 0.1, d * 0.9, d * 0.9), outline=tinta, width=max(1, d // 90))
    f = huruf("mesin_tebal", d * 0.11)
    baris = str(teks).upper().split("|")[:3]
    y = d / 2 - (len(baris) - 1) * f.size * 0.6
    for b in baris:
        g.text((d / 2, y), b, font=f, fill=tinta, anchor="mm")
        y += f.size * 1.2
    return tekstur(img, 18, seed)


def buat_carousel(daftar, folder, data, warna="serasi", nama="carousel", log=print):
    """Beberapa foto/video -> slide 4:5 yang menyambung jadi satu kertas panjang saat digeser:
    garis putus-putus tangan berjalan melewati semua slide, foto polaroid kadang melewati batas slide,
    catatan tempel, selotip, dan cap. Slide 1 = judul. Video -> slide-nya jadi MP4 (polaroid berisi video);
    foto -> JPG. Makin banyak media, makin panjang kertasnya. Kembalikan daftar file berurutan.

    data: judul, sub, keterangan ("a|b|c" per media), catatan (["...", ...] atau "a|b"), cap ("tempat|tanggal"),
    penutup (teks slide terakhir; kosong = tanpa slide penutup)."""
    folder = Path(folder)
    W, H = UKURAN["4:5"]
    daftar = [Path(x) for x in daftar]
    n = len(daftar)
    penutup = (data.get("penutup") or "").strip()
    s = n + 1 + (1 if penutup else 0)
    latar = tekstur(Image.new("RGBA", (W * s, H), (234, 227, 214, 255)), 7, 21)
    d = ImageDraw.Draw(latar)
    rnd = random.Random(5)
    # garis tangan putus-putus yang menyambung semua slide (terasa satu kertas saat digeser)
    titik = [(W * 0.55 + k * W * 0.5, H * (0.80 + 0.07 * math.sin(k * 1.7))) for k in range(2 * s)]
    for (x0, y0), (x1, y1) in zip(titik, titik[1:]):
        for j in range(0, 20, 2):
            ax, ay = x0 + (x1 - x0) * j / 20, y0 + (y1 - y0) * j / 20
            bx, by = x0 + (x1 - x0) * (j + 1) / 20, y0 + (y1 - y0) * (j + 1) / 20
            d.line((ax, ay, bx, by), fill=(150, 120, 100), width=3)
    # slide judul
    m = round(W * 0.09)
    judul = data.get("judul") or "Cerita kecil"
    fj, bj = judul_pas(d, judul, "bodoni", W - 2 * m, W * 0.15, 3)
    y = H * 0.36
    for b in bj:
        d.text((m, y), b, font=fj, fill=(46, 38, 32))
        y += round(fj.size * 1.02)
    if data.get("sub"):
        fs = huruf("serif_miring", W * 0.04)
        for b in bungkus(d, data["sub"], fs, W - 2 * m):
            d.text((m, y + W * 0.02), b, font=fs, fill=(96, 82, 70))
            y += round(fs.size * 1.3)
    ft = huruf("tangan", W * 0.045)
    d.text((W - m, H - m), "geser -->", font=ft, fill=(120, 100, 86), anchor="rb")
    ket = [x.strip() for x in str(data.get("keterangan") or "").split("|")]
    catatan = data.get("catatan") or []
    if isinstance(catatan, str):
        catatan = [x.strip() for x in catatan.split("|") if x.strip()]
    depan = Image.new("RGBA", latar.size, (0, 0, 0, 0))  # selotip di atas polaroid video
    video = {}  # slide -> (kartu, posisi media di kartu, sudut, pusat lokal, media, vf, durasi)
    grade = ae.WARNA[WARNA_SERASI["carousel"]] if warna == "serasi" else ae.WARNA.get(warna or "asli", "null")
    for i, md in enumerate(daftar):
        log(f"[carousel] {i + 1}/{n} {md.name}")
        sw, sh, total = ae.info_video(md)
        gerak = not ae.foto(md)
        t = total / 2 if gerak else 0
        atur = ae.atur_otomatis(md) if warna == "serasi" else {}
        pw = round(W * 0.66)
        tepi = round(pw * 0.06)
        kw = (pw - 2 * tepi) // 2 * 2
        kh = round(kw * 1.18) // 2 * 2
        ph = tepi + kh + round(pw * 0.2)
        vf = filter_media(md, kw, kh, {}, [t], sw, sh, grade, atur)
        kartu = tekstur(Image.new("RGBA", (pw, ph), (248, 246, 240, 255)), 3, 30 + i)
        if i < len(ket) and ket[i]:
            fk, bk = judul_pas(ImageDraw.Draw(kartu), ket[i], "tangan", pw - 2 * tepi, pw * 0.075, 1)
            ImageDraw.Draw(kartu).text((pw / 2, tepi + kh + (ph - tepi - kh) / 2), bk[0], font=fk,
                                       fill=(52, 46, 54), anchor="mm")
        # foto digeser bergantian supaya ada yang melewati batas slide; video tetap di dalam slidenya sendiri
        geser = 0 if gerak or i == n - 1 else (0.34 if i % 2 else -0.08) * W
        slide = i + 1
        cx = (slide + 0.5) * W + geser
        cy = H * (0.47 + rnd.uniform(-0.03, 0.03))
        sudut = rnd.uniform(-5, 5)
        # catatan tempel di pojok yang kosong (sisi berlawanan dari geseran foto)
        if i < len(catatan) and catatan[i]:
            c = catatan_tempel(catatan[i], round(W * 0.34), 60 + i)
            kanan = geser <= 0
            # di lapisan depan: menempel di atas tepi polaroid, tidak tertutup
            tempel(depan, c, slide * W + W * (0.80 if kanan else 0.20), H * (0.12 if i % 2 else 0.88),
                   rnd.uniform(-7, 7), 0.25)
        st = selotip(round(pw * 0.32), round(pw * 0.08), 40 + i)
        if gerak:
            video[slide] = (kartu, (tepi, tepi), sudut, (cx - slide * W, cy), md, vf, min(total, 30.0))
            tempel(depan, st, cx + rnd.uniform(-30, 30), cy - ph / 2 + 10, rnd.uniform(-8, 8), 0)
        else:
            k = kartu.copy()
            k.alpha_composite(ambil_gambar(md, t, vf).convert("RGBA"), (tepi, tepi))
            tempel(latar, k, cx, cy, sudut, 0.38)
            tempel(latar, st, cx + rnd.uniform(-30, 30), cy - ph / 2 + 10, rnd.uniform(-8, 8), 0)
    if data.get("cap"):  # cap tempat/tanggal di slide judul
        tempel(latar, stempel(data["cap"], round(W * 0.26), 7), W * 0.78, H * 0.17, -12, 0)
    if penutup:
        fp, bp = judul_pas(d, penutup, "bodoni_miring", W * 0.7, W * 0.1, 3)
        y = H * 0.4
        for b in bp:
            d.text(((s - 0.5) * W, y), b, font=fp, fill=(70, 56, 46), anchor="mt")
            y += round(fp.size * 1.1)
    hasil = []
    for k in range(s):
        potong = (k * W, 0, (k + 1) * W, H)
        if k in video:
            kartu, pos, sudut, pusat, md, vf, durasi = video[k]
            f = folder / f"{nama}_{k + 1:02d}.mp4"
            rakit_video(latar.crop(potong), kartu, pos, sudut, pusat, depan.crop(potong), md, vf, 0.0, durasi, f,
                        False, 0.38)
        else:
            f = folder / f"{nama}_{k + 1:02d}.jpg"
            Image.alpha_composite(latar.crop(potong), depan.crop(potong)).convert("RGB").save(f, quality=95)
        hasil.append(f)
    return hasil


# koleksi benda kenangan (koleksi.py) ikut terdaftar; diimpor di sini karena koleksi memakai helper di atas
if __name__ != "__main__":  # dijalankan langsung: pendaftaran terjadi saat main() memuat modul desain
    import koleksi  # noqa: E402

    GAYA.update(koleksi.GAYA_LAIN)
    RASIO_BAWAAN.update(koleksi.RASIO_LAIN)
    WARNA_SERASI.update(koleksi.WARNA_LAIN)

ISIAN = ("judul", "sub", "nama", "tempat", "tanggal", "jam", "kursi", "teks", "keterangan", "kutipan", "cerita",
         "label", "catatan", "cap", "penutup")

def main():
    ap = argparse.ArgumentParser(description="Desain dari foto atau video (lihat GAYA). Isian lain lewat --data JSON.")
    ap.add_argument("media", type=Path, nargs="+")
    ap.add_argument("--gaya", choices=[*GAYA, "carousel"], default="koran")
    ap.add_argument("--rasio", choices=UKURAN)
    ap.add_argument("--data", default="{}", help="isian sebagai JSON (lihat README)")
    for k in ISIAN:
        ap.add_argument(f"--{k}", default="")
    ap.add_argument("--warna", default="serasi")
    ap.add_argument("--mulai", type=float, default=0.0)
    ap.add_argument("--durasi", type=float)
    ap.add_argument("--crop", default="{}")
    ap.add_argument("--pratinjau", action="store_true")
    ap.add_argument("--keluar", type=Path)
    a = ap.parse_args()
    data = {**json.loads(a.data), **{k: v for k, v in vars(a).items()
                                     if k in ISIAN and v}}
    if a.gaya == "carousel":
        for f in buat_carousel(a.media, a.keluar or a.media[0].parent, data, a.warna, a.media[0].stem + "_carousel"):
            print(f)
    else:
        m = a.media[0]
        ext = ".jpg" if ae.foto(m) or a.pratinjau else ".mp4"
        print(buat_desain(m, a.keluar or m.with_name(f"{m.stem}_{a.gaya}{ext}"), data, a.gaya, a.rasio, a.mulai,
                          a.durasi, a.warna, None, json.loads(a.crop), a.pratinjau))


if __name__ == "__main__":
    import desain  # lewat modulnya sendiri, supaya koleksi.py (yang mengimpor desain) tidak memuat file ini dua kali
    desain.main()
