"""Tombol Magic: Gemini melihat frame + transkrip, lalu memilih gaya teks, warna, judul, hook,
dan pengaturan warna manual (eksposur, suhu, dll) untuk video ini.

Yang dikirim ke Google: 8 frame JPEG kecil dan potongan transkrip. Video utuh tidak di-upload.
Kunci API dibaca dari GEMINI_API_KEY (environment) atau ~/.config/watch/.env.

    python magic.py video.mp4 [--kata video.kata.json]
"""
import argparse
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import autoedit as ae
import selera

MODEL = os.environ.get("AUTOEDIT_GEMINI_MODEL", "gemini-3.7-flash")
# Kunci gratis: tiap model dibatasi ±20 permintaan/hari, jadi kalau satu habis pindah ke model berikutnya.
# Yang "lite" paling akhir (lebih ringan, kualitas sedikit di bawah).
CADANGAN = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3.6-flash",
            "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]


KUOTA = Path(__file__).resolve().parent / "kuota_habis.json"


def hari_kuota():
    """Kuota harian Gemini direset tengah malam waktu Pasifik (±UTC-8)."""
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - 8 * 3600))


def model_urut():
    """Model utama + cadangan, tanpa yang kuotanya sudah tercatat habis hari ini."""
    try:
        habis = json.loads(KUOTA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        habis = {}
    semua = list(dict.fromkeys([MODEL, *CADANGAN]))
    return [m for m in semua if habis.get(m) != hari_kuota()] or semua


def tandai_habis(model):
    try:
        habis = json.loads(KUOTA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        habis = {}
    habis[model] = hari_kuota()
    KUOTA.write_text(json.dumps(habis), encoding="utf-8")


ENV = Path.home() / ".config" / "watch" / ".env"
SETELAN = Path(__file__).resolve().parent / "setelan.json"


def boleh_online():
    """Saklar di Setelan aplikasi; bawaan: boleh."""
    try:
        return json.loads(SETELAN.read_text(encoding="utf-8")).get("online", True)
    except (OSError, ValueError):
        return True


def simpan_setelan(online=None, kunci=None):
    if online is not None:
        SETELAN.write_text(json.dumps({"online": bool(online)}), encoding="utf-8")
    if kunci:  # ganti baris GEMINI_API_KEY, baris lain di file dibiarkan
        ENV.parent.mkdir(parents=True, exist_ok=True)
        baris = [b for b in (ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else [])
                 if not b.startswith("GEMINI_API_KEY=")]
        ENV.write_text("\n".join([*baris, f"GEMINI_API_KEY={kunci.strip()}"]) + "\n", encoding="utf-8")


def ada_kunci():
    try:
        return bool(kunci_api())
    except SystemExit:
        return False


def kunci_api():
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    if ENV.exists():
        for baris in ENV.read_text(encoding="utf-8").splitlines():
            if baris.startswith("GEMINI_API_KEY="):
                nilai = baris.split("=", 1)[1].strip().strip('"')
                if nilai:
                    return nilai
    raise SystemExit("Kunci API Gemini belum diisi. Buka Setelan lalu isi Kunci API Gemini "
                     "(gratis di aistudio.google.com/apikey). Fitur tanpa Gemini tetap bisa dipakai.")


def ambil_frame(video, durasi, n=8):
    """n frame merata, lebar 512 px, sebagai JPEG bytes."""
    hasil = []
    for i in range(n):
        t = durasi * (i + 0.5) / n
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                            "-vf", "scale=512:-2", "-q:v", "5", "-f", "image2", "-c:v", "mjpeg", "-"],
                           capture_output=True, creationflags=ae.TANPA_JENDELA)
        if r.stdout:
            hasil.append(r.stdout)
    return hasil


