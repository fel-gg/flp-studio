"""Edit Pro sekali jalan: video mentah masuk, keluar proyek yang sudah diedit seperti editor profesional
(buang take gagal + jeda, jump cut dengan punch-in zoom, hook pembuka, subtitle, koreksi warna, musik yang
mengecil saat bicara, stabilisasi, suara dibersihkan). Pakai Gemini (sutradara.py) kalau bisa, kalau tidak
semuanya dihitung offline. Hasilnya proyek biasa: tetap bisa diubah di Full Edit lalu di-export.

    python pro.py video.mp4 [--audio suara.wav] [--rasio 9:16]
"""
import argparse
import json
from pathlib import Path

import autoedit as ae
import magic
import selera


def rasio_pas(video, rasio):
    """Orang awam tidak perlu memilih: video tegak -> 9:16 (Reels/TikTok), video lain dibiarkan."""
    if rasio and rasio != "asli":
        return rasio
    w, h, _ = ae.info_video(video)
    return "9:16" if h >= w else "asli"


def hook_dari_ucapan(kata, maks=9):
    """Kalimat (atau anak kalimat) pertama yang diucapkan = hook pembuka yang selalu nyambung. Tidak pernah
    dipotong di tengah kalimat: kalau kalimat pertama terlalu panjang, pakai bagian sampai koma pertama."""
    isi = [k["w"].strip() for k in kata if not ae.PENGISI.match(k["w"].strip())][:40]
    kalimat, koma = [], 0
    for w in isi:
        kalimat.append(w)
        if w[-1:] == "," and not koma:
            koma = len(kalimat)
        if w[-1:] in ".!?":
            break
    else:
        kalimat = []
    if len(kalimat) > maks:
        kalimat = kalimat[:koma] if 3 <= koma <= maks else []
    return " ".join(kalimat).strip(" ,.;") if len(kalimat) >= 3 else ""


def pecah_panjang(a, b, kata, target=4.0):
    """Bagian bicara yang panjang dipecah di akhir kalimat/anak kalimat setiap ~3-5 detik. Potongannya
    bersambung (tidak ada yang dibuang); gunanya supaya bingkai bisa berganti seperti editor memakai dua angle."""
    batas = [k["e"] for i, k in enumerate(kata) if a < k["e"] < b
             and (k["w"].rstrip()[-1:] in ".,!?;:" or (i + 1 < len(kata) and kata[i + 1]["s"] - k["e"] > 0.15))]
    hasil, mulai = [], a
    for t in batas:
        if t - mulai >= target * 0.75 and b - t >= 1.5:
            hasil.append((mulai, t))
            mulai = t
    return hasil + [(mulai, b)]


def potongan_jumpcut(kata, durasi):
    """Ritme editor: jeda lebih dari ~0,36 s dibuang (sisa jeda ~0,25 s, masih bernapas), lalu bingkai berganti
    selang-seling (punch-in 7%) di tiap potongan dan setiap ~4 detik bicara, supaya tidak ada gambar diam lama."""
    # bagian_dipakai membandingkan jeda SETELAH padding 0,12 s di kiri-kanan: 0,12 di sini = jeda asli > 0,36 s
    bagian = ae.bagian_dipakai(kata, durasi, jeda_maks=0.12) if kata else [(0.0, durasi)]
    pecah = [x for a, b in bagian if b - a > 0.25 for x in (pecah_panjang(a, b, kata) if kata else [(a, b)])]
    return [{"mulai": round(a, 3), "selesai": round(b, 3), "zoom": 1.07 if i % 2 else 1.0}
            for i, (a, b) in enumerate(pecah)] or [{"mulai": 0.0, "selesai": durasi, "zoom": 1.0}]


def ritme(pot, kata, maks=6.0):
    """Rencana Gemini kadang menyisakan potongan panjang dengan bingkai yang sama. Potongan > maks detik dipecah
    di akhir kalimat dan bingkainya diganti selang-seling, seperti di versi offline. Isi dan urutan tidak berubah."""
    hasil = []
    for x in pot:
        bagian = pecah_panjang(x["mulai"], x["selesai"], kata) if kata and x["selesai"] - x["mulai"] > maks else \
            [(x["mulai"], x["selesai"])]
        z = float(x.get("zoom", 1.0))
        for j, (a, b) in enumerate(bagian):
            y = {**x, "mulai": round(a, 3), "selesai": round(b, 3), "zoom": z if j % 2 == 0 else (1.0 if z > 1.001 else 1.07)}
            if j:
                y.pop("transisi", None)  # sambungan di dalam satu kalimat panjang: potong langsung
            hasil.append(y)
    return hasil


