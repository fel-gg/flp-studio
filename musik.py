"""Musik latar otomatis: pilih lagu yang cocok dari folder musik/ dan cari ketukannya (untuk montage).

- Taruh lagu bebas royalti (mp3/wav/m4a) di folder musik/. Kosong -> dibuatkan 2 musik bawaan yang lembut
  (disintesis sendiri, bebas hak cipta).
- Tiap lagu diukur sekali (tempo, energi, kecerahan) dan disimpan di musik/_ciri.json.
- Volume musik otomatis turun saat kamu bicara (ducking) — sudah dilakukan di autoedit.render.

    python musik.py            # daftar lagu + cirinya
"""
import json
import subprocess
from pathlib import Path

import numpy as np

FOLDER = Path(__file__).resolve().parent / "musik"
EKST = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
TANPA_JENDELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SR = 22050


def _pcm(path, sr=SR, maks=120):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", str(maks), "-ac", "1", "-ar", str(sr),
                        "-f", "f32le", "-"], capture_output=True, creationflags=TANPA_JENDELA)
    return np.frombuffer(r.stdout, np.float32)


def onset(x, sr=SR, hop=512):
    """Kekuatan 'serangan' bunyi per frame (spectral flux)."""
    n = 2048
    if len(x) < n * 4:
        return np.zeros(1), hop / sr
    jendela = np.hanning(n)
    frame = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * jendela
    spek = np.abs(np.fft.rfft(frame, axis=1))
    flux = np.maximum(np.diff(np.log1p(spek), axis=0), 0).sum(1)
    flux = flux - np.convolve(flux, np.ones(16) / 16, "same")
    return np.maximum(flux, 0), hop / sr


def tempo(env, dt):
    """BPM dari autokorelasi kekuatan onset (60-180 BPM)."""
    if len(env) < 64:
        return 0.0
    ac = np.correlate(env - env.mean(), env - env.mean(), "full")[len(env) - 1:]
    lo, hi = int(60 / 180 / dt), int(60 / 60 / dt)
    if hi >= len(ac):
        return 0.0
    lag = lo + int(np.argmax(ac[lo:hi]))
    # kesalahan oktaf: tempo cepat yang pantulan 2x-nya juga kuat kemungkinan setengah dari itu
    while 60 / (lag * dt) > 130 and 2 * lag < len(ac) and ac[2 * lag] > 0.5 * ac[lag]:
        lag *= 2
    return round(60 / (lag * dt), 1)


def ketukan(path, maks=120):
    """Daftar detik ketukan (beat) lagu: puncak onset yang paling selaras dengan tempo."""
    x = _pcm(path, maks=maks)
    env, dt = onset(x)
    bpm = tempo(env, dt)
    if not bpm:
        return []
    jarak = 60 / bpm / dt
    # cari fase terbaik: geser kisi ketukan, ambil yang total onsetnya paling besar
    fase = max(range(int(jarak)), key=lambda f: env[np.arange(f, len(env), jarak).astype(int)].sum())
    return [round(i * dt, 3) for i in np.arange(fase, len(env), jarak)]


def ciri(path):
    x = _pcm(path)
    if not len(x):
        return None
    env, dt = onset(x)
    spek = np.abs(np.fft.rfft(x[: SR * 30]))
    frek = np.fft.rfftfreq(len(x[: SR * 30]), 1 / SR)
    # denyut: seberapa jelas ketukannya (0 = ambient/pad, ~1 = drum tegas)
    ac = np.correlate(env - env.mean(), env - env.mean(), "full")[len(env) - 1:]
    bpm = tempo(env, dt)
    denyut = float(ac[int(60 / bpm / dt)] / (ac[0] + 1e-9)) if bpm else 0.0
    return {"bpm": bpm, "denyut": round(max(0.0, denyut), 2), "energi": round(float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9)), 1),
            "terang": round(float((spek * frek).sum() / (spek.sum() + 1e-9)), 0),
            "durasi": round(len(x) / SR, 1)}


