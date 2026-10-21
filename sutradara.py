"""Sutradara: Gemini menonton SELURUH video (gambar + suara) lalu menulis rencana edit lengkap:
potongan terbaik (boleh cold open), zoom, hook, elemen teks ala Canva, dan 3 versi tampilan.
Hasilnya file proyek .json yang bisa diedit lalu dirender:  python autoedit.py --proyek x.proyek.json

Yang dikirim ke Google: salinan kecil video (360p) + transkrip. Dihapus dari Google setelah selesai.

    python sutradara.py video.mp4 [--audio suara.m4a] [--rasio 9:16]
"""
import argparse
import base64
import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import autoedit as ae
import magic
import selera

HERE = Path(__file__).resolve().parent
API = "https://generativelanguage.googleapis.com"
JENIS_ELEMEN = {
    "judul": "judul besar di atas (format 'baris kecil|Kata Besar' boleh); untuk pembuka bab baru",
    "label": "label kecil huruf kapital berspasi di kiri atas: tempat, topik, atau konteks ('home studio, bandung')",
    "kata": "SATU kata kunci besar serif miring kuning di tengah, sangat singkat (0.8-1.5 s), untuk penekanan",
    "daftar": "poin bernomor kiri atas, diawali angka: '1 start small'; untuk langkah/tips",
    "kutipan": "kalimat pendek bermakna di tengah dengan tanda kutip; untuk momen reflektif",
    "tanggal": "stempel tanggal oranye ala kamera lama di kanan atas ('oct 19 2026'); untuk vlog/diary",
    "penutup": "kalimat penutup/ajakan di tengah di akhir video ('see you|Tomorrow', 'follow for|Day 13')",
}


def proksi(video, keluar, suara=None):
    """Salinan kecil untuk Gemini: 360p, 10 fps, suara mono. Cukup untuk menilai isi dan ritme.
    Kalau ada rekaman suara terpisah yang sudah sejajar, itu yang dipakai (lebih jelas)."""
    masukan = ["-i", str(video)] + (["-i", str(suara), "-map", "0:v", "-map", "1:a"] if suara else [])
    ae.jalankan(["ffmpeg", "-y", "-v", "error", *masukan, "-vf", "scale=-2:360,fps=10",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-c:a", "aac", "-ac", "1", "-b:a", "48k",
                 "-shortest", str(keluar)])