def ganti_bagian(pot, i):
    """Sambungan yang terasa seperti pindah bagian cerita: jeda panjang dibuang, atau potongan melompat
    mundur (cold open kembali ke awal). Di sambungan biasa editor cukup memotong langsung."""
    return i > 0 and (pot[i]["mulai"] - pot[i - 1]["selesai"] > 1.2 or pot[i]["mulai"] < pot[i - 1]["mulai"])


def transisi_halus(pot, jenis="blur"):
    """Transisi hanya di pergantian bagian, tidak di tiap jump cut (terlalu banyak transisi = terlihat amatir).
    Transisi yang sudah ditentukan rencana (Gemini) tidak diganti."""
    for i, x in enumerate(pot):
        if not x.get("transisi"):
            x["transisi"] = jenis if ganti_bagian(pot, i) else "potong"
    return pot


def offline(video, audio, rasio, sebab, log):
    log("Menyusun edit tanpa internet...")
    _, _, durasi = ae.info_video(video)
    sumber = video
    if audio:
        sumber = video.with_name(f"{video.stem}.{audio.stem}.sinkron.wav")
        if not sumber.exists():
            log("Menyinkronkan suara rekaman terpisah...")
            ae.siapkan_suara(video, audio, sumber, durasi)
    log("Mentranskrip suara...")
    cache = video.with_name(video.stem + (f".{audio.stem}" if audio else "") + ".kata.json")
    kata = ae.transkrip(sumber, None, cache)
    log("Mengukur warna...")
    r = magic.rekomendasi_offline(video, kata, sebab)
    bicara = len(kata) > 10
    pot = transisi_halus(potongan_jumpcut(kata, durasi))
    total = sum(p["selesai"] - p["mulai"] for p in pot)
    return {"sumber": [str(video)], "audio": str(audio) if audio else None, "musik": "auto", "rasio": rasio,
            "bingkai": "isi", "gaya": r["gaya"], "warna": r["warna"] or "", "judul": r["judul"] or "",
            "atur": r["atur"], "hook": (hook_dari_ucapan(kata) if bicara else "") or r["hook"],
            "durasi_hook": 3.0, "subtitle": bicara, "potongan": pot, "elemen": [], "stabil": True,
            "pro": {"model": "offline", "ringkasan": f"{durasi:.0f} detik jadi {total:.0f} detik, "
                                                     f"{len(pot)} potongan. {r['masalah']}"}}


def edit_pro(video, audio=None, rasio="asli", log=print):
    video, audio = Path(video), Path(audio) if audio else None
    rasio = rasio_pas(video, rasio)
    if magic.boleh_online() and magic.ada_kunci():
        try:
            import sutradara
            r = sutradara.buat_rencana(video, audio, rasio, log)
            video.with_name(video.stem + ".rencana.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
            # versi pertama = paling cocok menurut Gemini; kalau kamu sering memilih gaya tertentu, versi itu menang
            fav = selera.favorit("edit", "gaya")
            v = next((x for x in r["versi"] if x["gaya"] == fav), r["versi"][0])
            cache = video.with_name(video.stem + (f".{audio.stem}" if audio else "") + ".kata.json")
            kata = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else []
            # dipecah tanpa membuang apa pun: panjang timeline tetap, jadi waktu elemen teks tetap pas
            r["dasar"]["potongan"] = transisi_halus(ritme(r["dasar"].get("potongan") or [], kata))
            p = {**r["dasar"], "musik": "auto", "stabil": True, "gaya": v["gaya"], "warna": v["warna"] or "",
                 "judul": v["judul"] or "", "atur": v["atur"], "versi": v["nama"],
                 "pro": {"model": r["model"], "ringkasan": r["ringkasan"], "versi": r["versi"]}}
            return p
        except Exception as e:  # Gemini gagal (kuota, internet): tetap jadi, versi offline
            log(f"Gemini tidak bisa dipakai ({e}), lanjut tanpa internet...")
            return offline(video, audio, rasio, str(e)[:120], log)
    return offline(video, audio, rasio, "online dimatikan" if not magic.boleh_online() else "belum ada kunci API", log)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--rasio", default="asli")
    a = ap.parse_args()
    print(json.dumps(edit_pro(a.video, a.audio, a.rasio), ensure_ascii=False, indent=1))
