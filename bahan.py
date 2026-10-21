"""Latar dari bahan nyata (dibuat dengan kode, tanpa gambar dari internet): kayu, linen, kertas kraft, gabus,
beton, beludru, meja lampu. Plus cahaya jendela dari satu arah dan bayangan tirai tipis supaya terasa seperti
difoto di meja sungguhan, bukan latar polos.

    latar = bahan.buat("kayu", 1080, 1350, seed=3)  # RGBA
"""
import numpy as np
from PIL import Image, ImageFilter


def halus(w, h, skala, seed):
    """Noise lembut 0..1 (noise kecil yang diperbesar bikubik)."""
    rng = np.random.default_rng(seed)
    kw, kh = max(2, round(w / skala)), max(2, round(h / skala))
    a = Image.fromarray((rng.random((kh, kw)) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    return np.asarray(a, np.float32) / 255


def campur(gelap, terang, t):
    t = np.clip(t, 0, 1)[..., None]
    return np.asarray(gelap, np.float32) * (1 - t) + np.asarray(terang, np.float32) * t


def butir(a, kuat, seed):
    rng = np.random.default_rng(seed + 99)
    return a + rng.normal(0, kuat, a.shape[:2])[..., None]


def kayu(w, h, seed, gelap=(92, 62, 42), terang=(150, 108, 74), papan=4):
    """Papan kayu: serat memanjang yang bergelombang, tiap papan beda nada, celah gelap di antaranya."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    lebar = w / papan
    no = np.floor(x / lebar).astype(int)
    # serat = garis tipis memanjang searah papan: noise 1D halus per kolom, digeser pelan sepanjang papan
    n = 4 * w
    halus1 = lambda s, k: np.convolve(rng.random(n), np.ones(k) / k, "same")  # noqa: E731
    garis = halus1(0, 3) * 0.6 + halus1(0, 11) * 0.4
    kasar = np.convolve(rng.random(n), np.ones(60) / 60, "same")
    geser = (halus(w, h, 500, seed) - 0.5) * 18 + (halus(w, h, 120, seed + 1) - 0.5) * 4
    pos = np.clip((x + geser + no * w * 0.7).astype(int), 0, n - 1)
    serat = (garis[pos] - 0.5) * 2.2 + (kasar[pos] - 0.5) * 6
    nada = rng.uniform(-0.1, 0.1, papan + 1)[no]
    t = 0.5 + serat * 0.35 + nada + (halus(w, h, 250, seed + 3) - 0.5) * 0.15
    a = campur(gelap, terang, t)
    tepi = (x % lebar)
    a[tepi < 2] *= 0.42  # celah antar papan
    a[(tepi >= 2) & (tepi < 4)] *= 1.08  # pinggir papan sedikit tertangkap cahaya
    return butir(a, 2.5, seed)


def linen(w, h, seed, warna=(214, 206, 192)):
    """Kain linen: benang vertikal & horizontal dengan ketebalan acak, sedikit kusut."""
    rng = np.random.default_rng(seed)
    kol = rng.normal(0, 1, w)[None, :] * 0.5 + np.sin(np.arange(w) * 1.9)[None, :] * 0.5
    bar = rng.normal(0, 1, h)[:, None] * 0.5 + np.sin(np.arange(h) * 2.1)[:, None] * 0.5
    anyam = (kol + bar) * 5
    kusut = (halus(w, h, 220, seed) - 0.5) * 22 + (halus(w, h, 60, seed + 1) - 0.5) * 8
    a = np.asarray(warna, np.float32)[None, None, :] + (anyam + kusut)[..., None]
    return butir(a, 2.5, seed)


def kraft(w, h, seed, warna=(196, 164, 122)):
    """Kertas kraft: bercak lembut + serat pendek acak."""
    a = np.asarray(warna, np.float32)[None, None, :] + ((halus(w, h, 160, seed) - 0.5) * 9 +
                                                        (halus(w, h, 14, seed + 1) - 0.5) * 7 +
                                                        (halus(w, h, 3, seed + 2) - 0.5) * 8)[..., None]
    a = butir(a, 3.5, seed)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(seed + 5)
    for _ in range(w * h // 900):  # serat
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        sudut, pj = rng.uniform(0, np.pi), rng.uniform(4, 14)
        c = tuple(int(v) for v in np.asarray(warna) * rng.uniform(0.82, 1.12))
        d.line((x, y, x + np.cos(sudut) * pj, y + np.sin(sudut) * pj), fill=c, width=1)
    return np.asarray(img, np.float32)


def gabus(w, h, seed):
    """Papan gabus: butiran besar-kecil berwarna cokelat muda."""
    rng = np.random.default_rng(seed)
    a = np.zeros((h, w, 3), np.float32) + np.asarray((178, 134, 92), np.float32)
    for s, k in ((3, 30), (7, 22), (14, 14)):
        n = halus(w, h, s, seed + s)
        a += ((n - 0.5) * k)[..., None]
    bintik = rng.random((h, w)) < 0.012
    a[bintik] *= 0.7
    return a


def beton(w, h, seed, warna=(176, 172, 166)):
    a = np.asarray(warna, np.float32)[None, None, :] + ((halus(w, h, 300, seed) - 0.5) * 12 +
                                                        (halus(w, h, 30, seed + 1) - 0.5) * 8 +
                                                        (halus(w, h, 2.5, seed + 2) - 0.5) * 16)[..., None]
    rng = np.random.default_rng(seed)
    pori = rng.random((h, w)) < 0.004
    a[pori] *= 0.75
    return a


def beludru(w, h, seed, warna=(110, 26, 32)):
    """Tirai beludru: lipatan vertikal dengan sorotan lembut."""
    x = np.arange(w, dtype=np.float32)
    goyang = halus(w, 4, 80, seed)[0] * 30
    lipat = np.sin((x + goyang) / w * np.pi * 9) * 0.5 + 0.5
    lipat = lipat ** 1.6
    terang = 0.45 + lipat * 0.75
    a = np.asarray(warna, np.float32)[None, None, :] * terang[None, :, None] * np.ones((h, 1, 1), np.float32)
    return butir(a, 2, seed)


def meja_lampu(w, h, seed):
    """Meja lampu (lightbox) dengan bingkai aluminium di tepi dan cahaya yang tidak rata sempurna."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    terang = 246 - ((x / w - 0.45) ** 2 + (y / h - 0.4) ** 2) * 60 + (halus(w, h, 300, seed) - 0.5) * 8
    a = np.stack([terang, terang * 0.99, terang * 0.965], -1)
    bingkai = round(w * 0.035)
    for sl in (np.s_[:bingkai, :], np.s_[-bingkai:, :], np.s_[:, :bingkai], np.s_[:, -bingkai:]):
        a[sl] = a[sl] * 0 + np.asarray((150, 150, 152), np.float32)
    a[bingkai:bingkai + 3, bingkai:-bingkai] *= 0.8  # tepi bayangan dalam
    a[bingkai:-bingkai, bingkai:bingkai + 3] *= 0.85
    return butir(a, 2, seed)


def cahaya_jendela(a, seed, kuat=0.22, tirai=True):
    """Cahaya dari kiri atas meredup ke kanan bawah (bukan vinyet simetris) + bayangan tirai/daun tipis."""
    h, w = a.shape[:2]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    arah = (x / w * 0.6 + y / h * 0.8) / 1.4
    a = a * (1 + kuat * 0.6 - arah[..., None] * kuat)
    if tirai:
        rng = np.random.default_rng(seed)
        sudut = rng.uniform(0.5, 0.8)
        jarak = rng.uniform(70, 110) * w / 1080
        garis = np.sin((x * np.cos(sudut) + y * np.sin(sudut)) / jarak * 2 * np.pi)
        pola = (garis > 0.35).astype(np.float32)
        pola = np.asarray(Image.fromarray((pola * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(w * 0.02)), np.float32) / 255
        lembut = halus(w, h, 400, seed + 7)  # bayangan hanya di sebagian meja
        a = a * (1 - (pola * lembut * 0.09)[..., None])
    return a


def kusut(w, h, seed, kuat=1.0):
    """Peta terang-gelap kertas yang pernah diremas (1.0 = datar): bidang-bidang kecil dengan arah miring acak
    (Voronoi), lipatan tajam di batasnya, lalu diperhalus sedikit. Kalikan ke warna kertas."""
    rng = np.random.default_rng(seed)
    s = 3  # dihitung di resolusi 1/3 lalu diperbesar
    kw, kh = max(8, w // s), max(8, h // s)
    y, x = np.mgrid[0:kh, 0:kw].astype(np.float32)
    peta = np.zeros((kh, kw), np.float32)
    for skala, bobot in ((2600, 1.0), (500, 0.35)):  # lipatan besar + kerutan kecil
        n = max(12, kw * kh // skala)
        px, py = rng.uniform(0, kw, n), rng.uniform(0, kh, n)
        gx, gy = rng.normal(0, 1, n), rng.normal(0, 1, n)  # kemiringan tiap bidang
        jarak = (x[..., None] - px) ** 2 + (y[..., None] - py) ** 2
        urut = np.argpartition(jarak, 1, -1)[..., :2]
        dd = np.take_along_axis(jarak, urut, -1)
        tukar = dd[..., 0] > dd[..., 1]
        i0 = np.where(tukar, urut[..., 1], urut[..., 0])
        d0, d1 = np.sqrt(dd.min(-1)), np.sqrt(dd.max(-1))
        # tiap bidang condong ke arah acak: terang-gelapnya berubah halus di dalam bidang, patah di lipatan
        miring = ((x - px[i0]) * gx[i0] + (y - py[i0]) * gy[i0]) / np.sqrt(kw * kh / n)
        punggung = np.exp(-((d1 - d0) / 1.6) ** 2) * rng.choice([-1.0, 1.0], n)[i0]
        peta += bobot * (miring * 0.05 + punggung * 0.035)
    img = Image.fromarray(np.clip(peta * 255 + 128, 0, 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(2.2))
    return 1 + (np.asarray(img, np.float32) - 128) / 255 * kuat


BAHAN = {"kayu": kayu, "linen": linen, "kraft": kraft, "gabus": gabus, "beton": beton, "beludru": beludru,
         "meja_lampu": meja_lampu}


def buat(jenis, w, h, seed=1, tirai=True, **kw):
    a = BAHAN[jenis](w, h, seed, **kw)
    if jenis not in ("meja_lampu", "beludru"):
        a = cahaya_jendela(a, seed, tirai=tirai)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")