def prompt(kata, durasi, w, h, ukur=None):
    teks = " ".join(k["w"] for k in kata)[:2500] or "(tidak ada ucapan)"
    sumber = (f"Ini FOTO (bukan video), {w}x{h}, gambarnya di atas. Hook = judul yang menempel di foto; "
              "boleh string kosong kalau fotonya lebih bagus tanpa teks."
              if not durasi else
              f"Video: {durasi:.0f} detik, {w}x{h}. Di atas ada 8 frame merata dari video.\nTranskrip: \"{teks}\"")
    return f"""Kamu editor video & foto profesional untuk personal brand Instagram yang estetik dan hangat.
Pemiliknya mendokumentasikan dirinya belajar, bicara dalam bahasa Inggris.
{sumber}

Selera pemilik (wajib diikuti):
- Teks harus di BAWAH dan jelas terbaca. Dia tidak suka teks di samping/kiri wajah, jadi jangan pilih "sinematik".
- Dia suka nuansa warm aesthetic yang bersih; favoritnya "hangat-kotak" dan font kartun ala WoodFont.
- Gaya "bold" dan "pop" hanya untuk video tutorial yang energik.
{selera.ringkas()}

Tugasmu:
0. Nilai koreksi otomatis hasil ukur: {json.dumps(ukur or {}, ensure_ascii=False)}; pakai sebagai dasar koreksi,
   lalu sesuaikan untuk gaya (jangan menebak dari nol).
1. Nilai gambar seperti colorist: eksposur (terlalu gelap/terang?), white balance (terlalu kuning/biru/hijau?),
   kontras, saturasi, apakah ada wajah, suasana (dalam/luar ruangan, siang/malam).
2. Pilih gaya teks, preset warna, dan font judul yang paling cocok dengan suasana dan isi.
3. Atur koreksi manual supaya hasilnya enak dilihat: perbaiki dulu masalahnya (mis. terlalu gelap -> eksposur naik,
   terlalu kuning -> suhu turun), lalu sedikit sentuhan gaya. Jaga warna kulit tetap natural. Nilai kecil lebih baik
   daripada berlebihan; 0 = tidak diubah.
4. Tulis hook bahasa Inggris maksimal 7 kata yang membuat orang berhenti scroll, sesuai isi transkrip.
   Boleh pakai format judul 2 baris "baris kecil|Kata Besar" (contoh: "Day 12 of|Learning in Public").

Pilihan gaya teks: {json.dumps(ae.INFO_GAYA, ensure_ascii=False)}
Pilihan warna: {json.dumps(ae.INFO_WARNA, ensure_ascii=False)}
Pilihan font judul: {json.dumps(ae.INFO_JUDUL, ensure_ascii=False)}
Pengaturan manual (rentang): eksposur -100..100 (100 = +1 stop), kontras -100..100, saturasi -100..100,
suhu -100..100 (positif = lebih hangat), tint -100..100 (positif = magenta, negatif = hijau),
bayangan -100..100 (positif = angkat bayangan), sorotan -100..100 (negatif = redam highlight),
vignette 0..100, glow 0..100, tajam 0..100, grain 0..100.

Jawab dalam bahasa Indonesia untuk "alasan" dan "masalah" (singkat, 2-3 kalimat)."""


def skema():
    angka = {"type": "NUMBER"}
    return {
        "type": "OBJECT",
        "properties": {
            "masalah": {"type": "STRING"},
            "gaya": {"type": "STRING", "enum": list(ae.GAYA)},
            "warna": {"type": "STRING", "enum": list(ae.WARNA)},
            "judul": {"type": "STRING", "enum": list(ae.JUDUL)},
            "hook": {"type": "STRING"},
            "atur": {"type": "OBJECT", "properties": {k: angka for k in ae.ATUR}, "required": ae.ATUR},
            "alasan": {"type": "STRING"},
        },
        "required": ["masalah", "gaya", "warna", "judul", "hook", "atur", "alasan"],
    }


def panggil(model, isi, kunci):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(isi).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": kunci})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def minta_json(bagian, skema_jawab, suhu=0.6):
    """Kirim parts (gambar/teks) ke Gemini, jawaban JSON sesuai skema. Pakai urutan model + catatan kuota yang sama
    dengan Magic. Gagal/offline -> RuntimeError (pemanggil memakai cadangan offline-nya sendiri)."""
    if not boleh_online():
        raise RuntimeError("online dimatikan di Setelan")
    try:
        kunci = kunci_api()
    except SystemExit as e:
        raise RuntimeError(str(e))
    isi = {"contents": [{"role": "user", "parts": bagian}],
           "generationConfig": {"responseMimeType": "application/json", "responseSchema": skema_jawab,
                                "temperature": suhu}}
    galat = "tanpa model"
    for model in model_urut():
        try:
            jawab = panggil(model, isi, kunci)
            hasil = json.loads(jawab["candidates"][0]["content"]["parts"][0]["text"])
            hasil["model"] = model
            return hasil
        except urllib.error.HTTPError as e:
            badan = e.read().decode(errors="replace")
            galat = f"{model}: HTTP {e.code} {badan[:200]}"
            if e.code in (401, 403):
                break
            if "PerDay" in badan:
                tandai_habis(model)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            galat = f"tidak terhubung ({e.__class__.__name__})"
            break
        except (KeyError, IndexError, ValueError) as e:  # jawaban terpotong/aneh: coba model berikutnya
            galat = f"{model}: jawaban tidak terbaca ({e.__class__.__name__})"
    raise RuntimeError(galat)


