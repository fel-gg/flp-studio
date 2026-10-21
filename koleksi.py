"""Koleksi desain tambahan (benda kenangan): tiap fungsi tata_<nama>(data, w, h, gambar_kecil) mengembalikan spec
yang sama dengan desain.py (latar, kartu, kotak, sudut, pusat, depan, dorong) plus opsional:
  atas    = lapisan di atas foto/video tapi masih bagian kartu (ikut diputar), mis. jendela kaset, cap pos
  efek    = filter ffmpeg tambahan per kotak, mis. hitam-putih untuk photobooth
  kotak   = boleh daftar beberapa kotak (strip photobooth, film) -> video: tiap kotak momen berbeda
Semua teks bisa diganti lewat data; yang kosong memakai teks bawaan (bahasa Inggris, nuansa hangat-melankolis).
"""
import datetime
import hashlib
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import poster
import bahan
from desain import bungkus, judul_pas, kertas_sobek, selotip, tekstur

F = r"C:\Windows\Fonts"
HURUF2 = {
    "ocr": "OCRAEXT.TTF", "konsol_tebal": "consolab.ttf", "ketik": "LTYPE.TTF", "ketik_tebal": "LTYPEB.TTF", "konsol": "lucon.ttf",
    "tangan2": "LHANDW.TTF", "tangan": "Inkfree.ttf", "baskerville": "BASKVILL.TTF", "garamond": "GARA.TTF",
    "garamond_miring": "GARAIT.TTF", "garamond_tebal": "GARABD.TTF", "cooper": "COOPBL.TTF", "bauhaus": "BAUHS93.TTF",
    "simbol": "seguisym.ttf", "franklin_berat": "FRAHV.TTF", "franklin_sempit": "FRAMDCN.TTF", "stensil": "STENCIL.TTF",
    "bodoni": "BOD_B.TTF", "bodoni_miring": "BOD_I.TTF", "bodoni_biasa": "BOD_R.TTF", "georgia": "georgia.ttf",
    "georgia_miring": "georgiai.ttf", "georgia_tebal": "georgiab.ttf", "segoe": "segoeui.ttf", "segoe_tebal": "segoeuib.ttf",
    "impact": "impact.ttf", "abad": "CENTURY.TTF", "skrip": "segoesc.ttf", "kursif": "MTCORSVA.TTF",
}


import desain as _desain  # noqa: E402

# judul_pas()/huruf() di desain.py ikut mengenal font koleksi (nama yang sudah ada di sana tidak ditimpa)
_desain.HURUF.update({k: f"{F}\\{v}" for k, v in HURUF2.items() if k not in _desain.HURUF})


def hf(nama, ukuran):
    return ImageFont.truetype(f"{F}\\{HURUF2[nama]}", max(6, round(ukuran)))


def bs(ukuran, gaya="Bold Condensed"):
    """Bahnschrift (font variabel) potongan tertentu."""
    return poster.font(round(ukuran), gaya)


def isi(data, kunci, bawaan):
    v = data.get(kunci)
    return bawaan if v is None or str(v).strip() == "" else str(v)


def hari_ini(fmt="%d %b %Y"):
    return datetime.date.today().strftime(fmt).upper()


def teks_putar(teks, font, warna, sudut=90):
    d0 = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    l, t, r, b = d0.textbbox((0, 0), teks, font=font)
    img = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2 - l, 2 - t), teks, font=font, fill=warna)
    return img.rotate(sudut, expand=True, resample=Image.BICUBIC)


def spasi(d, xy, teks, font, warna, jarak, anchor="l"):
    """Teks dengan jarak antar huruf (letter-spacing). anchor l/m/r terhadap x."""
    lebar = sum(d.textlength(c, font=font) for c in teks) + jarak * (len(teks) - 1)
    x, y = xy
    x -= lebar / 2 if anchor == "m" else lebar if anchor == "r" else 0
    for c in teks:
        d.text((x, y), c, font=font, fill=warna)
        x += d.textlength(c, font=font) + jarak
    return lebar


def garis_kode(d, x, y, w, h, seed, warna):
    """Barcode semu dari seed: lebar batang bervariasi, berhenti tepat di lebar w."""
    bit = bin(int(hashlib.sha1(str(seed).encode()).hexdigest(), 16))[2:] * 4
    akhir, i = x + w, 0
    while i + 1 < len(bit):
        lb = 2 + int(bit[i]) * 3 + int(bit[i + 1]) * 2
        if x + lb > akhir:
            break
        d.rectangle((x, y, x + lb - 1, y + h), fill=warna)
        x += lb + 3 + int(bit[i + 1]) * 2
        i += 2