def daftar():
    """[(path, ciri)] semua lagu di folder musik (ciri di-cache)."""
    FOLDER.mkdir(exist_ok=True)
    if not any(f.suffix.lower() in EKST for f in FOLDER.iterdir()):
        buat_bawaan()
    cache_f = FOLDER / "_ciri.json"
    try:
        cache = json.loads(cache_f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    hasil, berubah = [], False
    for f in sorted(FOLDER.iterdir()):
        if f.suffix.lower() not in EKST:
            continue
        kunci = f"{f.name}:{f.stat().st_mtime_ns}"
        if kunci not in cache:
            cache[kunci] = ciri(f)
            berubah = True
        if cache[kunci]:
            hasil.append((f, cache[kunci]))
    if berubah:
        cache_f.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return hasil


def pilih(suasana="tenang", seed=0):
    """Lagu paling cocok: 'tenang' (video bicara/refleksi: pelan, lembut, tidak terlalu terang) atau
    'ceria' (vlog/montage: lebih cepat & bertenaga). seed memutar pilihan di antara yang hampir sama bagusnya."""
    lagu = daftar()
    if not lagu:
        return None

    def skor(c):
        bpm = c["bpm"] if c.get("denyut", 0) > 0.15 else 70  # tanpa ketukan jelas = ambient, dihitung pelan
        if suasana == "ceria":
            return -abs(bpm - 112) / 30 + (c["energi"] + 30) / 15 + c.get("denyut", 0) * 3
        return (-abs(bpm - 78) / 25 - max(0, c["terang"] - 2200) / 1500 - max(0, c["energi"] + 16) / 10
                - c.get("denyut", 0) * 3)

    urut = sorted(lagu, key=lambda x: skor(x[1]), reverse=True)
    teratas = urut[: max(1, min(3, len(urut)))]
    return teratas[seed % len(teratas)][0]


# ------------------------------------------------------------------------- musik bawaan (sintesis sendiri)
def _not(n):
    return 440 * 2 ** ((n - 69) / 12)


def _pad(frek, durasi, sr=44100):
    t = np.arange(int(durasi * sr)) / sr
    s = sum(np.sin(2 * np.pi * f * t * (1 + d)) for f in frek for d in (-0.002, 0.002)) / (len(frek) * 2)
    serang = np.minimum(1, t / 1.2)
    lepas = np.minimum(1, (durasi - t) / 1.5)
    return s * serang * np.clip(lepas, 0, 1)


def _petik(f, durasi, sr=44100):
    t = np.arange(int(durasi * sr)) / sr
    s = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t))
    return s * np.exp(-t * 3.2) * np.minimum(1, t / 0.005)


def buat_bawaan():
    """Dua musik latar lembut (Fmaj7-Em7-Dm7-Cmaj7), diproses ffmpeg (low-pass + gema) supaya hangat."""
    FOLDER.mkdir(exist_ok=True)
    sr = 44100
    akor = [[53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [48, 52, 55, 59]]
    for nama, bpm, petik in (("bawaan_hangat_pelan", 70, False), ("bawaan_hangat_ringan", 92, True)):
        ketuk = 60 / bpm
        bar = ketuk * 4
        total = []
        rng = np.random.default_rng(len(nama))
        for ulang in range(4):
            for a in akor:
                blok = _pad([_not(n) for n in a] + [_not(a[0] - 12)], bar + 1.5) * 0.5
                if petik:
                    for b in range(8):  # arpeggio lembut tiap setengah ketukan
                        n = a[[0, 2, 1, 3, 2, 1, 3, 2][b]] + 12
                        mulai = int(b * ketuk / 2 * sr)
                        p = _petik(_not(n), 1.2) * rng.uniform(0.18, 0.26)
                        blok[mulai:mulai + len(p)] += p[: len(blok) - mulai]
                total.append(blok)
        n_bar = int(bar * sr)
        keluar = np.zeros(n_bar * len(total) + sr * 3)
        for i, b in enumerate(total):  # tumpang-tindih sedikit supaya akor menyambung
            keluar[i * n_bar:i * n_bar + len(b)] += b
        keluar /= np.abs(keluar).max() + 1e-9
        mentah = FOLDER / f"_{nama}.f32"
        mentah.write_bytes((keluar * 0.8).astype(np.float32).tobytes())
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", str(mentah),
                        "-af", "lowpass=f=3200,aecho=0.8:0.6:120|260:0.25|0.15,afade=t=in:d=2,"
                               "areverse,afade=t=in:d=3,areverse,loudnorm=I=-20",
                        "-ac", "2", "-b:a", "192k", str(FOLDER / f"{nama}.mp3")], check=True,
                       creationflags=TANPA_JENDELA)
        mentah.unlink()


if __name__ == "__main__":
    for f, c in daftar():
        print(f.name, c)
    print("tenang ->", pilih("tenang"))
    print("ceria  ->", pilih("ceria"))