def rekomendasi(video, kata=None):
    video = Path(video)
    w, h, durasi = ae.info_video(video)
    frame = ambil_frame(video, durasi, n=1 if ae.foto(video) else 8)
    bagian = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(f).decode()}} for f in frame]
    bagian.append({"text": prompt(kata or [], durasi, w, h, ae.atur_otomatis(video))})
    isi = {"contents": [{"role": "user", "parts": bagian}],
           "generationConfig": {"responseMimeType": "application/json", "responseSchema": skema(),
                                "temperature": 0.4}}
    if not boleh_online():
        return rekomendasi_offline(video, kata, "online dimatikan di Setelan")
    try:
        kunci = kunci_api()
    except SystemExit as e:
        return rekomendasi_offline(video, kata, str(e))
    galat = None
    # model utama dulu; kalau sibuk (503/429) coba lagi sebentar, lalu pindah ke model cadangan
    percobaan = [(m, ulang) for m in model_urut() for ulang in range(2)]
    habis = set()
    for model, ulang in percobaan:
        if model in habis:
            continue
        if ulang:
            time.sleep(4)
        try:
            jawab = panggil(model, isi, kunci)
            teks = jawab["candidates"][0]["content"]["parts"][0]["text"]
            hasil = json.loads(teks)
            hasil["model"] = model
            # jaga nilai tetap di rentangnya
            for k, v in hasil["atur"].items():
                lo = 0 if k in ("vignette", "glow", "tajam", "grain") else -100
                hasil["atur"][k] = max(lo, min(100, round(float(v))))
            return hasil
        except urllib.error.HTTPError as e:
            badan = e.read().decode(errors="replace")
            galat = f"{model}: HTTP {e.code} {badan[:300]}"
            if e.code in (401, 403):  # kunci API salah: percuma mencoba model lain
                break
            if "PerDay" in badan:  # kuota harian habis: catat, jangan dicoba lagi hari ini
                tandai_habis(model)
                habis.add(model)
        except (urllib.error.URLError, TimeoutError, OSError) as e:  # tidak ada internet
            galat = f"tidak terhubung ({e.__class__.__name__})"
            break
    return rekomendasi_offline(video, kata, galat)


def rekomendasi_offline(video, kata, sebab=""):
    """Tanpa internet/Gemini: koreksi dari hasil ukur + template paling aman (Vlog Hangat)."""
    atur = ae.atur_otomatis(video)
    tpl = ae.TEMPLATE["Vlog Hangat"]
    masalah = []
    if atur["eksposur"] > 10:
        masalah.append("gambar agak gelap, dicerahkan")
    elif atur["eksposur"] < -10:
        masalah.append("gambar agak terang, diredam")
    if atur["suhu"] < -5:
        masalah.append("warnanya terlalu kuning, dinetralkan")
    elif atur["suhu"] > 5:
        masalah.append("warnanya kebiruan, dihangatkan")
    if atur["sorotan"] < 0:
        masalah.append("bagian terang hampir terbakar, diredam")
    return {"masalah": ("Diukur offline: " + "; ".join(masalah) + ".") if masalah
            else "Diukur offline: eksposur dan warna sudah cukup baik.",
            # pilihan yang paling sering kamu ekspor menang atas template bawaan
            "gaya": selera.favorit("edit", "gaya") if selera.favorit("edit", "gaya") in ae.GAYA else tpl["gaya"],
            "warna": selera.favorit("edit", "warna") if selera.favorit("edit", "warna") in ae.WARNA else tpl["warna"],
            "judul": selera.favorit("edit", "judul") if selera.favorit("edit", "judul") in ae.JUDUL else tpl["judul"],
            "hook": ae.pilih_hook("auto"),
            "atur": atur, "alasan": f"Mode offline ({sebab or 'tanpa Gemini'}): template Vlog Hangat + koreksi "
                                    "otomatis dari pengukuran gambar. Hook diambil dari hooks.txt.",
            "model": "offline"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--kata", type=Path, help="file .kata.json hasil transkrip")
    a = ap.parse_args()
    kata = json.loads(a.kata.read_text(encoding="utf-8")) if a.kata else []
    print(json.dumps(rekomendasi(a.video, kata), ensure_ascii=False, indent=2))
