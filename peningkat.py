"""Peningkat otomatis: suara dibersihkan sesuai kondisi rekamannya, video goyang distabilkan.

Semua diukur dari file-nya sendiri, jadi tidak ada setelan yang perlu dipilih pengguna.
"""
import json
import subprocess
from pathlib import Path

TANPA_JENDELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _pcm(path, sr=8000, maks=180):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", str(maks), "-ac", "1", "-ar", str(sr),
                        "-f", "f32le", "-"], capture_output=True, creationflags=TANPA_JENDELA)
    return np.frombuffer(r.stdout, dtype=np.float32)


def ukur_suara(path, kata=None):
    """{bising_db, bicara_db, snr, rendah, rata}: bising diukur di jeda antar kata (dari transkrip; tanpa
    transkrip: blok tersenyap), level bicara = persentil 90, dan porsi energi < 150 Hz (angin/dengung)."""
    import numpy as np
    sr = 8000
    x = _pcm(path, sr)
    n = sr // 40  # blok 25 ms: jeda pendek antar kalimat pun terhitung
    if len(x) < n * 40:
        return None
    blok = x[: len(x) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((blok ** 2).mean(1)) + 1e-9)
    hidup = db > -90  # bagian sunyi digital (awal/akhir rekaman) bukan bising
    t = (np.arange(len(blok)) + 0.5) * n / sr
    jeda = np.zeros(len(blok), bool)
    for a, b in zip(kata or [], (kata or [])[1:]):
        if b["s"] - a["e"] > 0.25:
            jeda |= (t > a["e"] + 0.08) & (t < b["s"] - 0.08)
    jeda &= hidup
    if jeda.sum() < 8:  # tidak ada transkrip/jeda: pakai blok tersenyap
        jeda = hidup & (db <= np.percentile(db[hidup], 5))
    bising, bicara = float(np.median(db[jeda])), float(np.percentile(db[hidup], 90))
    sepi = blok[jeda]
    spek = np.abs(np.fft.rfft(sepi, axis=1)) ** 2 + 1e-12
    rendah = float(spek[:, : int(150 / (sr / n)) + 1].sum() / spek.sum())
    # kerataan spektrum: desis/kipas/AC ~rata (>0.3); musik latar, gema, ramai orang bernada (<0.2)
    rata = float((np.exp(np.log(spek).mean(1)) / spek.mean(1)).mean())
    return {"bising_db": round(bising, 1), "bicara_db": round(bicara, 1),
            "snr": round(bicara - bising, 1), "rendah": round(rendah, 2), "rata": round(rata, 2)}


def rantai_suara(path, kata=None):
    """Filter suara yang pas untuk rekaman ini. Ukuran latensi tetap sama (afftdn 25 ms + alimiter 5 ms),
    jadi kompensasi di render tetap berlaku."""
    u = ukur_suara(path, kata)
    if not u:
        u = {"snr": 40, "rendah": 0, "bising_db": -60, "rata": 0}
    # Bawaan = setelan halus yang sudah terbukti enak (nr 8). Penghilang desis hanya dikuatkan untuk bising
    # yang rata (desis/kipas/AC): pada musik latar atau gema, afftdn kuat membuat suara "kaleng".
    nr, nf = 8, -40
    if u["snr"] > 40:
        nr = 6
    elif u["rata"] > 0.3 and u["snr"] < 25:
        nr = 18 if u["snr"] < 15 else 13
        nf = min(-25, max(-70, round(u["bising_db"] + 3)))
    # angin/dengung: potong bawah lebih tinggi (suara manusia mulai ~85 Hz, tidak hilang)
    keras = u["bising_db"] > -60  # bising yang nyaris tak terdengar tidak perlu diapa-apakan
    hp = 70 if not keras else 110 if u["rendah"] > 0.5 else 85 if u["rendah"] > 0.35 else 70
    return (f"highpass=f={hp},afftdn=nr={nr}:nf={nf}:tn=1,"
            "deesser=i=0.2:m=0.5:f=0.5,"  # bunyi "s" tajam dari mic HP diredam halus
            "acompressor=threshold=-18dB:ratio=2:attack=10:release=200:makeup=1"), u


def ukur_goyang(video, lebar=320, fps=10, maks=90):
    """Rata-rata getaran (px pada lebar 320) setelah gerak pelan kamera (pan) dibuang. ~>1.2 = goyang."""
    import cv2
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-t", str(maks), "-i", str(video), "-vf",
                        f"fps={fps},scale={lebar}:-2,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, creationflags=TANPA_JENDELA)
    if not r.stdout:
        return 0.0
    w = lebar
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True, creationflags=TANPA_JENDELA).stdout.strip().split(",")
    h = round(lebar * int(p[1]) / int(p[0]) / 2) * 2
    n = len(r.stdout) // (w * h)
    if n < 6:
        return 0.0
    f = np.frombuffer(r.stdout[: n * w * h], np.uint8).reshape(n, h, w).astype(np.float32)
    jendela = cv2.createHanningWindow((w, h), cv2.CV_32F)
    geser = np.array([cv2.phaseCorrelate(f[i], f[i + 1], jendela)[0] for i in range(n - 1)])
    jalur = np.cumsum(geser, 0)
    k = 5  # rata-rata bergerak 0.5 s = gerak yang disengaja
    halus = np.stack([np.convolve(jalur[:, j], np.ones(k) / k, mode="same") for j in range(2)], 1)
    sisa = (jalur - halus)[k:-k]
    return float(np.sqrt((sisa ** 2).sum(1)).mean()) if len(sisa) else 0.0


def stabilkan(video, ambang=1.2, log=print):
    """Video goyang -> versi stabil (disimpan di samping video dan dipakai ulang). Tidak goyang -> video asli.
    Pakai vidstab 2 tahap, gerak kamera yang disengaja tetap ada (smoothing 0.5 s), tepi di-zoom sedikit."""
    video = Path(video)
    catatan = video.with_name(f"{video.stem}.goyang.json")
    hasil = video.with_name(f"{video.stem}_stabil.mp4")
    kunci = video.stat().st_mtime_ns
    data = json.loads(catatan.read_text()) if catatan.exists() else {}
    if data.get("kunci") != kunci:
        data = {"kunci": kunci, "goyang": round(ukur_goyang(video), 2)}
        catatan.write_text(json.dumps(data))
    if data["goyang"] < ambang:
        return video
    if hasil.exists() and hasil.stat().st_mtime_ns > kunci:
        return hasil
    log(f"[stabil] video goyang ({data['goyang']}), distabilkan...")
    trf = video.with_name(f"{video.stem}.trf")
    cwd = video.parent  # path relatif: filter vidstab tidak suka "C:" di nilai opsi
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video.name, "-vf",
                    f"vidstabdetect=shakiness=6:accuracy=12:result={trf.name}", "-f", "null", "-"],
                   cwd=cwd, check=True, creationflags=TANPA_JENDELA)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video.name, "-vf",
                    f"vidstabtransform=input={trf.name}:smoothing=15:zoom=3:optzoom=0:interpol=bicubic,unsharp=5:5:0.4",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-c:a", "copy", hasil.name],
                   cwd=cwd, check=True, creationflags=TANPA_JENDELA)
    trf.unlink(missing_ok=True)
    return hasil