def qr_semu(ukuran, seed, warna=(30, 30, 34, 255)):
    """Pola mirip QR (tidak bisa dipindai; hiasan) dengan tiga penanda sudut."""
    n = 25
    rnd = random.Random(seed)
    s = ukuran / n
    img = Image.new("RGBA", (ukuran, ukuran), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i in range(n):
        for j in range(n):
            if rnd.random() < 0.48:
                d.rectangle((j * s, i * s, (j + 1) * s - 0.5, (i + 1) * s - 0.5), fill=warna)
    for ox, oy in ((0, 0), (n - 7, 0), (0, n - 7)):
        x, y = ox * s, oy * s
        d.rectangle((x - s * 0.5, y - s * 0.5, x + 7.5 * s, y + 7.5 * s), fill=(0, 0, 0, 0))
        d.rectangle((x, y, x + 7 * s, y + 7 * s), fill=warna)
        d.rectangle((x + s, y + s, x + 6 * s, y + 6 * s), fill=(0, 0, 0, 0))
        d.rectangle((x + 2 * s, y + 2 * s, x + 5 * s, y + 5 * s), fill=warna)
    return img


def tinta(img, alpha=0.85, seed=3):
    """Cap/tinta yang tidak rata: alpha diberi noise supaya terlihat dicap, bukan dicetak."""
    import numpy as np
    a = np.asarray(img.split()[3]).astype(np.float32)
    rng = np.random.default_rng(seed)
    noise = rng.uniform(0.45, 1.0, a.shape)
    noise = np.asarray(Image.fromarray((noise * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)))
    img.putalpha(Image.fromarray(np.clip(a * noise / 255 * alpha, 0, 255).astype(np.uint8)))
    return img


def cap_bulat(teks_atas, teks_tengah, teks_bawah, d, warna, seed):
    img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    lw = max(3, d // 36)
    g.ellipse((lw, lw, d - lw, d - lw), outline=warna, width=lw)
    g.ellipse((d * 0.17, d * 0.17, d * 0.83, d * 0.83), outline=warna, width=max(2, lw // 2))
    f = hf("ocr", d * 0.085)
    # teks melengkung di cincin luar
    for teks, atas in ((teks_atas, True), (teks_bawah, False)):
        n = len(teks)
        for i, c in enumerate(teks):
            sudut = (-60 + 120 * (i + 0.5) / max(n, 1)) if atas else (60 - 120 * (i + 0.5) / max(n, 1))
            rad = math.radians(sudut - 90 if atas else sudut + 90)
            r = d * 0.415
            cx, cy = d / 2 + r * math.cos(rad), d / 2 + r * math.sin(rad)
            huruf_img = teks_putar(c, f, warna, -sudut if atas else -sudut)
            img.alpha_composite(huruf_img, (round(cx - huruf_img.width / 2), round(cy - huruf_img.height / 2)))
    ft = hf("ocr", d * 0.12)
    g.text((d / 2, d / 2), teks_tengah, font=ft, fill=warna, anchor="mm")
    return tinta(img, 0.8, seed)


# ------------------------------------------------------------------------------------------ 1 BOARDING
def tata_boarding(data, w, h, kecil):
    latar = bahan.buat("kayu", w, h, 31, gelap=(150, 120, 92), terang=(205, 176, 140))
    bw = round(min(w * 0.82, h * 0.46))
    bh = round(min(h * 0.88, bw * 1.95))
    navy, oranye, kertas = (28, 38, 66), (214, 112, 58), (248, 245, 238, 255)
    kartu = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(kartu)
    d.rounded_rectangle((0, 0, bw - 1, bh - 1), round(bw * 0.035), fill=kertas)
    m = round(bw * 0.065)
    foto = (m, m, bw - 2 * m, round(bh * 0.33))
    y = foto[1] + foto[3] + round(bw * 0.04)
    # pita maskapai
    pita = round(bw * 0.085)
    d.rectangle((0, y, bw, y + pita), fill=navy)
    spasi(d, (m, y + pita * 0.22), isi(data, "maskapai", "HANGAT AIR"), bs(pita * 0.5, "Bold SemiCondensed"),
          (250, 246, 238), pita * 0.08)
    d.text((bw - m, y + pita * 0.3), "BOARDING PASS", font=bs(pita * 0.36, "SemiCondensed"),
           fill=(232, 180, 140), anchor="ra")
    y += pita + round(bw * 0.05)
    # kode kota besar + pesawat
    fk = bs(bw * 0.2, "Bold Condensed")
    d.text((m, y), isi(data, "dari", "PNK").upper()[:4], font=fk, fill=navy)
    d.text((bw - m, y), isi(data, "ke", "JOG").upper()[:4], font=fk, fill=navy, anchor="ra")
    ty = y + fk.size * 0.42
    d.line((bw * 0.38, ty, bw * 0.62, ty), fill=(180, 170, 160), width=2)
    d.text((bw / 2, ty), "\u2708", font=hf("simbol", bw * 0.075), fill=oranye, anchor="mm")
    y += round(fk.size * 1.02)
    fc = bs(bw * 0.034, "SemiCondensed")
    d.text((m, y), isi(data, "kota_dari", "Pontianak").upper(), font=fc, fill=(110, 104, 98))
    d.text((bw - m, y), isi(data, "kota_ke", "Yogyakarta").upper(), font=fc, fill=(110, 104, 98), anchor="ra")
    y += round(bw * 0.09)
    # kisi data
    fl, fv = bs(bw * 0.028, "SemiCondensed"), bs(bw * 0.048, "Bold SemiCondensed")
    kol = (bw - 2 * m) / 3
    baris = [[("PASSENGER", isi(data, "nama", "THE DREAMER"), 2), ("FLIGHT", isi(data, "penerbangan", "HG 1907"), 1)],
             [("DATE", isi(data, "tanggal", hari_ini("%d %b")), 1), ("GATE", isi(data, "gerbang", "B7"), 1),
              ("SEAT", isi(data, "kursi", "12A"), 1)],
             [("BOARDING", isi(data, "jam", "06:40"), 1), ("CLASS", isi(data, "kelas", "WINDOW SEAT DREAMS"), 2)]]
    for b in baris:
        x = m
        for lb, nilai, lebar in b:
            d.text((x, y), lb, font=fl, fill=oranye)
            t = str(nilai).upper()
            muat = kol * lebar - 12  # nilai panjang dikecilkan supaya tidak menabrak kolom sebelah
            f = fv if d.textlength(t, font=fv) <= muat else bs(fv.size * muat / d.textlength(t, font=fv),
                                                                "Bold SemiCondensed")
            d.text((x, y + fl.size * 1.35), t, font=f, fill=navy)
            x += kol * lebar
        y += round(fl.size * 1.35 + fv.size * 1.7)
    # sobekan + potongan bawah
    yp = round(bh * 0.80)
    rr = round(bw * 0.045)
    for cx in (0, bw):
        d.ellipse((cx - rr, yp - rr, cx + rr, yp + rr), fill=(0, 0, 0, 0))
    for x in range(rr + 8, bw - rr - 8, 18):
        d.line((x, yp, x + 9, yp), fill=(190, 180, 170), width=2)
    q = round(bh - yp - rr * 2.2)
    kartu.alpha_composite(qr_semu(q, isi(data, "nama", "x"), (*navy, 255)), (m, yp + round(rr * 1.1)))
    tx = m + q + round(bw * 0.05)
    d.text((tx, yp + rr * 1.2), "SEAT", font=fl, fill=oranye)
    d.text((tx, yp + rr * 1.2 + fl.size * 1.3), isi(data, "kursi", "12A").upper(), font=bs(q * 0.42), fill=navy)
    pesan = isi(data, "catatan", "gate closes when the sun goes down")
    d.text((tx, yp + rr * 1.2 + fl.size * 1.3 + q * 0.5), pesan, font=hf("tangan", bw * 0.034), fill=(90, 84, 92))
    kartu = tekstur(kartu, 3, 32)
    return {"latar": latar, "kartu": kartu, "kotak": foto, "sudut": -2.5, "pusat": (w / 2, h / 2), "depan": None,
            "dorong": False}


# --------------------------------------------------------------------------------------------- 2 KASET
def roda(d, cx, cy, r, warna_gelap):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(245, 240, 230, 255), outline=warna_gelap, width=3)
    d.ellipse((cx - r * 0.42, cy - r * 0.42, cx + r * 0.42, cy + r * 0.42), fill=warna_gelap)
    for k in range(6):  # gigi roda
        a = math.radians(k * 60)
        x0, y0 = cx + r * 0.2 * math.cos(a), cy + r * 0.2 * math.sin(a)
        x1, y1 = cx + r * 0.34 * math.cos(a), cy + r * 0.34 * math.sin(a)
        d.line((x0, y0, x1, y1), fill=(245, 240, 230, 255), width=max(3, round(r * 0.08)))


def gambar_kaset(lebar, judul, sisi, durasi, seed):
    """Pita kaset utuh (cangkang krem, label tulisan tangan, jendela dengan dua roda) sebagai RGBA."""
    kw_, kh_ = lebar, round(lebar * 0.63)
    img = Image.new("RGBA", (kw_, kh_), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    gelap = (52, 44, 40, 255)
    d.rounded_rectangle((0, 0, kw_ - 1, kh_ - 1), round(kw_ * 0.04), fill=(58, 52, 50, 255))
    d.polygon([(kw_ * 0.2, kh_), (kw_ * 0.26, kh_ * 0.78), (kw_ * 0.74, kh_ * 0.78), (kw_ * 0.8, kh_)],
              fill=(44, 40, 38, 255))
    for fx in (0.32, 0.41, 0.5, 0.59, 0.68):
        d.ellipse((kw_ * fx - 6, kh_ * 0.9 - 6, kw_ * fx + 6, kh_ * 0.9 + 6), fill=(20, 18, 18, 255))
    for fx, fy in ((0.035, 0.06), (0.965, 0.06), (0.035, 0.92), (0.965, 0.92)):
        cx, cy = kw_ * fx, kh_ * fy
        d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=(120, 112, 104, 255))
        d.line((cx - 5, cy, cx + 5, cy), fill=(70, 64, 60, 255), width=2)
    # label kertas krem dengan pita warna, judul tulisan tangan, jendela pita
    lx, ly, lw, lh = kw_ * 0.06, kh_ * 0.08, kw_ * 0.88, kh_ * 0.64
    d.rounded_rectangle((lx, ly, lx + lw, ly + lh), 10, fill=(240, 232, 216, 255))
    d.rectangle((lx, ly + lh * 0.62, lx + lw, ly + lh * 0.74), fill=(196, 92, 72, 255))
    d.rectangle((lx, ly + lh * 0.74, lx + lw, ly + lh * 0.8), fill=(226, 160, 84, 255))
    d.text((lx + lw * 0.03, ly + lh * 0.16), sisi, font=bs(lh * 0.22), fill=(196, 92, 72), anchor="lm")
    d.line((lx + lw * 0.12, ly + lh * 0.28, lx + lw * 0.95, ly + lh * 0.28), fill=(170, 160, 150, 255), width=2)
    fj, bj = judul_pas(d, judul, "tangan", lw * 0.8, lh * 0.2, 1)
    d.text((lx + lw * 0.13, ly + lh * 0.27), bj[0], font=fj, fill=(40, 34, 48), anchor="ls")
    d.text((lx + lw * 0.97, ly + lh * 0.97), durasi, font=bs(lh * 0.1, "Bold SemiCondensed"), fill=(110, 100, 92),
           anchor="rb")
    jx0, jy0, jx1, jy1 = lx + lw * 0.2, ly + lh * 0.34, lx + lw * 0.8, ly + lh * 0.6
    d.rounded_rectangle((jx0, jy0, jx1, jy1), round((jy1 - jy0) * 0.5), fill=(34, 28, 26, 255))
    r = (jy1 - jy0) * 0.4
    for fx, besar in ((0.27, 1.5), (0.73, 1.05)):  # sisi A lebih banyak pitanya (baru diputar sebagian)
        cx, cy = jx0 + (jx1 - jx0) * fx, (jy0 + jy1) / 2
        d.ellipse((cx - r * besar, cy - r * besar, cx + r * besar, cy + r * besar), fill=(88, 58, 40, 255))
        roda(d, cx, cy, r * 0.6, gelap)
    return tekstur(img, 3, seed)


def tata_kaset(data, w, h, kecil):
    """Sampul J-card (foto/video) + pita kaset di sampingnya + kertas daftar lagu."""
    from desain import tempel
    latar = bahan.buat("linen", w, h, 41, warna=(204, 180, 172))
    # kertas daftar lagu (kanan bawah) dan pita kaset (kanan atas), keduanya di latar
    jw, jh = round(w * 0.48), round(h * 0.36)
    j = kertas_sobek(jw, jh, (244, 238, 226, 255), 42, sobek=(1, 0, 0, 0))
    gj = ImageDraw.Draw(j)
    mj = round(jw * 0.09)
    spasi(gj, (mj, jh * 0.07), "SIDE " + isi(data, "sisi", "A"), bs(jh * 0.06, "Bold SemiCondensed"), (196, 92, 72),
          jh * 0.012)
    lagu = [x.strip() for x in isi(data, "lagu", "video games|summertime sadness|young and beautiful|"
                                                    "cinnamon girl|say yes to heaven").split("|") if x.strip()][:7]
    ft = hf("tangan", jh * 0.062)
    yy = jh * 0.2
    for i, l in enumerate(lagu):
        gj.text((mj, yy), f"{i + 1}. {l}", font=ft, fill=(48, 40, 52))
        gj.line((mj, yy + ft.size * 1.2, jw - mj, yy + ft.size * 1.2), fill=(170, 160, 150, 150), width=1)
        yy += ft.size * 1.55
    tempel(latar, j, w * 0.77, h * 0.82, 5, 0.3)
    kaset = gambar_kaset(round(w * 0.62), isi(data, "judul", "songs for 2 a.m."), isi(data, "sisi", "A"),
                         isi(data, "durasi", "C-60"), 43)
    tempel(latar, kaset, w * 0.78, h * 0.22, 14, 0.4)
    # J-card: panel depan berfoto + punggung (spine) bertuliskan judul vertikal
    cw = round(w * 0.52)
    ch = round(cw * 1.56)
    spine = round(cw * 0.13)
    kartu = tekstur(Image.new("RGBA", (cw + spine, ch), (244, 238, 226, 255)), 4, 44)
    d = ImageDraw.Draw(kartu)
    d.rectangle((0, 0, spine, ch), fill=(196, 92, 72, 255))
    d.line((spine, 0, spine, ch), fill=(150, 70, 56, 255), width=2)  # lipatan
    pt = teks_putar(isi(data, "judul", "songs for 2 a.m.") + "   ·   " + isi(data, "nama", "a mixtape"),
                    bs(spine * 0.42, "SemiCondensed"), (250, 240, 228), 90)
    kartu.alpha_composite(pt, (round(spine / 2 - pt.width / 2), round(ch * 0.06)))
    m = round(cw * 0.06)
    foto = (spine + m, m, cw - 2 * m, round(ch * 0.7))
    y = foto[1] + foto[3] + round(ch * 0.035)
    fj, bj = judul_pas(d, isi(data, "judul", "songs for 2 a.m."), "tangan", cw - 2 * m, cw * 0.11, 2)
    for b in bj:
        d.text((spine + m, y), b, font=fj, fill=(40, 34, 48))
        y += fj.size * 1.1
    d.text((spine + m, ch - m), isi(data, "nama", "a mixtape") + " · " + isi(data, "tahun", hari_ini("%Y")),
           font=bs(cw * 0.04, "SemiCondensed"), fill=(150, 70, 56), anchor="lb")
    d.text((spine + cw - m, ch - m), "SIDE " + isi(data, "sisi", "A"), font=bs(cw * 0.04, "Bold SemiCondensed"),
           fill=(150, 70, 56), anchor="rb")
    return {"latar": latar, "kartu": kartu, "kotak": foto, "sudut": -4, "pusat": (w * 0.36, h * 0.45), "depan": None,
            "dorong": False}


# ------------------------------------------------------------------------------------------- 3 VINYL
def tata_vinyl(data, w, h, kecil):
    latar = bahan.buat("beton", w, h, 51, warna=(200, 192, 182))
    s = round(w * 0.66)
    keluar = round(s * 0.36)
    kartu = Image.new("RGBA", (s + keluar, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(kartu)
    # piringan: alur melingkar, label tengah, kilap
    cx, cy, r = s - s * 0.5 + keluar, s / 2, s * 0.48
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(18, 17, 18, 255))
    for k in range(18, 100, 2):
        rr = r * k / 100
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(30 + k % 4 * 4, 29 + k % 4 * 4, 31 + k % 4 * 4, 255))
    kilap = Image.new("RGBA", kartu.size, (0, 0, 0, 0))
    ImageDraw.Draw(kilap).pieslice((cx - r, cy - r, cx + r, cy + r), -40, -20, fill=(255, 255, 255, 34))
    ImageDraw.Draw(kilap).pieslice((cx - r, cy - r, cx + r, cy + r), 140, 160, fill=(255, 255, 255, 26))
    kartu.alpha_composite(kilap.filter(ImageFilter.GaussianBlur(6)))
    rl = r * 0.33
    d.ellipse((cx - rl, cy - rl, cx + rl, cy + rl), fill=(196, 84, 60, 255))
    d.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill=(226, 218, 206, 255))
    fl = bs(rl * 0.18, "Bold SemiCondensed")
    d.text((cx + rl * 0.15, cy - rl * 0.45), isi(data, "nama", "THE QUIET ONES").upper(), font=fl,
           fill=(250, 236, 220), anchor="mm")
    d.text((cx + rl * 0.15, cy + rl * 0.45), "33\u2153 RPM \u00b7 SIDE A", font=bs(rl * 0.13, "SemiCondensed"),
           fill=(250, 236, 220), anchor="mm")
    # sampul: foto penuh + sedikit bekas lingkaran (ring wear) + teks + stiker
    sampul = (0, 0, s, s)
    atas = Image.new("RGBA", kartu.size, (0, 0, 0, 0))
    g = ImageDraw.Draw(atas)
    import numpy as np
    grad = np.clip(1 - np.linspace(0, 1, s)[:, None] / 0.35, 0, 1) ** 1.8 * 120
    gl = Image.new("RGBA", (s, s), (10, 8, 6, 0))
    gl.putalpha(Image.fromarray(np.repeat(grad, s, 1).astype(np.uint8)))
    atas.alpha_composite(gl)
    g.ellipse((s * 0.06, s * 0.06, s * 0.94, s * 0.94), outline=(255, 255, 255, 12), width=round(s * 0.015))
    m = round(s * 0.06)
    g.text((m, m), isi(data, "nama", "THE QUIET ONES").upper(), font=bs(s * 0.05, "Bold SemiCondensed"),
           fill=(250, 246, 238))
    fj, bj = judul_pas(g, isi(data, "judul", "Golden Hour Tapes"), "bodoni_miring", s * 0.8, s * 0.1, 2)
    y = m + s * 0.07
    for b in bj:
        g.text((m, y), b, font=hf("bodoni_miring", fj.size), fill=(250, 246, 238))
        y += fj.size * 1.05
    sr = s * 0.12
    sx, sy = s * 0.8, s * 0.82
    g.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=(240, 200, 90, 255))
    fs = bs(sr * 0.24, "Bold SemiCondensed")
    for i, b in enumerate(bungkus(g, isi(data, "stiker", "includes the single 'late night'").upper(), fs, sr * 1.5)[:4]):
        g.text((sx, sy - sr * 0.42 + i * fs.size * 1.15), b, font=fs, fill=(70, 40, 30), anchor="mt")
    g.rectangle((0, 0, s - 1, s - 1), outline=(0, 0, 0, 60), width=2)
    return {"latar": latar, "kartu": kartu, "kotak": sampul, "atas": atas, "sudut": -3,
            "pusat": (w * 0.53, h * 0.47), "depan": None, "dorong": False, "bayangan": 0.45}


# ----------------------------------------------------------------------------------------- 4 FILMSTRIP
def tata_filmstrip(data, w, h, kecil):
    latar = bahan.buat("meja_lampu", w, h, 61)  # film dilihat di atas meja lampu
    sw_ = round(min(w * 0.64, h * 0.38))
    fw = round(sw_ * 0.76)
    fh = round(fw / 1.5)
    jarak = round(fw * 0.09)
    n = 4
    sh_ = n * (fh + jarak) + round(fw * 0.32)
    film = (52, 30, 18, 255)
    kartu = Image.new("RGBA", (sw_, sh_), film)
    d = ImageDraw.Draw(kartu)
    lubang_w, lubang_h = round(sw_ * 0.05), round(sw_ * 0.07)
    tepi = (sw_ - fw) / 2
    for yy in range(round(fw * 0.04), sh_, round(lubang_h * 1.8)):
        for xx in (tepi / 2 - lubang_w / 2, sw_ - tepi / 2 - lubang_w / 2):
            d.rounded_rectangle((xx, yy, xx + lubang_w, yy + lubang_h), 4, fill=(0, 0, 0, 0))
    kotak = []
    y0 = round(fw * 0.25)
    oranye = (232, 140, 64)
    no = int(isi(data, "nomor", "12"))
    for j in range(n):
        yy = y0 + j * (fh + jarak)
        kotak.append((round(tepi), yy, fw, fh))
        lb = teks_putar(f"{no + j}  >  {no + j}A", hf("ocr", sw_ * 0.034), oranye, 90)
        kartu.alpha_composite(lb, (round(tepi * 0.02), yy + fh // 2 - lb.height // 2))
    merk = teks_putar(isi(data, "film", "HANGAT 400") + "   " + isi(data, "film", "HANGAT 400"),
                      hf("ocr", sw_ * 0.034), oranye, -90)
    kartu.alpha_composite(merk, (sw_ - round(tepi * 0.98), round(sh_ * 0.3)))
    # label selotip di atas strip + coretan pensil lilin merah di frame kedua
    depan = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    from desain import tempel
    pita = selotip(round(sw_ * 0.9), round(sw_ * 0.16), 62)
    gp = ImageDraw.Draw(pita)
    fj, bj = judul_pas(gp, isi(data, "judul", "roll 07 \u00b7 summer '26"), "tangan", sw_ * 0.8, sw_ * 0.085, 1)
    gp.text((pita.width / 2, pita.height / 2), bj[0], font=fj, fill=(40, 34, 40), anchor="mm")
    cx, cy = w / 2, h / 2
    sudut = -4
    tempel(depan, pita, cx - sh_ * 0.5 * math.sin(math.radians(sudut)) - sw_ * 0.05,
           cy - sh_ / 2 + fw * 0.12, sudut - 3, 0.15)
    merah = (206, 52, 44, 230)
    gd = ImageDraw.Draw(depan)
    ky = cy - sh_ / 2 + y0 + (fh + jarak) + fh / 2
    for k in range(3):  # lingkaran pensil yang tidak sempurna, digambar beberapa kali
        rw, rh = fw * (0.6 + 0.02 * k), fh * (0.62 + 0.03 * k)
        gd.ellipse((cx - rw, ky - rh, cx + rw, ky + rh), outline=merah, width=5)
    fc = hf("tangan", sw_ * 0.08)
    tx, ty = cx + fw * 0.42, ky + fh * 0.55
    catatan = isi(data, "catatan", "this one")
    gd.text((tx, ty), catatan, font=fc, fill=merah)
    # centang digambar tangan (font tulisan tangan tidak punya simbol centang)
    vx = tx + gd.textlength(catatan, font=fc) + fc.size * 0.3
    vy = ty + fc.size * 0.55
    gd.line((vx, vy, vx + fc.size * 0.25, vy + fc.size * 0.3, vx + fc.size * 0.7, vy - fc.size * 0.35),
            fill=merah, width=5, joint="curve")
    return {"latar": latar, "kartu": kartu, "kotak": kotak, "sudut": sudut, "pusat": (cx, cy), "depan": depan,
            "dorong": False, "bayangan": 0.25}


# ------------------------------------------------------------------------------------------ 5 KARTU POS
def tata_kartupos(data, w, h, kecil):
    latar = bahan.buat("kayu", w, h, 71)
    cw = round(w * 0.92)
    ch = round(cw * 0.64)
    kertas = (243, 236, 221, 255)
    kartu = tekstur(Image.new("RGBA", (cw, ch), kertas), 5, 72)
    d = ImageDraw.Draw(kartu)
    m = round(cw * 0.05)
    tinta_biru = (40, 52, 96)
    spasi(d, (cw / 2, m * 0.8), "POST CARD", hf("baskerville", cw * 0.04), (90, 80, 70), cw * 0.012, "m")
    d.line((cw / 2, m * 2.2, cw / 2, ch - m), fill=(150, 138, 124), width=2)
    # pesan tulisan tangan di kiri
    fp = hf("tangan2", cw * 0.026)
    pesan = isi(data, "pesan", "Dear you, the light here turns gold around five and everything slows down. "
                                "I keep thinking you would love it. Saving this moment so I can give it to you "
                                "when I'm home. Don't forget to look up tonight.")
    y = m * 2.6
    for b in bungkus(d, pesan, fp, cw / 2 - m * 2)[:9]:
        d.text((m, y), b, font=fp, fill=tinta_biru)
        y += fp.size * 1.75
    d.text((cw / 2 - m, y + fp.size * 0.6), isi(data, "dari", "\u2014 F."), font=fp, fill=tinta_biru, anchor="ra")
    # perangko (berisi foto/video) dengan tepi bergerigi
    pw, ph = round(cw * 0.25), round(cw * 0.3)
    px, py = cw - m - pw, round(m * 1.7)
    d.rectangle((px, py, px + pw, py + ph), fill=(252, 250, 246, 255))
    rr = max(5, round(pw * 0.028))
    for k in range(int(pw / (rr * 2.6)) + 1):
        xx = px + k * rr * 2.6
        for yy in (py, py + ph):
            d.ellipse((xx - rr, yy - rr, xx + rr, yy + rr), fill=kertas)
    for k in range(int(ph / (rr * 2.6)) + 1):
        yy = py + k * rr * 2.6
        for xx in (px, px + pw):
            d.ellipse((xx - rr, yy - rr, xx + rr, yy + rr), fill=kertas)
    tp = round(pw * 0.08)
    foto = (px + tp, py + tp, pw - 2 * tp, round(ph - tp * 3.2))
    d.text((px + tp, py + ph - tp * 0.7), isi(data, "negara", "HOME"), font=bs(pw * 0.08, "Bold SemiCondensed"),
           fill=(150, 60, 50), anchor="lb")
    d.text((px + pw - tp, py + ph - tp * 0.7), isi(data, "nilai", "2026"), font=bs(pw * 0.08, "Bold SemiCondensed"),
           fill=(150, 60, 50), anchor="rb")
    # alamat
    lebar_alamat = cw / 2 - m * 2.3
    for i in range(3):
        yy = ch * 0.7 + i * ch * 0.09
        d.line((cw / 2 + m, yy, cw - m, yy), fill=(150, 138, 124), width=2)
    untuk = [x.strip() for x in isi(data, "untuk", "to: someone who needs this|wherever you are|the world").split("|")]
    for i, b in enumerate(untuk[:3]):
        u = cw * 0.03
        while u > cw * 0.016 and d.textlength(b, font=hf("tangan2", u)) > lebar_alamat:
            u -= 1
        d.text((cw / 2 + m * 1.3, ch * 0.7 + i * ch * 0.09 - 6), b, font=hf("tangan2", u), fill=tinta_biru,
               anchor="ls")
    # cap pos menimpa perangko (lapisan atas)
    atas = Image.new("RGBA", kartu.size, (0, 0, 0, 0))
    gelap = (40, 36, 40, 255)
    cap = cap_bulat(isi(data, "tempat", "PONTIANAK").upper()[:14], hari_ini("%d.%m.%y"),
                    "* POST *", round(pw * 0.78), gelap, 73)
    atas.alpha_composite(cap, (round(px - pw * 0.42), round(py + ph * 0.45)))
    g = ImageDraw.Draw(atas)
    for k in range(4):  # garis bergelombang cap pos
        pts = [(px - pw * 0.05 + t * 3, py + ph * 0.55 + k * pw * 0.07 + math.sin(t * 0.18) * 5)
               for t in range(round(pw * 0.42))]
        g.line(pts, fill=(40, 36, 40, 150), width=3)
    return {"latar": latar, "kartu": kartu, "kotak": foto, "atas": atas, "sudut": 3, "pusat": (w / 2, h / 2),
            "depan": None, "dorong": False}


# --------------------------------------------------------------------------------------------- 6 STRUK
def zigzag(w, h, warna, gigi=18):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    t = max(6, round(w / gigi / 2))
    pts = []
    for i in range(gigi * 2 + 1):  # tepi atas bergerigi
        pts.append((w * i / (gigi * 2), 0 if i % 2 == 0 else t))
    for i in range(gigi * 2, -1, -1):  # tepi bawah
        pts.append((w * i / (gigi * 2), h - (0 if i % 2 == 0 else t)))
    ImageDraw.Draw(img).polygon(pts, fill=warna)
    return img, t


def tata_struk(data, w, h, kecil):
    latar = bahan.buat("kayu", w, h, 81, gelap=(70, 50, 38), terang=(122, 90, 66))
    rw, rh = round(min(w * 0.64, h * 0.36)), round(h * 0.94)
    kartu, t = zigzag(rw, rh, (247, 245, 240, 255), 16)
    kartu = tekstur(kartu, 2, 82)
    teks = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))  # tulisan di lapisan sendiri: dibuat agak pudar (thermal)
    d = ImageDraw.Draw(teks)
    hitam = (38, 38, 42, 255)
    m = round(rw * 0.08)
    fn, fb, fk = hf("konsol", rw * 0.036), hf("konsol_tebal", rw * 0.036), hf("konsol", rw * 0.03)
    y = t + rw * 0.06
    fj, bj = judul_pas(d, isi(data, "nama", "THE GOOD DAY STORE").upper(), "koran", rw - 2 * m, rw * 0.075, 2)
    for b in bj:
        d.text((rw / 2, y), b, font=hf("konsol_tebal", fj.size), fill=hitam, anchor="mt")
        y += fj.size * 1.15
    for b in (isi(data, "tempat", "PONTIANAK, ID"), isi(data, "telp", "TEL. 0800-SLOW-DOWN")):
        d.text((rw / 2, y), b.upper(), font=fk, fill=hitam, anchor="mt")
        y += fk.size * 1.35
    tb = fn.size * 1.45

    def garis(c="-"):
        nonlocal y
        y += tb * 0.25
        d.text((rw / 2, y), c * 40, font=fn, fill=hitam, anchor="mt")
        y += tb

    def baris(kiri, kanan, f=fn):
        nonlocal y
        d.text((m, y), kiri, font=f, fill=hitam)
        d.text((rw - m, y), kanan, font=f, fill=hitam, anchor="ra")
        y += tb

    garis("=")
    baris(isi(data, "tanggal", hari_ini("%d/%m/%Y")), isi(data, "jam", "17:42"))
    baris("CASHIER: " + isi(data, "kasir", "YOU").upper(), "#" + isi(data, "nomor", "0019"))
    garis()
    foto = (m, round(y + tb * 0.2), rw - 2 * m, round(rh * 0.3))
    y = foto[1] + foto[3] + tb * 0.5
    d.text((rw / 2, y), "*** printed memory ***", font=fk, fill=hitam, anchor="mt")
    y += tb
    garis()
    barang = [x for x in isi(data, "barang", "golden hour:0.00|cold coffee x2:4.50|long walk home:0.00|"
                                              "one good song (on repeat):0.99|unexpected laugh:FREE").split("|")
              if x.strip()][:7]
    for b in barang:
        nama, _, harga = b.partition(":")
        nama = nama.strip().upper()
        while d.textlength(nama, font=fn) > rw - 2 * m - d.textlength("000.00", font=fn) - 10:
            nama = nama[:-2] + "…"
        baris(nama, harga.strip().upper() or "-")
    garis()
    baris("SUBTOTAL", isi(data, "subtotal", "5.49"))
    baris("TAX (WORRIES)", "0.00")
    y += tb * 0.2
    baris("TOTAL", isi(data, "total", "PRICELESS").upper(), hf("konsol_tebal", rw * 0.05))
    y += tb * 0.2
    baris("PAID WITH", isi(data, "bayar", "TIME").upper())
    baris("CHANGE", isi(data, "kembali", "A GOOD MOOD").upper())
    garis("=")
    for b in [x for x in isi(data, "penutup", "THANK YOU FOR STAYING|please come again").split("|") if x.strip()][:3]:
        d.text((rw / 2, y), b, font=fb if b.isupper() else fn, fill=hitam, anchor="mt")
        y += tb
    y += tb * 0.3
    garis_kode(d, m * 1.6, y, rw - 3.2 * m, rw * 0.11, isi(data, "nama", "x"), hitam)
    y += rw * 0.13
    d.text((rw / 2, y), "*0" + isi(data, "nomor", "0019") + hari_ini("%d%m%y") + "*", font=fk, fill=hitam,
           anchor="mt")
    kartu.alpha_composite(tinta(teks, 0.95, 83))
    return {"latar": latar, "kartu": kartu, "kotak": foto, "sudut": 2, "pusat": (w / 2, h / 2 + h * 0.01),
            "depan": None, "dorong": False, "bayangan": 0.45,
            "efek": ["hue=s=0,eq=contrast=1.35:brightness=0.05:gamma=1.1"]}


# --------------------------------------------------------------------------------------------- 7 PASPOR
def guilloche(d, w, h, warna, seed, n=34):
    rnd = random.Random(seed)
    for k in range(n):
        y0 = h * (k + 0.5) / n
        a, f, p = h * 0.03, rnd.uniform(0.008, 0.014), rnd.uniform(0, 6.28)
        pts = [(x, y0 + a * math.sin(x * f + p) + a * 0.4 * math.sin(x * f * 2.7 + k)) for x in range(0, w + 6, 6)]
        d.line(pts, fill=warna, width=1)


def cap_kotak(teks1, teks2, teks3, lebar, warna, seed):
    tinggi = round(lebar * 0.62)
    img = Image.new("RGBA", (lebar, tinggi), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    lw = max(3, lebar // 40)
    g.rounded_rectangle((lw, lw, lebar - lw, tinggi - lw), lebar // 14, outline=warna, width=lw)
    g.rounded_rectangle((lw * 3, lw * 3, lebar - lw * 3, tinggi - lw * 3), lebar // 18, outline=warna,
                        width=max(1, lw // 2))
    g.text((lebar / 2, tinggi * 0.3), teks1, font=bs(tinggi * 0.2, "Bold SemiCondensed"), fill=warna, anchor="mm")
    g.text((lebar / 2, tinggi * 0.56), teks2, font=hf("ocr", tinggi * 0.13), fill=warna, anchor="mm")
    g.text((lebar / 2, tinggi * 0.77), teks3, font=bs(tinggi * 0.12, "SemiCondensed"), fill=warna, anchor="mm")
    return tinta(img, 0.85, seed)


def tata_paspor(data, w, h, kecil):
    from desain import tempel
    latar = bahan.buat("kayu", w, h, 91)
    pw = round(min(w * 0.86, h * 0.68 / 0.66 / 2 * 1.0))
    ph = round(pw * 0.66)
    sampul = Image.new("RGBA", (pw + round(pw * 0.06), ph * 2 + round(pw * 0.06)), (88, 30, 36, 255))
    sampul = tekstur(sampul, 6, 92)
    tempel(latar, sampul, w / 2, h / 2, 1.5, 0.5)
    kartu = Image.new("RGBA", (pw, ph * 2), (226, 236, 228, 255))
    d = ImageDraw.Draw(kartu)
    guilloche(d, pw, ph * 2, (186, 210, 198, 255), 93, 60)
    for r in range(8, 0, -1):  # roset di halaman atas
        d.ellipse((pw * 0.5 - r * pw * 0.04, ph * 0.5 - r * pw * 0.04, pw * 0.5 + r * pw * 0.04,
                   ph * 0.5 + r * pw * 0.04), outline=(196, 216, 206, 255), width=1)
    kartu = tekstur(kartu, 3, 94)
    d = ImageDraw.Draw(kartu)
    d.line((0, ph, pw, ph), fill=(150, 168, 158, 255), width=3)  # lipatan tengah
    hijau, gelap = (86, 112, 100), (34, 40, 44)
    m = round(pw * 0.05)
    # halaman bawah: data
    y0 = ph
    spasi(d, (m, y0 + m * 0.6), "PASSPORT", bs(pw * 0.04, "Bold SemiCondensed"), hijau, pw * 0.01)
    d.text((pw - m, y0 + m * 0.7), "P   " + isi(data, "kode", "IDN") + "   " + isi(data, "nomor", "A0192026"),
           font=hf("ocr", pw * 0.026), fill=gelap, anchor="ra")
    fw_, fh_ = round(pw * 0.27), round(pw * 0.27 * 1.28)
    foto = (m, round(y0 + ph * 0.17), fw_, fh_)
    fl, fv = bs(pw * 0.021, "SemiCondensed"), hf("ocr", pw * 0.028)
    x1, x2 = m + fw_ + m, m + fw_ + m + (pw - fw_ - 3 * m) / 2
    tahun = datetime.date.today().year
    isian = [((x1, 0), "Surname / Nama", isi(data, "nama", "DREAMER")),
             ((x1, 1), "Given names", isi(data, "nama_depan", "THE QUIET ONE")),
             ((x1, 2), "Nationality", isi(data, "kebangsaan", "SOMEWHERE IN BETWEEN")),
             ((x1, 3), "Date of birth", isi(data, "lahir", "A SUMMER, LONG AGO")),
             ((x2, 3), "Place of birth", isi(data, "tempat", "PONTIANAK")),
             ((x1, 4), "Date of issue", isi(data, "tanggal", hari_ini("%d %b %Y"))),
             ((x2, 4), "Date of expiry", isi(data, "berlaku", "NEVER"))]
    for (x, r), lb, v in isian:
        yy = foto[1] + r * ph * 0.092
        d.text((x, yy), lb, font=fl, fill=hijau)
        lebar = (pw - m - x) if x == x1 and r < 3 else (pw - 3 * m - fw_) / 2 - 8
        f = fv
        while d.textlength(v.upper(), font=f) > lebar and f.size > 10:
            f = hf("ocr", f.size - 1)
        d.text((x, yy + fl.size * 1.3), v.upper(), font=f, fill=gelap)
    d.text((x1, foto[1] + ph * 0.47), "Signature", font=fl, fill=hijau)
    d.text((x1, foto[1] + ph * 0.47 + fl.size * 1.1), isi(data, "ttd", "Your Name"), font=hf("kursif", pw * 0.05),
           fill=(30, 40, 80))
    nama_mrz = (isi(data, "nama", "DREAMER") + "<<" + isi(data, "nama_depan", "THE QUIET ONE")).upper()
    nama_mrz = "".join(c if c.isalnum() else "<" for c in nama_mrz)
    b1 = ("P<" + isi(data, "kode", "IDN").upper() + nama_mrz + "<" * 44)[:44]
    b2 = (isi(data, "nomor", "A0192026").upper() + "<0" + isi(data, "kode", "IDN").upper() + str(tahun)[2:] +
          "0101" + "<" * 44)[:44]
    fm = hf("ocr", pw * 0.031)
    while d.textlength(b1, font=fm) > pw - 2 * m:
        fm = hf("ocr", fm.size - 1)
    d.text((m, y0 + ph - m - fm.size * 2.6), b1, font=fm, fill=gelap)
    d.text((m, y0 + ph - m - fm.size * 1.2), b2, font=fm, fill=gelap)
    # halaman atas: cap-cap perjalanan (cap = "tempat:tanggal|...")
    cap = [x for x in isi(data, "cap", "GOLDEN HOUR:" + hari_ini("%d %b %Y") + "|LATE NIGHTS:ALWAYS|"
                                        "SOMEWHERE NEW:SOON|HOME:" + str(tahun)).split("|") if x.strip()][:5]
    tinta_ = [(46, 120, 84, 255), (110, 60, 140, 255), (180, 60, 60, 255), (40, 70, 150, 255), (60, 60, 60, 255)]
    rnd = random.Random(95)
    posisi = [(0.25, 0.32), (0.68, 0.3), (0.32, 0.72), (0.75, 0.7), (0.5, 0.5)]
    atas = Image.new("RGBA", kartu.size, (0, 0, 0, 0))
    for i, c in enumerate(cap):
        tempat, _, tgl = c.partition(":")
        warna = tinta_[i % len(tinta_)]
        if i % 2:
            st = cap_bulat(tempat.strip().upper()[:16], tgl.strip().upper()[:11], "* ARRIVED *",
                           round(pw * 0.27), warna, 96 + i)
        else:
            st = cap_kotak(("ARRIVED" if i % 4 == 0 else "DEPARTED"), tgl.strip().upper()[:12],
                           tempat.strip().upper()[:18], round(pw * 0.34), warna, 96 + i)
        st = st.rotate(rnd.uniform(-18, 18), expand=True, resample=Image.BICUBIC)
        fx, fy = posisi[i]
        atas.alpha_composite(st, (round(pw * fx - st.width / 2), round(ph * fy - st.height / 2)))
    kecil_cap = cap_bulat(isi(data, "tempat", "PONTIANAK").upper()[:14], "OK", "CHECKED",
                          round(pw * 0.17), (46, 120, 84, 255), 99)
    atas.alpha_composite(kecil_cap, (foto[0] + fw_ - round(pw * 0.09), foto[1] + fh_ - round(pw * 0.1)))
    return {"latar": latar, "kartu": kartu, "kotak": foto, "atas": atas, "sudut": 1.5, "pusat": (w / 2, h / 2),
            "depan": None, "dorong": False, "efek": ["hue=s=0.7"]}


# --------------------------------------------------------------------------------------------- 8 MUSEUM
def tata_museum(data, w, h, kecil):
    import numpy as np
    dinding = np.asarray(bahan.buat("linen", w, h, 101, tirai=False, warna=(222, 216, 206)), np.float32)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    sorot = np.exp(-(((x - w * 0.42) / (w * 0.55)) ** 2 + ((y - h * 0.05) / (h * 0.75)) ** 2))  # lampu sorot
    dinding[..., :3] *= (0.78 + 0.32 * sorot)[..., None]
    latar = Image.fromarray(np.clip(dinding, 0, 255).astype(np.uint8))
    # bingkai kayu tipis + passe-partout (karton putih) dengan bevel
    fw_ = round(w * 0.62)
    fh_ = round(fw_ * 1.25)
    tb = round(fw_ * 0.045)
    kayu = bahan.buat("kayu", fw_, fh_, 102, tirai=False, papan=1, gelap=(70, 48, 34), terang=(120, 86, 60))
    kartu = kayu.copy()
    d = ImageDraw.Draw(kartu)
    d.rectangle((tb, tb, fw_ - tb, fh_ - tb), fill=(243, 240, 233, 255))
    d.rectangle((0, 0, fw_ - 1, fh_ - 1), outline=(40, 28, 20, 255), width=2)
    d.rectangle((tb, tb, fw_ - tb, fh_ - tb), outline=(30, 22, 16, 255), width=3)  # bayangan dalam bingkai
    d.line((2, 2, fw_ - 3, 2), fill=(160, 124, 96, 255), width=2)  # tepi bingkai yang kena lampu
    d.line((2, 2, 2, fh_ - 3), fill=(140, 108, 84, 255), width=2)
    mat = round(fw_ * 0.11)
    fx0, fy0 = tb + mat, tb + mat
    foto = (fx0, fy0, fw_ - 2 * (tb + mat), fh_ - 2 * (tb + mat))
    d.rectangle((fx0 - 5, fy0 - 5, fx0 + foto[2] + 4, fy0 + foto[3] + 4), outline=(252, 251, 248, 255), width=3)
    d.line((fx0 - 5, fy0 - 5, fx0 + foto[2] + 4, fy0 - 5), fill=(200, 196, 188, 255), width=3)  # bevel atas teduh
    # kartu keterangan (label museum) di dinding
    from desain import tempel
    lw_, lh_ = round(w * 0.24), round(w * 0.3)
    lab = Image.new("RGBA", (lw_, lh_), (250, 249, 245, 255))
    g = ImageDraw.Draw(lab)
    ml = round(lw_ * 0.09)
    yy = ml
    g.text((ml, yy), isi(data, "seniman", "Your Name"), font=hf("segoe_tebal", lw_ * 0.075), fill=(28, 28, 30))
    yy += lw_ * 0.1
    g.text((ml, yy), isi(data, "asal", "Indonesian, b. 2000"), font=hf("segoe", lw_ * 0.05), fill=(90, 90, 92))
    yy += lw_ * 0.12
    fj = hf("georgia_miring", lw_ * 0.068)
    for b in bungkus(g, isi(data, "judul", "Learning to Stay") + ", " + isi(data, "tahun", hari_ini("%Y")), fj,
                     lw_ - 2 * ml)[:2]:
        g.text((ml, yy), b, font=fj, fill=(28, 28, 30))
        yy += fj.size * 1.25
    g.text((ml, yy), isi(data, "medium", "Golden hour and a phone camera"), font=hf("segoe", lw_ * 0.045),
           fill=(90, 90, 92))
    yy += lw_ * 0.1
    fd = hf("segoe", lw_ * 0.042)
    for b in bungkus(g, isi(data, "deskripsi", "A small, unremarkable evening that the artist decided was worth "
                                              "keeping. Notice the light: it never stays this long."),
                     fd, lw_ - 2 * ml)[:6]:
        g.text((ml, yy), b, font=fd, fill=(60, 60, 62))
        yy += fd.size * 1.4
    lab = lab.crop((0, 0, lw_, min(lh_, round(yy + ml))))
    latar = latar.convert("RGBA")
    tempel(latar, lab, w * 0.86, h * 0.66, 0, 0.18, jarak=4)
    return {"latar": latar, "kartu": kartu, "kotak": foto, "sudut": 0.0, "pusat": (w * 0.39, h * 0.45),
            "depan": None, "dorong": False, "bayangan": 0.55}


# --------------------------------------------------------------------------------------- 9 PERPUSTAKAAN
def penjepit(d, x, y, s, warna=(150, 152, 158, 255)):
    """Klip kertas dari kawat: dua lengkung memanjang."""
    lw = max(3, round(s * 0.06))
    d.rounded_rectangle((x, y, x + s * 0.42, y + s * 1.25), round(s * 0.21), outline=warna, width=lw)
    d.rounded_rectangle((x + s * 0.09, y + s * 0.18, x + s * 0.33, y + s * 1.0), round(s * 0.12), outline=warna,
                        width=lw)


def tata_perpustakaan(data, w, h, kecil):
    latar = bahan.buat("kayu", w, h, 111, gelap=(60, 40, 28), terang=(110, 76, 52))
    cw = round(w * 0.6)
    ch = round(cw * 1.5)
    atas_ = round(cw * 0.16)
    kanan = round(cw * 0.14)
    kartu = Image.new("RGBA", (cw + kanan, ch + atas_), (0, 0, 0, 0))
    manila = tekstur(Image.new("RGBA", (cw, ch), (233, 218, 180, 255)), 5, 112)
    kartu.alpha_composite(manila, (0, atas_))
    d = ImageDraw.Draw(kartu)
    ungu, ketik = (92, 60, 140, 255), (44, 40, 40)
    m = round(cw * 0.07)
    y = atas_ + m
    fk, fl = hf("ketik", cw * 0.033), hf("ketik", cw * 0.026)
    for lb, v in (("Author", isi(data, "penulis", "Your Name")), ("Title", isi(data, "judul", "Notes on Slow Evenings"))):
        d.text((m, y), lb, font=fl, fill=ketik)
        f = fk
        while d.textlength(v, font=f) > cw * 0.4 and f.size > 10:  # jangan tertutup foto di kanan atas
            f = hf("ketik", f.size - 1)
        d.text((m + cw * 0.17, y - 2), v, font=f, fill=ketik)
        d.line((m + cw * 0.16, y + fk.size * 1.15, cw * 0.6, y + fk.size * 1.15), fill=(120, 100, 70), width=1)
        y += fk.size * 2
    y += m * 0.3
    # tabel DATE DUE / BORROWER'S NAME
    kol = m + cw * 0.3
    d.line((m, y, cw - m, y), fill=(150, 70, 60), width=2)
    d.text((m + cw * 0.02, y + 6), "DATE DUE", font=fl, fill=(150, 70, 60))
    d.text((kol + cw * 0.03, y + 6), "BORROWER'S NAME", font=fl, fill=(150, 70, 60))
    y += fl.size * 1.9
    d.line((m, y, cw - m, y), fill=(150, 70, 60), width=2)
    tinggi = ch * 0.068
    akhir = atas_ + ch - m
    d.line((kol, y - fl.size * 1.9, kol, akhir), fill=(150, 70, 60), width=2)
    pinjam = [x for x in isi(data, "peminjam", "yourname:" + hari_ini("%d %b %y") + "|a quiet afternoon:02 NOV 26|"
                                                "you, maybe:14 FEB 27|past me:01 JAN 25").split("|") if x.strip()]
    rnd = random.Random(113)
    lapis = Image.new("RGBA", kartu.size, (0, 0, 0, 0))
    gl = ImageDraw.Draw(lapis)
    baris_ke = 0
    while y + tinggi <= akhir:
        y += tinggi
        d.line((m, y, cw - m, y), fill=(190, 160, 120), width=1)
        if baris_ke < len(pinjam):
            nama, _, tgl = pinjam[baris_ke].partition(":")
            cap = teks_putar(tgl.strip().upper(), hf("ocr", cw * 0.036), ungu, rnd.uniform(-4, 4))
            lapis.alpha_composite(cap, (round(m + cw * 0.02 + rnd.uniform(-4, 4)), round(y - tinggi * 0.85)))
            gl.text((kol + cw * 0.04, y - tinggi * 0.15), nama.strip(), font=hf("tangan2", cw * 0.04),
                    fill=(30, 40, 90), anchor="ls")
        baris_ke += 1
    kartu.alpha_composite(tinta(lapis, 0.9, 114))
    # foto dijepit klip di kanan atas (sebagian keluar dari kartu)
    fs = round(cw * 0.44)
    bingkai = round(fs * 0.06)
    fx, fy = cw + kanan - fs - bingkai * 2, 0
    d.rectangle((fx, fy, fx + fs + bingkai * 2, fy + fs + bingkai * 3), fill=(250, 248, 242, 255))
    foto = (fx + bingkai, fy + bingkai, fs, fs)
    atas = Image.new("RGBA", kartu.size, (0, 0, 0, 0))
    penjepit(ImageDraw.Draw(atas), fx + fs * 0.4, fy - fs * 0.05, fs * 0.28)
    # kantong kartu di bawah
    ga = ImageDraw.Draw(atas)
    ky = atas_ + ch * 0.8
    ga.rectangle((0, ky, cw, atas_ + ch), fill=(214, 194, 150, 255))
    ga.pieslice((cw / 2 - cw * 0.12, ky - cw * 0.12, cw / 2 + cw * 0.12, ky + cw * 0.12), 0, 180,
                fill=(0, 0, 0, 0))
    ga.line((0, ky, cw / 2 - cw * 0.12, ky), fill=(180, 160, 120, 255), width=2)
    ga.line((cw / 2 + cw * 0.12, ky, cw, ky), fill=(180, 160, 120, 255), width=2)
    teks = isi(data, "perpus", "THE QUIET LIBRARY").upper()
    ga.text((cw / 2, ky + ch * 0.095), teks, font=hf("ketik_tebal", cw * 0.04), fill=ketik, anchor="mm")
    ga.text((cw / 2, ky + ch * 0.15), "please return on or before the last date stamped", font=hf("ketik", cw * 0.026),
            fill=ketik, anchor="mm")
    return {"latar": latar, "kartu": kartu, "kotak": foto, "atas": atas, "sudut": -3, "pusat": (w * 0.5, h * 0.5),
            "depan": None, "dorong": False}


# ------------------------------------------------------------------------------------------ 10 PHOTOBOOTH
def strip_booth(sw_, n=4):
    fw = round(sw_ * 0.86)
    fh = round(fw * 0.86)
    jarak = round(sw_ * 0.05)
    atas = round(sw_ * 0.07)
    sh_ = atas + n * (fh + jarak) + round(sw_ * 0.2)
    tepi = (sw_ - fw) // 2
    return [(tepi, atas + j * (fh + jarak), fw, fh) for j in range(n)], sh_


def tata_photobooth(data, w, h, kecil):
    from desain import tempel
    from PIL import ImageOps
    latar = bahan.buat("beludru", w, h, 121)
    sw_ = round(min(w * 0.42, h * 0.235))
    kotak, sh_ = strip_booth(sw_)
    putih = (250, 249, 246, 255)
    # strip kedua (berwarna) di belakang, dari cuplikan kecil
    lain = tekstur(Image.new("RGBA", (sw_, sh_), putih), 3, 122)
    for j, (x, y, fw, fh) in enumerate(kotak):
        g = ImageOps.fit(kecil, (fw, fh), centering=(0.5, 0.35 + 0.05 * j)).convert("RGBA")
        lain.alpha_composite(g, (x, y))
    tempel(latar, lain, w * 0.13, h * 0.6, -9, 0.45)
    kartu = tekstur(Image.new("RGBA", (sw_, sh_), putih), 3, 123)
    d = ImageDraw.Draw(kartu)
    ft = hf("ocr", sw_ * 0.05)
    teks = isi(data, "teks", hari_ini("%b %d %Y") + "  -  " + isi(data, "tempat", "PONTIANAK"))
    while d.textlength(teks, font=ft) > sw_ * 0.86 and ft.size > 10:
        ft = hf("ocr", ft.size - 1)
    d.text((sw_ / 2, sh_ - sw_ * 0.1), teks.upper(), font=ft, fill=(90, 86, 84), anchor="mm")
    bw = "hue=s=0,eq=contrast=1.12:brightness=0.02"
    efek = [None if str(data.get("warna_strip", "")).lower() in ("warna", "color") else bw] * len(kotak)
    return {"latar": latar, "kartu": kartu, "kotak": kotak, "efek": efek, "sudut": 4, "pusat": (w * 0.58, h * 0.5),
            "depan": None, "dorong": False, "bayangan": 0.5}


# --------------------------------------------------------------------------------------------- 11 SURAT
def segel_lilin(d, inisial, seed):
    """Segel lilin merah: tepi meleleh tidak rata, cincin timbul, inisial di tengah."""
    rnd = random.Random(seed)
    img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    g = ImageDraw.Draw(img)
    pts = []
    for k in range(40):
        a = 2 * math.pi * k / 40
        r = d * 0.46 * (1 + rnd.uniform(-0.06, 0.05))
        pts.append((d / 2 + r * math.cos(a), d / 2 + r * math.sin(a)))
    g.polygon(pts, fill=(140, 22, 28, 255))
    g.ellipse((d * 0.17, d * 0.17, d * 0.83, d * 0.83), fill=(122, 18, 24, 255))
    g.ellipse((d * 0.19, d * 0.19, d * 0.81, d * 0.81), outline=(170, 50, 52, 255), width=max(2, d // 40))
    g.text((d / 2, d / 2), inisial[:2], font=hf("kursif", d * 0.38), fill=(176, 58, 58), anchor="mm")
    g.text((d / 2 + 2, d / 2 + 2), inisial[:2], font=hf("kursif", d * 0.38), fill=(96, 12, 18), anchor="mm")
    kilap = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    ImageDraw.Draw(kilap).ellipse((d * 0.25, d * 0.15, d * 0.55, d * 0.35), fill=(255, 220, 220, 60))
    img.alpha_composite(kilap.filter(ImageFilter.GaussianBlur(d * 0.04)))
    return img


def tata_surat(data, w, h, kecil):
    from desain import tempel
    latar = bahan.buat("kayu", w, h, 131, gelap=(140, 110, 84), terang=(196, 164, 128))
    cw, ch = round(w * 0.72), round(w * 0.98)
    kartu = tekstur(Image.new("RGBA", (cw, ch), (246, 241, 230, 255)), 3, 132)
    d = ImageDraw.Draw(kartu)
    m = round(cw * 0.08)
    for k in range(int(ch / (cw * 0.055))):  # garis kertas surat tipis
        yy = round(cw * 0.1 + k * cw * 0.055)
        d.line((m * 0.6, yy, cw - m * 0.6, yy), fill=(196, 206, 222, 255), width=1)
    fw_ = round(cw * 0.5)
    foto = (m, m, fw_, round(fw_ * 1.2))
    biru = (36, 44, 90)
    ft = hf("tangan", cw * 0.045)
    d.text((cw - m, m + cw * 0.02), isi(data, "tanggal", hari_ini("%d %B")).lower(), font=ft, fill=biru, anchor="ra")
    y = foto[1] + foto[3] + cw * 0.06
    fp = hf("tangan2", cw * 0.034)
    d.text((m, y), isi(data, "untuk", "Dear you,"), font=fp, fill=biru)
    y += fp.size * 1.9
    for b in bungkus(d, isi(data, "pesan", "I found this moment and thought of you. Nothing big happened, the light "
                                         "just stayed a little longer than usual and I wanted to keep it somewhere "
                                         "safe. So here it is. Keep it for me?"), fp, cw - 2 * m)[:8]:
        d.text((m, y), b, font=fp, fill=biru)
        y += fp.size * 1.75
    atas = Image.new("RGBA", kartu.size, (0, 0, 0, 0))
    for (x, yy, s) in ((foto[0] - cw * 0.03, foto[1] - cw * 0.01, -35), (foto[0] + fw_ - cw * 0.07,
                                                                         foto[1] - cw * 0.01, 35)):
        tempel(atas, selotip(round(cw * 0.16), round(cw * 0.045), 133), x + cw * 0.05, yy + cw * 0.02, s, 0)
    # amplop di depan menutupi bagian bawah surat (surat seperti baru ditarik keluar)
    depan = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ew, eh = round(w * 0.86), round(h * 0.4)
    ex, ey = round((w - ew) / 2), round(h * 0.64)
    amplop = bahan.buat("kraft", ew, eh, 134, tirai=False, warna=(206, 178, 140))
    ga = ImageDraw.Draw(amplop)
    ga.line((0, eh, ew * 0.5, eh * 0.45, ew, eh), fill=(170, 140, 104, 255), width=3)
    ga.line((0, 0, ew * 0.42, eh * 0.55), fill=(184, 154, 116, 255), width=2)
    ga.line((ew, 0, ew * 0.58, eh * 0.55), fill=(184, 154, 116, 255), width=2)
    bay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(bay).rectangle((ex, ey - 14, ex + ew, ey + 10), fill=(30, 20, 12, 90))
    depan.alpha_composite(bay.filter(ImageFilter.GaussianBlur(10)))
    depan.alpha_composite(amplop, (ex, ey))
    gd = ImageDraw.Draw(depan)
    gd.text((ex + ew * 0.1, ey + eh * 0.62), isi(data, "dari", "— F."), font=hf("tangan2", w * 0.04),
            fill=(60, 44, 34))
    s = segel_lilin(round(w * 0.17), isi(data, "inisial", "F"), 135)
    depan.alpha_composite(s, (round(w / 2 - s.width / 2), round(ey + eh * 0.42 - s.height / 2)))
    return {"latar": latar, "kartu": kartu, "kotak": foto, "atas": atas, "sudut": -2.5, "pusat": (w / 2, h * 0.43),
            "depan": depan, "dorong": False}


# ----------------------------------------------------------------------------------------------- 12 VHS
def tata_vhs(data, w, h, kecil):
    latar = bahan.buat("kayu", w, h, 141, gelap=(64, 46, 34), terang=(112, 82, 60))
    cw = round(min(w * 0.78, h * 0.44))
    ch = round(cw * 1.78)
    hitam = (22, 20, 22, 255)
    kartu = Image.new("RGBA", (cw, ch), hitam)
    d = ImageDraw.Draw(kartu)
    m = round(cw * 0.06)
    krem, oranye, kuning, merah = (244, 230, 200), (232, 118, 44), (244, 188, 60), (196, 56, 44)
    # pita atas
    d.text((m, m), isi(data, "label", "HANGAT HOME VIDEO"), font=bs(cw * 0.04, "Bold SemiCondensed"), fill=krem)
    d.rectangle((cw - m - cw * 0.17, m * 0.8, cw - m, m * 0.8 + cw * 0.075), outline=krem, width=3)
    d.text((cw - m - cw * 0.085, m * 0.8 + cw * 0.0375), "VHS", font=bs(cw * 0.05, "Bold"), fill=krem, anchor="mm")
    # judul gaya 70-an: Cooper Black krem dengan bayangan oranye
    y = m + cw * 0.12
    fj, bj = judul_pas(d, isi(data, "judul", "Late Night Feelings"), "cooper", cw - 2 * m, cw * 0.15, 2)
    fj = hf("cooper", fj.size)
    for b in bj:
        d.text((m + 5, y + 5), b, font=fj, fill=oranye)
        d.text((m, y), b, font=fj, fill=krem)
        y += fj.size * 1.0
    d.text((m, y + cw * 0.02), isi(data, "tagline", "some nights stay with you forever."),
           font=hf("georgia_miring", cw * 0.042), fill=(220, 206, 180))
    y += cw * 0.1
    foto = (m, round(y), cw - 2 * m, round(ch * 0.46))
    d.rectangle((m - 6, y - 6, cw - m + 5, y + foto[3] + 5), outline=kuning, width=3)
    # garis pelangi 70-an di pojok bawah
    yb = foto[1] + foto[3] + cw * 0.05
    for i, c in enumerate((merah, oranye, kuning, (120, 160, 90))):
        d.polygon([(0, yb + i * cw * 0.035), (cw, yb + cw * 0.18 + i * cw * 0.035),
                   (cw, yb + cw * 0.18 + (i + 1) * cw * 0.035), (0, yb + (i + 1) * cw * 0.035)], fill=c)
    yi = ch - m - cw * 0.1
    d.text((m, yi), (isi(data, "info", "COLOR · " + isi(data, "durasi", "92") + " MIN · HI-FI STEREO")),
           font=bs(cw * 0.036, "SemiCondensed"), fill=krem)
    d.rectangle((m, yi + cw * 0.055, m + cw * 0.1, yi + cw * 0.11), outline=krem, width=2)
    d.text((m + cw * 0.05, yi + cw * 0.083), "PG", font=bs(cw * 0.04, "Bold"), fill=krem, anchor="mm")
    d.text((m + cw * 0.13, yi + cw * 0.083), "Pretty Gentle · " + isi(data, "tahun", hari_ini("%Y")),
           font=bs(cw * 0.032, "SemiCondensed"), fill=(200, 190, 170), anchor="lm")
    # bekas pakai: goresan tipis, tepi aus, stiker rental
    atas = Image.new("RGBA", kartu.size, (0, 0, 0, 0))
    g = ImageDraw.Draw(atas)
    rnd = random.Random(142)
    for _ in range(40):
        x0, y0 = rnd.uniform(0, cw), rnd.uniform(0, ch)
        g.line((x0, y0, x0 + rnd.uniform(-60, 60), y0 + rnd.uniform(-8, 8)), fill=(255, 255, 255, rnd.randint(10, 30)),
               width=1)
    g.rectangle((0, 0, cw - 1, ch - 1), outline=(90, 86, 84, 160), width=4)
    sr = round(cw * 0.13)
    sx, sy = cw - m - sr, round(ch * 0.2)
    stiker = Image.new("RGBA", (sr * 2, sr * 2), (0, 0, 0, 0))
    gs = ImageDraw.Draw(stiker)
    gs.ellipse((0, 0, sr * 2 - 1, sr * 2 - 1), fill=(240, 120, 50, 245))
    fs = bs(sr * 0.32, "Bold SemiCondensed")
    for i, b in enumerate(isi(data, "stiker", "BE KIND|REWIND").split("|")[:2]):
        gs.text((sr, sr * (0.7 + i * 0.6)), b.upper(), font=fs, fill=(255, 250, 236), anchor="mm")
    atas.alpha_composite(stiker.rotate(-14, expand=True, resample=Image.BICUBIC), (sx - sr // 2, sy))
    return {"latar": latar, "kartu": kartu, "kotak": foto, "atas": atas, "sudut": -3, "pusat": (w / 2, h / 2),
            "depan": None, "dorong": False, "bayangan": 0.5}


# ---------------------------------------------------------------------------------------------- 13 LOST
def paku_payung(d, cx, cy, r, warna=(200, 40, 40)):
    d.ellipse((cx - r * 0.9 + 6, cy - r * 0.9 + 8, cx + r * 0.9 + 6, cy + r * 0.9 + 8), fill=(20, 10, 6, 90))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=warna)
    d.ellipse((cx - r * 0.55, cy - r * 0.65, cx - r * 0.05, cy - r * 0.2), fill=(255, 200, 200, 200))


def tata_lost(data, w, h, kecil):
    from desain import catatan_tempel, tempel
    latar = bahan.buat("gabus", w, h, 151)
    for i, (tx, fx, fy, s) in enumerate((("call mom back", 0.1, 0.12, -8), ("yard sale sat 9am", 0.9, 0.86, 6),
                                         ("guitar lessons → ask inside", 0.92, 0.14, 9))):
        tempel(latar, catatan_tempel(tx, round(w * 0.3), 152 + i), w * fx, h * fy, s, 0.3)
    cw = round(w * 0.68)
    ch = round(cw * 1.42)
    kertas = (240, 239, 236, 255)
    kartu = tekstur(Image.new("RGBA", (cw, ch), kertas), 6, 153)
    d = ImageDraw.Draw(kartu)
    m = round(cw * 0.07)
    hitam = (24, 24, 26)
    fj, _ = judul_pas(d, isi(data, "judul", "LOST").upper(), "impact", cw - 2 * m, cw * 0.28, 1)
    d.text((cw / 2, m * 1.3), isi(data, "judul", "LOST").upper(), font=hf("impact", fj.size), fill=hitam, anchor="mt")
    y = m * 1.3 + fj.size * 1.08
    fs, bsub = judul_pas(d, isi(data, "sub", "my sense of time"), "georgia_tebal", cw - 2 * m, cw * 0.07, 1)
    d.text((cw / 2, y), bsub[0], font=fs, fill=hitam, anchor="mt")
    y += fs.size * 1.5
    foto = (m, round(y), cw - 2 * m, round(ch * 0.3))
    y = foto[1] + foto[3] + cw * 0.035
    fi = hf("georgia", cw * 0.034)
    for b in bungkus(d, isi(data, "isi", "Last seen somewhere between golden hour and 2 a.m. Answers to "
                                       "\"one more song\". Very friendly, slightly dramatic."), fi, cw - 2 * m)[:3]:
        d.text((cw / 2, y), b, font=fi, fill=hitam, anchor="mt")
        y += fi.size * 1.35
    y += cw * 0.01
    d.text((cw / 2, y), isi(data, "hadiah", "REWARD: a good conversation").upper(), font=hf("franklin_berat", cw * 0.045),
           fill=hitam, anchor="mt")
    # sobekan kontak di bawah, satu sudah diambil orang
    tinggi = round(ch * 0.15)
    ya = ch - tinggi
    n = 8
    lb = cw / n
    for i in range(n):
        x = i * lb
        if i == 5:
            d.rectangle((x + 2, ya + 6, x + lb - 2, ch), fill=(0, 0, 0, 0))
            continue
        if i:
            for yy in range(ya, ch, 12):
                d.line((x, yy, x, yy + 6), fill=(150, 150, 150), width=1)
        kontak = isi(data, "kontak", "@yourname")
        fk = hf("georgia", lb * 0.36)
        while d.textlength(kontak, font=fk) > tinggi * 0.86 and fk.size > 8:
            fk = hf("georgia", fk.size - 1)
        t = teks_putar(kontak, fk, hitam, 90)
        kartu.alpha_composite(t, (round(x + lb / 2 - t.width / 2), round(ya + tinggi / 2 - t.height / 2)))
    d.line((0, ya, cw, ya), fill=(150, 150, 150), width=1)
    depan = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    paku_payung(ImageDraw.Draw(depan), w / 2, h / 2 - ch / 2 + cw * 0.04, w * 0.025)
    return {"latar": latar, "kartu": kartu, "kotak": foto, "sudut": -1.5, "pusat": (w / 2, h / 2 + h * 0.01),
            "depan": depan, "dorong": False, "bayangan": 0.45,
            "efek": ["hue=s=0,eq=contrast=1.55:brightness=0.06,noise=alls=12:allf=0"]}


# -------------------------------------------------------------------------------------------- 14 KERETA
def tata_kereta(data, w, h, kecil):
    from desain import tempel
    latar = bahan.buat("linen", w, h, 161, warna=(200, 196, 188))
    cw = round(w * 0.74)
    ch = round(cw * 1.3)
    tepi = round(cw * 0.05)
    kartu = tekstur(Image.new("RGBA", (cw, ch), (250, 249, 245, 255)), 2, 162)
    foto = (tepi, tepi, cw - 2 * tepi, ch - 2 * tepi)
    # tiket kereta karton kecil (Edmondson) di pojok bawah, di depan foto
    tw, th = round(w * 0.46), round(w * 0.46 * 0.56)
    t = Image.new("RGBA", (tw, th), (206, 226, 210, 255))
    g = ImageDraw.Draw(t)
    for k in range(0, tw + th, 7):  # pola garis halus pengaman
        g.line((k, 0, k - th, th), fill=(194, 216, 199, 255), width=1)
    t = tekstur(t, 4, 163)
    g = ImageDraw.Draw(t)
    mt = round(tw * 0.06)
    hijau = (34, 70, 52)
    g.text((mt, mt * 0.8), isi(data, "kelas", "2ND CLASS · SINGLE"), font=bs(tw * 0.045, "Bold SemiCondensed"),
           fill=hijau)
    g.text((tw - mt, mt * 0.8), "No. " + isi(data, "nomor", "04721"), font=hf("ocr", tw * 0.04), fill=hijau, anchor="ra")
    fl = bs(tw * 0.04, "SemiCondensed")
    fb = bs(tw * 0.085, "Bold SemiCondensed")
    g.text((mt, th * 0.28), "FROM", font=fl, fill=(80, 110, 92))
    fv, bv = judul_pas(g, isi(data, "dari", "PONTIANAK").upper(), "koran", tw - 2 * mt, tw * 0.08, 1)
    g.text((mt, th * 0.28 + fl.size * 1.2), isi(data, "dari", "PONTIANAK").upper(), font=fb, fill=hijau)
    g.text((mt, th * 0.55), "TO", font=fl, fill=(80, 110, 92))
    ke = isi(data, "ke", "SOMEWHERE QUIET").upper()
    f2 = fb
    while g.textlength(ke, font=f2) > tw - 2 * mt and f2.size > 10:
        f2 = bs(f2.size - 2, "Bold SemiCondensed")
    g.text((mt, th * 0.55 + fl.size * 1.2), ke, font=f2, fill=hijau)
    g.text((mt, th - mt), isi(data, "tanggal", hari_ini("%d %b %Y")) + "  ·  VALID FOR ONE JOURNEY",
           font=bs(tw * 0.035, "SemiCondensed"), fill=hijau, anchor="lb")
    g.text((tw - mt, th - mt), isi(data, "harga", "Rp 0"), font=bs(tw * 0.06, "Bold SemiCondensed"), fill=hijau,
           anchor="rb")
    r = round(th * 0.07)
    g.ellipse((tw * 0.82 - r, th * 0.42 - r, tw * 0.82 + r, th * 0.42 + r), fill=(0, 0, 0, 0))  # lubang plong
    depan = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tempel(depan, t, w * 0.66, h * 0.8, 9, 0.4)
    return {"latar": latar, "kartu": kartu, "kotak": foto, "sudut": -3, "pusat": (w * 0.46, h * 0.45),
            "depan": depan, "dorong": False}


# --------------------------------------------------------------------------------------------- 15 JURNAL
def daun(d, x, y, panjang, sudut, warna):
    """Ranting kecil dengan daun (coretan hiasan)."""
    ex, ey = x + panjang * math.cos(sudut), y + panjang * math.sin(sudut)
    d.line((x, y, ex, ey), fill=warna, width=3)
    for k in range(1, 6):
        t = k / 6
        px, py = x + (ex - x) * t, y + (ey - y) * t
        for sisi in (-1, 1):
            a = sudut + sisi * 0.8
            l = panjang * 0.18 * (1 - t * 0.4)
            qx, qy = px + l * math.cos(a), py + l * math.sin(a)
            d.line((px, py, qx, qy), fill=warna, width=2)
            d.ellipse((qx - l * 0.25, qy - l * 0.25, qx + l * 0.25, qy + l * 0.25), outline=warna, width=2)


def tata_jurnal(data, w, h, kecil):
    from desain import tempel
    latar = bahan.buat("linen", w, h, 171, warna=(214, 204, 188))
    cw, ch = round(w * 0.84), round(h * 0.9)
    kartu = tekstur(Image.new("RGBA", (cw, ch), (250, 247, 240, 255)), 3, 172)
    d = ImageDraw.Draw(kartu)
    jarak = cw * 0.045
    for yy in range(round(jarak), ch, round(jarak)):  # titik kisi buku dot-grid
        for xx in range(round(cw * 0.12), cw, round(jarak)):
            d.ellipse((xx - 1.4, yy - 1.4, xx + 1.4, yy + 1.4), fill=(200, 196, 190, 255))
    # lubang & ring spiral di kiri
    for yy in range(round(ch * 0.03), ch, round(ch * 0.045)):
        d.ellipse((cw * 0.035, yy, cw * 0.065, yy + cw * 0.03), fill=(0, 0, 0, 0))
    m = round(cw * 0.12)
    tinta_ = (52, 46, 66)
    d.text((cw - cw * 0.06, cw * 0.05), isi(data, "tanggal", hari_ini("%d.%m.%y")), font=hf("tangan", cw * 0.045),
           fill=tinta_, anchor="ra")
    fj, bj = judul_pas(d, isi(data, "judul", "things I want to remember"), "tangan", cw * 0.6, cw * 0.075, 2)
    y = cw * 0.05
    for b in bj:
        d.text((m, y), b, font=fj, fill=tinta_)
        y += fj.size * 1.1
    d.line((m, y + 4, m + cw * 0.45, y + 10), fill=(220, 140, 120), width=4)  # garis bawah stabilo
    y += cw * 0.05
    fw_ = round(cw * 0.56)
    foto = (m, round(y), fw_, round(fw_ * 1.15))
    # catatan kecil + panah di samping foto
    fx = m + fw_ + cw * 0.04
    fn = hf("tangan", cw * 0.04)
    yy = foto[1] + cw * 0.06
    for b in bungkus(d, isi(data, "catatan", "me, pretending this was planned"), fn, cw - fx - cw * 0.05)[:4]:
        d.text((fx, yy), b, font=fn, fill=tinta_)
        yy += fn.size * 1.2
    ax, ay = fx + cw * 0.02, yy + cw * 0.02
    d.line((ax + cw * 0.08, ay, ax, ay + cw * 0.08), fill=tinta_, width=3)
    d.line((ax, ay + cw * 0.08, ax + cw * 0.035, ay + cw * 0.075), fill=tinta_, width=3)
    d.line((ax, ay + cw * 0.08, ax + cw * 0.005, ay + cw * 0.045), fill=tinta_, width=3)
    daun(d, fx + cw * 0.05, foto[1] + foto[3] - cw * 0.02, cw * 0.2, -1.2, (110, 130, 96))
    y = foto[1] + foto[3] + cw * 0.06
    fi = hf("tangan", cw * 0.042)
    for b in bungkus(d, isi(data, "isi", "the light came in sideways and for once I didn't reach for my phone right "
                                       "away. Small list: cold coffee, the song I keep replaying, a sky that "
                                       "couldn't decide on a colour. Today was soft. I want more days like this."),
                     fi, cw - m - cw * 0.06):
        if y > ch - cw * 0.08:
            break
        d.text((m, y), b, font=fi, fill=tinta_)
        y += fi.size * 1.45
    # bintang coretan
    sx, sy, r = cw * 0.86, ch * 0.08 + cw * 0.08, cw * 0.035
    titik = [(sx + r * (1 if k % 2 == 0 else 0.45) * math.cos(-math.pi / 2 + k * math.pi / 5),
              sy + r * (1 if k % 2 == 0 else 0.45) * math.sin(-math.pi / 2 + k * math.pi / 5)) for k in range(11)]
    d.line(titik, fill=(230, 170, 60), width=3)
    atas = Image.new("RGBA", kartu.size, (0, 0, 0, 0))
    for (px, py, s) in ((foto[0] + cw * 0.02, foto[1], -30), (foto[0] + fw_ - cw * 0.02, foto[1] + foto[3], -30)):
        pita = selotip(round(cw * 0.16), round(cw * 0.045), 173)
        gp = ImageDraw.Draw(pita)
        for k in range(0, pita.width, 10):  # selotip washi bergaris
            gp.line((k, 0, k, pita.height), fill=(220, 150, 140, 90), width=4)
        tempel(atas, pita, px, py, s, 0)
    # ring spiral logam di atas lubang
    for yy in range(round(ch * 0.03), ch, round(ch * 0.045)):
        ImageDraw.Draw(atas).arc((-cw * 0.02, yy - cw * 0.012, cw * 0.06, yy + cw * 0.045), 200, 340,
                                 fill=(150, 150, 156, 255), width=max(3, round(cw * 0.008)))
    return {"latar": latar, "kartu": kartu, "kotak": foto, "atas": atas, "sudut": -2, "pusat": (w * 0.52, h / 2),
            "depan": None, "dorong": False}


# -------------------------------------------------------------------------------------- 16 STRUK LAGU
LAGU_BAWAAN = ("Video Games - Lana Del Rey 4:41|Summertime Sadness - Lana Del Rey 4:25|"
               "Young and Beautiful - Lana Del Rey 3:56|Cinnamon Girl - Lana Del Rey 5:00|"
               "Say Yes to Heaven - Lana Del Rey 3:29|Born to Die - Lana Del Rey 4:46|"
               "West Coast - Lana Del Rey 4:16|Brooklyn Baby - Lana Del Rey 5:51")


def lapisan_kusut(w, h, seed, kuat=1.0):
    """Peta kertas kusut sebagai lapisan RGBA: bagian lebih gelap = hitam transparan, lebih terang = putih
    transparan. Ditaruh di atas kertas DAN foto, jadi fotonya ikut terlihat tercetak di kertas yang kusut."""
    import numpy as np
    k = bahan.kusut(w, h, seed, kuat)
    gelap = np.clip((1 - k) * 255 * 2.2, 0, 255)
    terang = np.clip((k - 1) * 255 * 1.6, 0, 255)
    a = np.zeros((h, w, 4), np.uint8)
    putih = terang > gelap
    a[..., :3] = np.where(putih[..., None], 255, 0)
    a[..., 3] = np.where(putih, terang, gelap).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


def tata_playlist(data, w, h, kecil):
    """Struk belanja yang isinya daftar lagu (judul - penyanyi, durasi), total waktu dihitung otomatis."""
    import re
    latar = bahan.buat("beton", w, h, 181, warna=(214, 212, 208))
    rw = round(min(w * 0.68, h * 0.38))
    rh = round(h * 0.93)
    kartu = Image.new("RGBA", (rw, rh), (242, 242, 240, 255))
    d = ImageDraw.Draw(kartu)
    hitam = (40, 40, 44)
    m = round(rw * 0.07)
    fj = bs(rw * 0.085, "Bold")
    y = rw * 0.08
    judul = isi(data, "judul", "LATE NIGHT RECEIPT").upper()
    while d.textlength(judul, font=fj) > rw - 2 * m and fj.size > 20:
        fj = bs(fj.size - 2, "Bold")
    d.text((rw / 2, y), judul, font=fj, fill=hitam, anchor="mt")
    y += fj.size * 1.35
    fs = bs(rw * 0.034, "SemiCondensed")
    d.text((rw / 2, y), isi(data, "periode", "LAST MONTH").upper(), font=fs, fill=hitam, anchor="mt")
    y += fs.size * 2.0
    fn = hf("konsol", rw * 0.033)
    tb = fn.size * 1.5
    foto = (m, round(y), rw - 2 * m, round(rh * 0.2))
    y += foto[3] + tb * 0.7
    nama = isi(data, "nama", "FELIX").upper()
    for b in bungkus(d, f"ORDER #{isi(data, 'nomor', '0001')} FOR {nama}", fn, rw - 2 * m):
        d.text((m, y), b, font=fn, fill=hitam)
        y += tb
    d.text((m, y), isi(data, "tanggal", datetime.date.today().strftime("%A, %B %d, %Y")).upper(), font=fn, fill=hitam)
    y += tb

    def putus():
        nonlocal y
        for x in range(m, rw - m, round(fn.size * 0.6)):
            d.line((x, y + tb * 0.35, x + fn.size * 0.3, y + tb * 0.35), fill=hitam, width=2)
        y += tb * 0.7

    putus()
    kol_item, kol_amt = m + d.textlength("00  ", font=fn), rw - m
    d.text((m, y), "QTY", font=fn, fill=hitam)
    d.text((kol_item, y), "ITEM", font=fn, fill=hitam)
    d.text((kol_amt, y), "AMT", font=fn, fill=hitam, anchor="ra")
    y += tb
    putus()
    lagu = [x.strip() for x in isi(data, "lagu", LAGU_BAWAAN).split("|") if x.strip()][:12]
    total = 0
    lebar_item = kol_amt - kol_item - d.textlength(" 00:00", font=fn)
    for i, l in enumerate(lagu):
        cocok = re.search(r"\s(\d{1,2}):(\d{2})$", l)
        dur = ""
        if cocok:
            dur = f"{int(cocok.group(1))}:{cocok.group(2)}"
            total += int(cocok.group(1)) * 60 + int(cocok.group(2))
            l = l[:cocok.start()].strip()
        d.text((m, y), f"{i + 1:02d}", font=fn, fill=hitam)
        d.text((kol_amt, y), dur, font=fn, fill=hitam, anchor="ra")
        for j, b in enumerate(bungkus(d, l.upper(), fn, lebar_item)[:2]):
            d.text((kol_item, y), b, font=fn, fill=hitam)
            y += tb
        y += tb * 0.15
    putus()
    d.text((m, y), "ITEM COUNT:", font=fn, fill=hitam)
    d.text((kol_amt, y), str(len(lagu)), font=fn, fill=hitam, anchor="ra")
    y += tb
    d.text((m, y), "TOTAL:", font=fn, fill=hitam)
    jam, sisa = divmod(total, 3600)
    d.text((kol_amt, y), (f"{jam}:{sisa // 60:02d}:{sisa % 60:02d}" if jam else f"{sisa // 60}:{sisa % 60:02d}"),
           font=fn, fill=hitam, anchor="ra")
    y += tb
    putus()
    kode = int(hashlib.md5((nama + judul).encode()).hexdigest()[:6], 16) % 1000000
    for b in (f"CARD #: **** **** **** {isi(data, 'tahun', hari_ini('%Y'))}", f"AUTH CODE: {kode:06d}",
              f"CARDHOLDER: {nama}"):
        d.text((m, y), b, font=fn, fill=hitam)
        y += tb
    y += tb * 0.5
    d.text((rw / 2, y), isi(data, "penutup", "THANK YOU FOR LISTENING!").upper(), font=fn, fill=hitam, anchor="mt")
    y += tb * 1.3
    garis_kode(d, rw * 0.18, y, rw * 0.64, rw * 0.11, judul + nama, hitam)
    y += rw * 0.13
    d.text((rw / 2, y), isi(data, "kaki", "made with hangat studio").lower(), font=fn, fill=hitam, anchor="mt")
    rh = min(rh, round(y + rw * 0.13))  # panjang struk mengikuti isinya
    teks = kartu.crop((0, 0, rw, rh))
    kartu = Image.new("RGBA", (rw, rh), (242, 242, 240, 255))
    kartu.alpha_composite(tinta(teks, 0.97, 182))  # tinta thermal tidak rata
    atas = lapisan_kusut(rw, rh, 183, 0.7)
    return {"latar": latar, "kartu": kartu, "kotak": foto, "atas": atas, "sudut": 1.5, "pusat": (w / 2, h / 2),
            "depan": None, "dorong": False, "bayangan": 0.4,
            "efek": ["hue=s=0,eq=contrast=1.3:brightness=0.05:gamma=1.1"]}


GAYA_LAIN = {"boarding": tata_boarding, "kaset": tata_kaset, "vinyl": tata_vinyl, "filmstrip": tata_filmstrip,
             "kartupos": tata_kartupos, "struk": tata_struk, "paspor": tata_paspor, "museum": tata_museum,
             "perpustakaan": tata_perpustakaan, "photobooth": tata_photobooth, "surat": tata_surat, "vhs": tata_vhs,
             "lost": tata_lost, "kereta": tata_kereta, "jurnal": tata_jurnal, "playlist": tata_playlist}
RASIO_LAIN = {"boarding": "9:16", "kaset": "4:5", "vinyl": "4:5", "filmstrip": "9:16", "kartupos": "4:5",
              "struk": "9:16", "paspor": "4:5", "museum": "4:5", "perpustakaan": "4:5", "photobooth": "9:16",
              "surat": "4:5", "vhs": "9:16", "lost": "4:5", "kereta": "4:5", "jurnal": "4:5", "playlist": "9:16"}
WARNA_LAIN = {"boarding": "terang", "kaset": "vintage", "vinyl": "film", "filmstrip": "vintage", "kartupos": "matte",
              "struk": "natural", "paspor": "matte", "museum": "film", "perpustakaan": "vintage", "photobooth": "natural",
              "surat": "golden", "vhs": "vhs", "lost": "natural", "kereta": "matte", "jurnal": "golden", "playlist": "natural"}

# Isian yang bisa diedit per desain (dipakai UI untuk membuat form otomatis):
# (kunci, label, contoh/bawaan, jenis) — jenis: teks | panjang (paragraf) | daftar (satu baris per item -> "a|b|c")
ISIAN_LAIN = {
    "boarding": [("maskapai", "Maskapai", "HANGAT AIR", "teks"), ("dari", "Kode asal", "PNK", "teks"),
                 ("kota_dari", "Kota asal", "Pontianak", "teks"), ("ke", "Kode tujuan", "JOG", "teks"),
                 ("kota_ke", "Kota tujuan", "Yogyakarta", "teks"), ("nama", "Penumpang", "THE DREAMER", "teks"),
                 ("penerbangan", "Nomor penerbangan", "HG 1907", "teks"), ("tanggal", "Tanggal", "20 OCT", "teks"),
                 ("gerbang", "Gate", "B7", "teks"), ("kursi", "Kursi", "12A", "teks"), ("jam", "Boarding", "06:40", "teks"),
                 ("kelas", "Kelas", "WINDOW SEAT DREAMS", "teks"),
                 ("catatan", "Catatan tulisan tangan", "gate closes when the sun goes down", "teks")],
    "kaset": [("judul", "Judul mixtape", "songs for 2 a.m.", "teks"), ("nama", "Nama kecil", "a mixtape", "teks"),
              ("tahun", "Tahun", "2026", "teks"), ("sisi", "Sisi", "A", "teks"), ("durasi", "Tipe kaset", "C-60", "teks"),
              ("lagu", "Daftar lagu", "video games\nsummertime sadness\nyoung and beautiful", "daftar")],
    "vinyl": [("nama", "Nama artis/band", "THE QUIET ONES", "teks"), ("judul", "Judul album", "Golden Hour Tapes", "teks"),
              ("stiker", "Teks stiker", "includes the single 'late night'", "teks")],
    "filmstrip": [("judul", "Label selotip", "roll 07 · summer '26", "teks"), ("catatan", "Coretan", "this one", "teks"),
                  ("film", "Merek film", "HANGAT 400", "teks"), ("nomor", "Nomor frame awal", "12", "teks")],
    "kartupos": [("pesan", "Pesan", "Dear you, the light here turns gold around five...", "panjang"),
                 ("dari", "Dari", "— F.", "teks"), ("untuk", "Alamat (3 baris)", "to: someone who needs this\n"
                                                                              "wherever you are\nthe world", "daftar"),
                 ("tempat", "Cap pos", "PONTIANAK", "teks"), ("negara", "Tulisan perangko", "HOME", "teks"),
                 ("nilai", "Nilai perangko", "2026", "teks")],
    "struk": [("nama", "Nama toko", "THE GOOD DAY STORE", "teks"), ("tempat", "Alamat", "PONTIANAK, ID", "teks"),
              ("telp", "Telepon", "TEL. 0800-SLOW-DOWN", "teks"), ("tanggal", "Tanggal", "20/10/2026", "teks"),
              ("jam", "Jam", "17:42", "teks"), ("kasir", "Kasir", "YOU", "teks"), ("nomor", "No. struk", "0019", "teks"),
              ("barang", "Barang (nama:harga)", "golden hour:0.00\ncold coffee x2:4.50", "daftar"),
              ("subtotal", "Subtotal", "5.49", "teks"), ("total", "Total", "PRICELESS", "teks"),
              ("bayar", "Dibayar dengan", "TIME", "teks"), ("kembali", "Kembalian", "A GOOD MOOD", "teks"),
              ("penutup", "Penutup", "THANK YOU FOR STAYING\nplease come again", "daftar")],
    "paspor": [("nama", "Surname", "DREAMER", "teks"), ("nama_depan", "Given names", "THE QUIET ONE", "teks"),
               ("kebangsaan", "Nationality", "SOMEWHERE IN BETWEEN", "teks"),
               ("lahir", "Date of birth", "A SUMMER, LONG AGO", "teks"), ("tempat", "Place of birth", "PONTIANAK", "teks"),
               ("tanggal", "Date of issue", "20 OCT 2026", "teks"), ("berlaku", "Date of expiry", "NEVER", "teks"),
               ("ttd", "Tanda tangan", "Your Name", "teks"), ("nomor", "Nomor paspor", "A0192026", "teks"),
               ("cap", "Cap perjalanan (tempat:tanggal)", "GOLDEN HOUR:20 OCT 2026\nLATE NIGHTS:ALWAYS", "daftar")],
    "museum": [("seniman", "Seniman", "Your Name", "teks"), ("asal", "Asal, tahun lahir", "Indonesian, b. 2000", "teks"),
               ("judul", "Judul karya", "Learning to Stay", "teks"), ("tahun", "Tahun", "2026", "teks"),
               ("medium", "Medium", "Golden hour and a phone camera", "teks"),
               ("deskripsi", "Deskripsi", "A small, unremarkable evening...", "panjang")],
    "perpustakaan": [("penulis", "Author", "Your Name", "teks"), ("judul", "Title", "Notes on Slow Evenings", "teks"),
                     ("peminjam", "Peminjam (nama:tanggal)", "yourname:20 OCT 26\na quiet afternoon:02 NOV 26", "daftar"),
                     ("perpus", "Nama perpustakaan", "THE QUIET LIBRARY", "teks")],
    "photobooth": [("teks", "Tulisan bawah", "OCT 20 2026 - PONTIANAK", "teks"),
                   ("warna_strip", "Warna foto (ketik 'warna' untuk berwarna)", "hitam-putih", "teks")],
    "surat": [("tanggal", "Tanggal", "20 october", "teks"), ("untuk", "Pembuka", "Dear you,", "teks"),
              ("pesan", "Isi surat", "I found this moment and thought of you...", "panjang"),
              ("dari", "Dari", "— F.", "teks"), ("inisial", "Inisial segel", "F", "teks")],
    "vhs": [("label", "Label atas", "HANGAT HOME VIDEO", "teks"), ("judul", "Judul film", "Late Night Feelings", "teks"),
            ("tagline", "Tagline", "some nights stay with you forever.", "teks"), ("durasi", "Durasi (menit)", "92", "teks"),
            ("tahun", "Tahun", "2026", "teks"), ("stiker", "Stiker (2 baris)", "BE KIND\nREWIND", "daftar")],
    "lost": [("judul", "Judul besar", "LOST", "teks"), ("sub", "Yang hilang", "my sense of time", "teks"),
             ("isi", "Keterangan", "Last seen somewhere between golden hour and 2 a.m. ...", "panjang"),
             ("hadiah", "Hadiah", "REWARD: a good conversation", "teks"), ("kontak", "Kontak (sobekan)", "@yourname", "teks")],
    "kereta": [("dari", "Dari", "PONTIANAK", "teks"), ("ke", "Ke", "SOMEWHERE QUIET", "teks"),
               ("kelas", "Kelas", "2ND CLASS · SINGLE", "teks"), ("tanggal", "Tanggal", "20 OCT 2026", "teks"),
               ("harga", "Harga", "Rp 0", "teks"), ("nomor", "Nomor tiket", "04721", "teks")],
    "jurnal": [("tanggal", "Tanggal", "20.10.26", "teks"), ("judul", "Judul halaman", "things I want to remember", "teks"),
               ("catatan", "Catatan di samping foto", "me, pretending this was planned", "teks"),
               ("isi", "Isi jurnal", "the light came in sideways...", "panjang")],
    "playlist": [("judul", "Judul struk", "LATE NIGHT RECEIPT", "teks"), ("periode", "Periode", "LAST MONTH", "teks"),
                 ("nama", "Nama", "FELIX", "teks"), ("nomor", "No. order", "0001", "teks"),
                 ("tanggal", "Tanggal", "TUESDAY, OCTOBER 20, 2026", "teks"),
                 ("lagu", "Lagu (Judul - Penyanyi 3:45)", "Video Games - Lana Del Rey 4:41\n"
                                                         "Summertime Sadness - Lana Del Rey 4:25", "daftar"),
                 ("penutup", "Penutup", "THANK YOU FOR LISTENING!", "teks"), ("kaki", "Tulisan paling bawah",
                                                                            "made with hangat studio", "teks")],
}
NAMA_LAIN = {"boarding": "Boarding Pass", "kaset": "Kaset Mixtape", "vinyl": "Piringan Hitam", "filmstrip": "Film Strip",
             "kartupos": "Kartu Pos", "struk": "Struk Belanja", "paspor": "Paspor", "museum": "Museum",
             "perpustakaan": "Kartu Perpustakaan", "photobooth": "Photobooth", "surat": "Surat & Amplop",
             "vhs": "Sampul VHS", "lost": "Poster LOST", "kereta": "Tiket Kereta", "jurnal": "Jurnal",
             "playlist": "Struk Lagu"}