def adegan(video):
    """Waktu pergantian adegan (deteksi visual), supaya potongan bisa jatuh di batas shot."""
    e = subprocess.run(["ffmpeg", "-i", str(video), "-vf", "scale=320:-2,select='gt(scene,0.32)',showinfo",
                        "-an", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=ae.TANPA_JENDELA).stderr
    return [round(float(x.split("pts_time:")[1].split()[0]), 2) for x in e.splitlines() if "pts_time:" in x]


def unggah(path, kunci):
    data = path.read_bytes()
    if len(data) < 15e6:
        return {"inline_data": {"mime_type": "video/mp4", "data": base64.b64encode(data).decode()}}, None
    req = urllib.request.Request(
        f"{API}/upload/v1beta/files", method="POST", data=json.dumps({"file": {"display_name": path.stem}}).encode(),
        headers={"x-goog-api-key": kunci, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                 "X-Goog-Upload-Header-Content-Length": str(len(data)),
                 "X-Goog-Upload-Header-Content-Type": "video/mp4", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        url = r.headers["X-Goog-Upload-URL"]
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "X-Goog-Upload-Command": "upload, finalize", "X-Goog-Upload-Offset": "0", "Content-Length": str(len(data))})
    with urllib.request.urlopen(req, timeout=600) as r:
        f = json.loads(r.read())["file"]
    while f.get("state") == "PROCESSING":
        time.sleep(3)
        with urllib.request.urlopen(urllib.request.Request(f"{API}/v1beta/{f['name']}",
                                                           headers={"x-goog-api-key": kunci})) as r:
            f = json.loads(r.read())
    return {"file_data": {"mime_type": "video/mp4", "file_uri": f["uri"]}}, f


def hapus(f, kunci):
    try:
        urllib.request.urlopen(urllib.request.Request(f"{API}/v1beta/{f['name']}", method="DELETE",
                                                      headers={"x-goog-api-key": kunci}), timeout=30)
    except Exception:
        pass


def kalimat(kata):
    """Transkrip per frasa dengan waktu sumber, untuk dibaca Gemini."""
    return "\n".join(f"[{p[0]['s']:.2f}-{p[-1]['e']:.2f}] {' '.join(k['w'] for k in p)}"
                     for p in ae.potong_kalimat(kata, 14)) or "(tidak ada ucapan)"


def prompt(durasi, w, h, rasio, kata, potong_adegan, ukur):
    panduan = (HERE / "panduan_gaya.md").read_text(encoding="utf-8") if (HERE / "panduan_gaya.md").exists() else ""
    return f"""Kamu sutradara + editor video profesional untuk personal brand Instagram yang hangat, bersih, estetik.
Pemiliknya mendokumentasikan dirinya belajar dan bicara bahasa Inggris. Dia ingin memasukkan video mentah lalu
langsung dapat hasil yang terasa diedit profesional, tanpa mengatur apa pun.

Tonton video di atas SELURUHNYA (gambar dan suara). Durasi {durasi:.1f} s, {w}x{h}, hasil akhir rasio {rasio}.
Transkrip dengan waktu sumber (detik):
{kalimat(kata)}
Pergantian adegan (detik): {potong_adegan[:80]}
Hasil ukur koreksi otomatis (dasar slider): {json.dumps(ukur)}

PANDUAN GAYA (hasil analisis ratusan reels estetik yang disukai pemilik):
{panduan}

Tugas:
1. potongan: susun ulang video jadi versi terbaik. Buang take gagal/diulang, kalimat terpotong, salah ucap,
   bagian membosankan, dan jeda panjang. Jaga cerita tetap utuh dan kalimat tidak terpotong di tengah kata
   (pakai waktu dari transkrip). Urut maju sesuai waktu, KECUALI potongan pertama boleh "cold open": kalimat
   paling kuat/menarik dari tengah video diputar duluan (2-5 s), lalu video mulai dari awal.
   zoom tiap potongan: 1.0 normal, 1.08 sedikit dekat, 1.15 dekat untuk penekanan emosi. Selang-seling zoom
   antar potongan berdekatan supaya jump cut terasa seperti ganti angle. Tanpa ucapan (b-roll/vlog): pilih
   shot terbaik dengan ritme yang cocok dengan panduan.
   transisi tiap potongan (masuk ke potongan itu): "potong" (hard cut, hampir selalu) atau "fade" (dip lembut
   ke hitam) hanya saat suasana/tempat/waktu berganti atau sebelum penutup; maksimal 1-2 per video.
2. hook: judul pembuka bahasa Inggris maks 7 kata yang membuat berhenti scroll, sesuai isi; boleh format
   "baris kecil|Kata Besar". durasi_hook 2.5-4 s.
3. elemen: 2-8 elemen teks yang benar-benar menambah nilai (jangan ramai). Waktu dalam detik SUMBER
   (sama dengan transkrip). Jangan bertabrakan dengan hook di awal. Jenis:
   {json.dumps(JENIS_ELEMEN, ensure_ascii=False)}
   Teks elemen bahasa Inggris, huruf kecil kecuali judul/penutup, singkat.
3b. bingkai: "isi" = gambar memenuhi layar (crop otomatis mengikuti wajah) — cocok untuk video bicara/selfie;
   "letterbox" = gambar utuh dengan bingkai hitam atas-bawah, subtitle dan judul di bingkai — gaya film yang
   sering dipakai reels estetik, cocok untuk footage lebar/sinematik/b-roll. Hanya berpengaruh kalau bentuk
   video ({w}x{h}) berbeda jauh dari rasio hasil ({rasio}); kalau sama, pilih "isi".
4. versi: tepat 3 versi tampilan yang BERBEDA nyata, cocok dengan isi dan cahaya video. Versi 1 = paling aman
   dan paling cocok. Untuk tiap versi pilih gaya teks, warna, font judul, dan atur (slider: mulai dari hasil
   ukur, perbaiki masalah dulu, lalu sentuhan gaya kecil; kulit tetap natural).
   Selera pemilik: teks di BAWAH dan jelas (jangan "sinematik"); suka hangat-kotak dan font kartun ala WoodFont;
   "bold"/"pop" hanya untuk tutorial energik.
   {selera.ringkas()}
   Gaya: {json.dumps(ae.INFO_GAYA, ensure_ascii=False)}
   Warna: {json.dumps(ae.INFO_WARNA, ensure_ascii=False)}
   Font judul: {json.dumps(ae.INFO_JUDUL, ensure_ascii=False)}
   Atur (rentang): eksposur/kontras/saturasi/suhu/tint/bayangan/sorotan -100..100 (suhu + = hangat,
   tint + = magenta, bayangan + = angkat, sorotan - = redam), vignette/glow/tajam/grain 0..100.
5. ringkasan dan alasan dalam bahasa Indonesia, singkat."""


def skema():
    S = lambda **p: {"type": "OBJECT", "properties": p, "required": list(p)}
    T, N = {"type": "STRING"}, {"type": "NUMBER"}
    return S(
        jenis_video=T, ringkasan=T,
        potongan={"type": "ARRAY", "items": S(mulai=N, selesai=N, zoom=N,
                                              transisi={"type": "STRING", "enum": ["potong", "fade"]}, alasan=T)},
        hook=T, durasi_hook=N, bingkai={"type": "STRING", "enum": ["isi", "letterbox"]},
        elemen={"type": "ARRAY", "items": S(jenis={"type": "STRING", "enum": list(JENIS_ELEMEN)}, teks=T,
                                            mulai=N, selesai=N)},
        versi={"type": "ARRAY", "items": S(
            nama=T, gaya={"type": "STRING", "enum": list(ae.GAYA)},
            warna={"type": "STRING", "enum": list(ae.WARNA)}, judul={"type": "STRING", "enum": list(ae.JUDUL)},
            atur={"type": "OBJECT", "properties": {k: N for k in ae.ATUR}, "required": ae.ATUR}, alasan=T)},
    )


def tanya(bagian_video, teks, kunci, log):
    isi = {"contents": [{"role": "user", "parts": [bagian_video, {"text": teks}]}],
           "generationConfig": {"responseMimeType": "application/json", "responseSchema": skema(),
                                "temperature": 0.4}}
    galat = None
    for coba, model in enumerate(magic.model_urut()):
        if coba:
            log(f"Gemini ({model}) sedang menonton seluruh video dan menyusun edit...")
        try:
            req = urllib.request.Request(f"{API}/v1beta/models/{model}:generateContent",
                                         data=json.dumps(isi).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": kunci})
            # 3 menit cukup (biasanya 20-60 s); model yang menggantung dilewati
            with urllib.request.urlopen(req, timeout=180) as r:
                j = json.loads(r.read())
            hasil = json.loads(j["candidates"][0]["content"]["parts"][0]["text"])
            hasil["model"] = model
            return hasil
        except urllib.error.HTTPError as e:
            isi_galat = e.read().decode(errors="replace")
            galat = f"{model}: HTTP {e.code} {isi_galat[:200]}"
            if e.code in (401, 403):
                break
            if "PerDay" in isi_galat:  # kuota harian model ini habis: catat, langsung model berikutnya
                magic.tandai_habis(model)
                log(f"Kuota harian {model} habis, pindah model...")
                continue
            log(f"Gemini {model} sibuk ({e.code}), pindah model...")
            time.sleep(5)
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError) as e:
            galat = f"{model}: {e.__class__.__name__}"
            log(f"Gemini {model} tidak menjawab dengan benar, pindah model...")
    raise RuntimeError(f"Gemini gagal: {galat}")


def rapikan_potongan(rencana, kata, durasi):
    """Batas potongan tidak boleh memotong kata; di dalam tiap potongan jeda panjang tetap dibuang
    (jump cut) dengan zoom selang-seling supaya terasa seperti ganti angle."""
    hening = ae.bagian_dipakai(kata, durasi) if kata else [(0.0, durasi)]
    hasil = []
    for p in rencana:
        a, b = max(0.0, float(p["mulai"])), min(durasi, float(p["selesai"]))
        for k in kata:  # geser batas keluar dari tengah kata
            if k["s"] < a < k["e"]:
                a = max(0.0, k["s"] - 0.08)
            if k["s"] < b < k["e"]:
                b = min(durasi, k["e"] + 0.12)
        if b - a < 0.3:
            continue
        z = max(1.0, min(1.2, float(p.get("zoom") or 1.0)))
        sub = [(max(a, x), min(b, y)) for x, y in hening if min(b, y) - max(a, x) > 0.25] if kata else [(a, b)]
        for i, (x, y) in enumerate(sub or [(a, b)]):
            hasil.append({"mulai": round(x, 3), "selesai": round(y, 3),
                          "zoom": round(z * (1.06 if i % 2 else 1.0), 3),
                          # transisi hanya di awal potongan Gemini, bukan di jump cut di dalamnya
                          "transisi": p.get("transisi", "potong") if i == 0 else "potong"})
    return hasil


def ke_timeline(t, potongan):
    """Waktu sumber -> waktu di video hasil (kemunculan pertama). Di bagian yang dibuang: ke potongan berikutnya."""
    total, cadangan = 0.0, None
    for p in potongan:
        if p["mulai"] <= t <= p["selesai"]:
            return total + t - p["mulai"]
        if cadangan is None and p["mulai"] > t:
            cadangan = total
        total += p["selesai"] - p["mulai"]
    return cadangan if cadangan is not None else max(0.0, total - 2)


def buat_rencana(video, audio=None, rasio="9:16", log=print):
    """Kembalikan {rencana mentah Gemini + proyek dasar + 3 versi}. Proyek = dasar + satu versi."""
    video = Path(video)
    if not magic.boleh_online():
        raise RuntimeError("Edit otomatis butuh internet. Nyalakan 'Boleh pakai internet' di Setelan.")
    kunci = magic.kunci_api()
    w, h, durasi = ae.info_video(video)
    sumber = video
    if audio:
        log("Menyinkronkan suara rekaman terpisah...")
        sumber = video.with_name(f"{video.stem}.{Path(audio).stem}.sinkron.wav")
        if not sumber.exists():
            ae.siapkan_suara(video, Path(audio), sumber, durasi)
    log("Mentranskrip suara...")
    cache = video.with_name(video.stem + (f".{Path(audio).stem}" if audio else "") + ".kata.json")
    kata = ae.transkrip(sumber, None, cache)
    log("Mengukur warna dan adegan...")
    ukur, potong_adegan = ae.atur_otomatis(video), adegan(video)
    with tempfile.TemporaryDirectory() as tmp:
        kecil = Path(tmp) / "proksi.mp4"
        log("Menyiapkan salinan kecil untuk Gemini...")
        proksi(video, kecil, sumber if audio else None)
        bagian_video, berkas = unggah(kecil, kunci)
        try:
            log(f"Gemini ({magic.model_urut()[0]}) sedang menonton seluruh video dan menyusun edit...")
            r = tanya(bagian_video, prompt(durasi, w, h, rasio, kata, potong_adegan, ukur), kunci, log)
        finally:
            if berkas:
                hapus(berkas, kunci)

    potongan = rapikan_potongan(r["potongan"], kata, durasi) or [{"mulai": 0.0, "selesai": durasi, "zoom": 1.0}]
    total = sum(p["selesai"] - p["mulai"] for p in potongan)
    elemen = []
    for e in r["elemen"]:
        a = ke_timeline(float(e["mulai"]), potongan)
        b = min(total, a + max(0.8, float(e["selesai"]) - float(e["mulai"])))
        if a < float(r["durasi_hook"]) and e["jenis"] in ("judul", "kutipan", "kata"):
            continue  # tabrakan dengan hook pembuka
        elemen.append({"jenis": e["jenis"], "teks": e["teks"], "mulai": round(a, 2), "selesai": round(b, 2)})
    dasar = {"sumber": [str(video)], "audio": str(audio) if audio else None, "rasio": rasio,
             "hook": r["hook"], "durasi_hook": max(2.0, min(4.0, float(r["durasi_hook"]))),
             "subtitle": True, "potongan": potongan, "elemen": elemen, "bingkai": r.get("bingkai", "isi")}
    versi = []
    for v in r["versi"][:3]:
        atur = {k: max(0 if k in ("vignette", "glow", "tajam", "grain") else -100, min(100, round(v["atur"][k])))
                for k in ae.ATUR}
        versi.append({"nama": v["nama"], "gaya": v["gaya"], "warna": v["warna"], "judul": v["judul"],
                      "atur": atur, "alasan": v["alasan"]})
    log(f"Rencana selesai: {len(potongan)} potongan, {len(elemen)} elemen, {durasi:.0f}s -> {total:.0f}s")
    return {"ringkasan": r["ringkasan"], "jenis_video": r["jenis_video"], "model": r["model"],
            "durasi_asli": durasi, "durasi_hasil": round(total, 2), "dasar": dasar, "versi": versi}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--rasio", default="9:16", choices=ae.RASIO)
    a = ap.parse_args()
    hasil = buat_rencana(a.video.resolve(), a.audio.resolve() if a.audio else None, a.rasio)
    keluar = a.video.resolve().with_name(a.video.stem + ".rencana.json")
    keluar.write_text(json.dumps(hasil, ensure_ascii=False, indent=1), encoding="utf-8")
    for i, v in enumerate(hasil["versi"], 1):  # satu file proyek per versi, siap dirender / diedit
        p = {**hasil["dasar"], **{k: v[k] for k in ("gaya", "warna", "judul", "atur")}}
        f = a.video.resolve().with_name(f"{a.video.stem}.v{i}.proyek.json")
        f.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"versi {i} ({v['nama']}): {f}")
    print(json.dumps({k: hasil[k] for k in ("ringkasan", "jenis_video", "model", "durasi_hasil")},
                     ensure_ascii=False, indent=1))
